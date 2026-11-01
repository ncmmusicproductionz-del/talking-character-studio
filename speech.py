"""Voice generation, audio analysis and sentence timing."""
import asyncio
import re
import json
import os
import subprocess
import tempfile
from array import array

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

EDGE_VOICES = [
    ('en-US-AndrewNeural', 'Andrew (US male, warm)'),
    ('en-US-ChristopherNeural', 'Christopher (US male, calm)'),
    ('en-US-GuyNeural', 'Guy (US male, deep)'),
    ('en-US-EricNeural', 'Eric (US male, smooth)'),
    ('en-US-AriaNeural', 'Aria (US female)'),
    ('en-US-JennyNeural', 'Jenny (US female)'),
    ('en-US-MichelleNeural', 'Michelle (US female)'),
    ('en-GB-RyanNeural', 'Ryan (UK male)'),
    ('en-GB-ThomasNeural', 'Thomas (UK male)'),
    ('en-GB-SoniaNeural', 'Sonia (UK female)'),
    ('en-IE-ConnorNeural', 'Connor (Irish male)'),
    ('en-IE-EmilyNeural', 'Emily (Irish female)'),
    ('en-AU-WilliamNeural', 'William (Australian male)'),
    ('en-AU-NatashaNeural', 'Natasha (Australian female)'),
]


def windows_voices():
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                             capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout
        return [v.strip() for v in out.splitlines() if v.strip()]
    except Exception:
        return []


def edge_available():
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


def _rate_str(speed_pct):
    return f'{int(speed_pct):+d}%'


def words_path(audio_path):
    return audio_path + '.words.json'


def synth_edge(text, voice, speed_pct, out_path, progress=None):
    """Neural voice. Also saves the exact time every word is spoken (from the service's word boundary events),
    which is what keeps captions, gestures and overlays in sync with the voice."""
    import edge_tts
    words = []
    est = max(5.0, len(text.split()) / 2.5 * (1 - speed_pct / 100.0))     # expected length in seconds

    async def run():
        com = edge_tts.Communicate(text, voice, rate=_rate_str(speed_pct), boundary='WordBoundary')
        with open(out_path, 'wb') as f:
            async for chunk in com.stream():
                if chunk['type'] == 'audio':
                    f.write(chunk['data'])
                elif chunk['type'] == 'WordBoundary':
                    st = chunk['offset'] / 1e7
                    words.append(dict(w=chunk['text'], s=round(st, 3), e=round(st + chunk['duration'] / 1e7, 3)))
                    if progress and len(words) % 8 == 0:
                        # also the moment a Cancel press is noticed (the callback raises)
                        progress(f'Generating the voiceover ({int(st // 60)}:{int(st % 60):02d} of about {int(est // 60)}:{int(est % 60):02d})',
                                 min(1.0, st / est))

    asyncio.run(run())
    with open(words_path(out_path), 'w', encoding='utf-8') as f:
        json.dump(words, f)
    return words


def load_words(audio_path):
    try:
        with open(words_path(audio_path), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _norm(w):
    return re.sub(r'[^a-z0-9]', '', w.lower())


def align_words(sentences, words, duration):
    """Matches every script word to the voice's own word timings. Sets start/end on each sentence and an exact
    (start, end) per caption token in s['word_times']. Returns the share of words that matched."""
    bw = [[_norm(w['w']), w['s'], w['e']] for w in words if _norm(w['w'])]
    j, hits, total = 0, 0, 0
    for s in sentences:
        times = []
        for tok, _ in s['tokens']:
            n = _norm(tok)
            if not n:
                times.append(None)
                continue
            total += 1
            found = None
            for k in range(j, min(j + 6, len(bw))):
                b = bw[k][0]
                if b == n or (len(n) > 2 and len(b) > 2 and n.startswith(b)):
                    found = k
                    break
                if b.startswith(n) and len(b) > len(n):
                    # the voice reported several script words as one ("In 1848"): give this word its share of the time
                    bs, be = bw[k][1], bw[k][2]
                    cut = bs + (be - bs) * len(n) / len(b)
                    times.append((bs, cut))
                    bw[k] = [b[len(n):], cut, be]
                    j = k
                    hits += 1
                    found = -1
                    break
            if found == -1:
                continue
            if found is None:
                times.append(None)
                continue
            times.append((bw[found][1], bw[found][2]))
            j = found + 1
            hits += 1
        s['word_times'] = times
    # fill the gaps by interpolation and set sentence bounds
    flat = [(si, ti) for si, s in enumerate(sentences) for ti in range(len(s['tokens']))]
    known = [(idx, sentences[si]['word_times'][ti]) for idx, (si, ti) in enumerate(flat) if sentences[si]['word_times'][ti]]
    if not known:
        return 0.0
    ki = 0
    for idx, (si, ti) in enumerate(flat):
        if sentences[si]['word_times'][ti]:
            continue
        while ki + 1 < len(known) and known[ki + 1][0] < idx:
            ki += 1
        a = known[ki] if known[ki][0] < idx else None
        b = next((kn for kn in known[ki:] if kn[0] > idx), None)
        if a and b:
            f = (idx - a[0]) / (b[0] - a[0])
            t = a[1][1] + (b[1][0] - a[1][1]) * f
        elif a:
            t = min(duration, a[1][1] + 0.25 * (idx - a[0]))
        else:
            t = max(0.0, b[1][0] - 0.25 * (b[0] - idx))
        sentences[si]['word_times'][ti] = (t, t + 0.2)
    prev_end = 0.0
    for i, s in enumerate(sentences):
        wt = s['word_times'] or [(prev_end, prev_end + 0.5)]
        s['start'] = max(prev_end, wt[0][0] - 0.05)
        s['end'] = max(s['start'] + 0.2, wt[-1][1])
        prev_end = s['end']
    # each sentence runs until the next one starts, so poses hold through the pauses
    for a, b in zip(sentences, sentences[1:]):
        a['end'] = max(a['end'], min(b['start'], a['end'] + 0.6))
    sentences[-1]['end'] = min(duration, sentences[-1]['end'] + 0.3)
    return hits / max(total, 1)


def synth_windows(text, voice, speed_pct, out_path):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        txt = f.name
    rate = max(-10, min(10, round(speed_pct / 10)))
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"if ('{voice}') {{ $s.SelectVoice('{voice}') }};"
        f"$s.Rate = {rate};"
        f"$s.SetOutputToWaveFile('{out_path}');"
        f"$s.Speak([System.IO.File]::ReadAllText('{txt}', [System.Text.Encoding]::UTF8));"
        "$s.Dispose()"
    )
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                           capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError('Windows voice failed: ' + (r.stderr or r.stdout)[:300])
    finally:
        os.unlink(txt)


def synthesize(text, mode, voice, speed_pct, out_path, progress=None):
    """progress(message, fraction 0..1) is called while a neural voice downloads."""
    if mode == 'edge':
        synth_edge(text, voice, speed_pct, out_path, progress)
    elif mode == 'windows':
        synth_windows(text, voice, speed_pct, out_path)
    else:
        raise ValueError('unknown voice mode ' + mode)
    return out_path


def decode_pcm(path, seconds=None):
    cmd = [FFMPEG, '-v', 'error', '-i', path]
    if seconds:
        cmd += ['-t', str(seconds)]
    cmd += ['-f', 's16le', '-ac', '1', '-ar', '16000', '-']
    r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError('Could not read audio: ' + r.stderr.decode('utf-8', 'ignore')[:300])
    a = array('h')
    a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    return a


def analyze(path, fps, seconds=None):
    """Returns dict(duration, env (per video frame, 0..1), rms (per 20 ms), hop)."""
    pcm = decode_pcm(path, seconds)
    sr = 16000
    dur = len(pcm) / sr
    hop = 320
    rms = []
    for a in range(0, len(pcm) - hop + 1, hop):
        seg = pcm[a:a + hop]
        rms.append((sum(x * x for x in seg) / hop) ** 0.5)
    if not rms:
        raise RuntimeError('Audio is empty')
    srt = sorted(rms)
    ref = max(srt[int(len(srt) * 0.95)], 1.0)
    norm = [min(1.0, r / ref) for r in rms]
    nframes = int(dur * fps) + 1
    per = 0.02
    env, s = [], 0.0
    for i in range(nframes):
        a = int(i / fps / per)
        b = max(a + 1, int((i + 1) / fps / per))
        raw = max(norm[a:b] or [0.0])
        raw = raw if raw > 0.06 else 0.0
        s = s + (raw - s) * (0.65 if raw > s else 0.25)
        env.append(s)
    return dict(duration=dur, env=env, norm=norm, hop=per)


def _silences(norm, hop, thresh=0.04, min_len=0.16):
    out, start = [], None
    for i, v in enumerate(norm):
        if v < thresh:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) * hop >= min_len:
                out.append((start * hop, i * hop))
            start = None
    if start is not None and (len(norm) - start) * hop >= min_len:
        out.append((start * hop, len(norm) * hop))
    return out


def align_sentences(sentences, norm, hop, duration):
    """Gives each sentence start/end seconds by splitting the speech in proportion to text
    length and snapping each boundary to the nearest pause in the audio."""
    n = len(sentences)
    sil = _silences(norm, hop)
    first = 0.0
    last = duration
    if sil and sil[0][0] < 0.05:
        first = sil[0][1]
    if sil and sil[-1][1] > duration - 0.05:
        last = sil[-1][0]
    inner = [s for s in sil if s[0] > first + 0.2 and s[1] < last - 0.2]
    weights = [max(len(s['spoken']), 4) for s in sentences]
    total = float(sum(weights))
    cum, bounds = 0.0, []
    for w in weights[:-1]:
        cum += w
        bounds.append(first + (last - first) * cum / total)
    used, snapped = set(), []
    prev = first
    for b in bounds:
        best, best_score = None, None
        for idx, (a, e) in enumerate(inner):
            if idx in used:
                continue
            c = (a + e) / 2
            dist = abs(c - b)
            if dist > 1.6 or c <= prev + 0.3:
                continue
            score = dist - min(e - a, 1.0) * 0.6
            if best_score is None or score < best_score:
                best, best_score = idx, score
        if best is not None:
            used.add(best)
            c = sum(inner[best]) / 2
            snapped.append(c)
            prev = c
        else:
            snapped.append(max(b, prev + 0.3))
            prev = snapped[-1]
    edges = [first] + snapped + [last]
    for i, s in enumerate(sentences):
        s['start'] = edges[i]
        s['end'] = edges[i + 1]
    return sentences
