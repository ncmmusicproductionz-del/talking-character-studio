"""Script (+ optional recording) in, talking-character video out."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import footage as ftg
import images as imgs
import rig
import sets
import speech
from render import build_config, render_video, still_frame, write_srt
from scriptparse import parse_script, spoken_text
from speech import FFMPEG, NO_WINDOW

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAN_CACHE = os.path.join(ROOT, 'assets', 'plan')
SIZES = {
    ('vertical', 'final'): (1080, 1920), ('vertical', 'draft'): (540, 960),
    ('landscape', 'final'): (1920, 1080), ('landscape', 'draft'): (960, 540),
}
DEFAULT_SOURCES = ['wikimedia', 'nasa', 'cleveland']


# ----------------------------------------------------------------------------------------- scene planning

def script_key(text):
    return hashlib.sha1(text.strip().encode('utf-8')).hexdigest()[:12]


def plan_blocks(sentences, set_mode='auto', overrides=None, key='', stage_mode='mix'):
    """Splits the script into set blocks (one procedurally generated set each).
    A new set starts at every # chapter, at a [set: x] tag, or every ~45 seconds of narration."""
    overrides = overrides or {}
    full = ' '.join(s['spoken'] for s in sentences)
    global_theme, _ = sets.detect_theme(full)
    has_chapters = any(s['chapter'] for s in sentences)
    limit = 1400 if has_chapters else 650
    groups, cur, chars = [], [], 0
    for i, s in enumerate(sentences):
        new = bool(cur) and bool(s['chapter'] or s.get('set_theme') or chars >= limit)
        if new:
            groups.append(cur)
            cur, chars = [], 0
        cur.append(i)
        chars += len(s['spoken'])
    if cur:
        groups.append(cur)
    if len(groups) > 1:
        last = groups[-1]
        if sum(len(sentences[i]['spoken']) for i in last) < 120 and not sentences[last[0]]['chapter'] and not sentences[last[0]].get('set_theme'):
            groups[-2].extend(last)
            groups.pop()

    first_chapter = next((s['chapter'] for s in sentences if s['chapter']), None)
    blocks = []
    for bi, idx in enumerate(groups):
        text = ' '.join(sentences[i]['spoken'] for i in idx)
        tag = next((sentences[i]['set_theme'] for i in idx if sentences[i].get('set_theme') in sets.THEMES), None)
        ov = overrides.get(str(bi)) or {}
        if ov.get('theme') in sets.THEMES:
            theme = ov['theme']
        elif tag:
            theme = tag
        elif set_mode in sets.THEMES:
            theme = set_mode
        else:
            chap_text = next((sentences[i]['chapter'] for i in idx if sentences[i]['chapter']), '') or ''
            theme, scores = sets.detect_theme(chap_text + ' ' + chap_text + ' ' + text, fallback=global_theme)
            best = max(scores, key=lambda n: scores[n])
            if theme == global_theme and scores[best] >= 1 and scores.get(global_theme, 0) == 0:
                theme = best
        seed = int(ov['seed']) if str(ov.get('seed', '')).isdigit() else sets.seed_for(key + text[:200], bi)
        chap = next((sentences[i]['chapter'] for i in idx if sentences[i]['chapter']), None)
        title = chap or (first_chapter if bi == 0 and first_chapter else '') or imgs.keywords(text).title() or sets.THEMES[theme]['label']
        if ov.get('stage') in sets.STAGES:
            stage = ov['stage']
        elif stage_mode in sets.STAGES:
            stage = stage_mode
        else:   # mix: start in the room, then alternate with scenes out in the world
            stage = 'open' if bi % 2 == 1 else 'room'
        blocks.append(dict(idx=idx, theme=theme, seed=seed, title=title, text=text, stage=stage))
    return blocks


def plan_preview(script_text, fmt='landscape', set_mode='auto', overrides=None, character=None, stage_mode='mix'):
    """Plans the sets for a script and renders a small still of each. Returns a list of scene dicts."""
    sentences = parse_script(script_text)
    if not sentences:
        return []
    key = script_key(script_text)
    blocks = plan_blocks(sentences, set_mode, overrides, key, stage_mode)
    os.makedirs(PLAN_CACHE, exist_ok=True)
    tw, th = (270, 480) if fmt == 'vertical' else (480, 270)

    def thumb(b):
        ck = json.dumps(character or {}, sort_keys=True)
        name = hashlib.sha1(f"{b['theme']}|{b['seed']}|{b['title']}|{tw}x{th}|{ck}|{b['stage']}|v4".encode()).hexdigest()[:16] + '.jpg'
        path = os.path.join(PLAN_CACHE, name)
        if not os.path.exists(path):
            still_frame(b['theme'], b['seed'], b['title'], tw * 2, th * 2, character, b['stage']).resize((tw, th)).save(path, 'JPEG', quality=86)
        return name

    with ThreadPoolExecutor(4) as ex:
        names = list(ex.map(thumb, blocks))
    out = []
    c = character or {}
    for bi, (b, name) in enumerate(zip(blocks, names)):
        st = rig.make_style(c.get('mode', 'classic'), b['theme'], b['seed'] + int(c.get('seed', 0)), c.get('custom'))
        mine = c.get('mode') == 'image'
        out.append(dict(outfit='Your character' if mine else rig.OUTFITS[st['outfit']], hat='' if mine else rig.HATS[st['hat']], index=bi, theme=b['theme'], label=sets.THEMES[b['theme']]['label'], seed=b['seed'], title=b['title'],
                        snippet=b['text'][:140], seconds=round(len(b['text']) / 15.0, 1), sentences=len(b['idx']), stage=b['stage'], thumb=name))
    return out


# ----------------------------------------------------------------------------------------- pictures

def pick_pictures(sentences, opts, fmt, report, skip_scenes=()):
    """Chooses and downloads one picture per picture-scene. Returns (pictures, credit lines, warnings).
    skip_scenes: scene indexes that already have footage."""
    scenes = imgs.group_scenes(sentences)
    sources = [s for s in (opts.get('sources') or DEFAULT_SOURCES) if s in imgs.PROVIDERS]
    strict = opts.get('license', 'standard') == 'strict'
    orient = 'portrait' if fmt == 'vertical' else 'landscape'
    chosen = opts.get('chosen') or {}
    queries = opts.get('queries') or {}
    warnings = []

    def pick(i):
        sc = scenes[i]
        if sc['skip'] or i in skip_scenes:
            return None
        key = str(i)
        if opts.get('mode') == 'chosen' and key in chosen:
            cid = chosen[key]
            if not cid:
                return None
            if cid in imgs.CAND:
                return imgs.CAND[cid]
        q = (queries.get(key) or sc['query'] or '').strip()
        if not q:
            return None
        try:
            res, errs = imgs.search(q, sources, per_source=2, strict=strict, orient=orient, limit=4)
        except Exception as e:
            warnings.append(f'Image search failed for "{q}": {e}')
            return None
        if not res and errs:
            warnings.append(f'No pictures for "{q}" ({"; ".join(f"{k}: {v}" for k, v in errs.items())})')
        return res[0] if res else None

    report('Finding pictures', 0.09)
    with ThreadPoolExecutor(4) as ex:
        picks = list(ex.map(pick, range(len(scenes))))

    paths = {}

    def fetch(c):
        try:
            return c['id'], imgs.prepare(c), None
        except Exception as e:
            return c['id'], None, f'Could not download "{c["title"]}": {e}'

    uniq = {c['id']: c for c in picks if c}
    report('Downloading pictures', 0.12)
    with ThreadPoolExecutor(4) as ex:
        for cid, path, err in ex.map(fetch, uniq.values()):
            if path:
                paths[cid] = path
            elif err:
                warnings.append(err)

    pictures, used, prev = [], {}, None
    for i, (sc, c) in enumerate(zip(scenes, picks)):
        if i in skip_scenes:
            prev = None
            continue
        if c and c['id'] in paths:
            prev = c
        elif not sc['skip']:
            c = prev
        else:
            c = None
        if c and c['id'] in paths:
            used[c['id']] = c
            pictures.append(dict(start=sentences[sc['idx'][0]]['start'], end=sentences[sc['idx'][-1]]['end'], path=paths[c['id']]))
    credits = [imgs.credit_line(c) + (' [credit required]' if c['attribution_required'] else '') for c in used.values()]
    return pictures, credits, warnings


# ----------------------------------------------------------------------------------------- footage

def pick_footage(sentences, opts, fmt, W, H, fps, seconds, report, scenes=None):
    """Finds, downloads and cuts one clip per media scene. Returns (clips, {scene index: clip}, credits, warnings).
    opts: dict(sources=[...], display='screen'|'inside'|'bubble'|'mix', all=True).
    inside = full-screen clip with the character standing in the shot; bubble = full-screen clip with the character in a circle. With all=False only scenes tagged [clip:] get footage."""
    scenes = scenes or imgs.group_scenes(sentences)
    sources = [x for x in (opts.get('sources') or ftg.DEFAULT_SOURCES) if x in ftg.PROVIDERS]
    portrait = fmt == 'vertical'
    display = opts.get('display', 'screen')
    use_all = opts.get('all', True)
    limit = seconds or 1e9
    L = sets.layout_for(W, H)
    px0, py0, px1, py1 = L['panel']
    pw, ph = int(px1 - px0) // 2 * 2, int(py1 - py0) // 2 * 2
    warnings, used = [], {}

    wanted = []
    for i, sc in enumerate(scenes):
        start = sentences[sc['idx'][0]]['start']
        end = sentences[sc['idx'][-1]]['end']
        if sc['skip'] or start >= limit or sc.get('want') == 'image':
            continue
        if sc.get('clip_full'):
            # tagged b-roll covers its own sentence (and the next one if it is very short), so the character isn't hidden for long
            k = next(j for j in sc['idx'] if sentences[j].get('clip_query'))
            pos = sc['idx'].index(k)
            end = sentences[k]['end']
            if end - start < 1.8 and pos + 1 < len(sc['idx']):
                end = sentences[sc['idx'][pos + 1]]['end']
        if sc.get('want') == 'clip' or use_all:
            wanted.append((i, sc, start, min(end, limit)))

    def find(item):
        i, sc, start, end = item
        q = (sc.get('clip_query') or sc['query'] or '').strip()
        if not q:
            return i, None
        try:
            res, errs = ftg.search(q, sources, portrait=portrait, per_source=2, limit=4, min_seconds=end - start)
        except Exception as e:
            warnings.append(f'Footage search failed for "{q}": {e}')
            return i, None
        if not res and sc.get('want') == 'clip':
            warnings.append(f'No footage found for "{q}"' + (f' ({"; ".join(f"{k}: {v}" for k, v in errs.items())})' if errs else ''))
        return i, res

    report('Finding footage', 0.09)
    with ThreadPoolExecutor(4) as ex:
        found = dict(ex.map(find, wanted))

    taken = set()
    n_full = 0
    jobs = []
    for i, sc, start, end in wanted:
        cands = [c for c in (found.get(i) or []) if c['id'] not in taken] or (found.get(i) or [])
        if not cands:
            continue
        full = sc.get('clip_full') or display in ('full', 'inside', 'bubble') or (display == 'mix' and len(jobs) % 2 == 1)
        jobs.append((i, sc, start, end, cands, full))
        taken.add(cands[0]['id'])

    def fetch(job):
        i, sc, start, end, cands, full = job
        dur = end - start + 0.8
        size = (W, H) if full else (pw, ph)
        for c in cands[:3]:
            try:
                r = ftg.prepare(c, dur, size[0], size[1], fps, start_at=sc.get('clip_at') if c['provider'] == 'mine' else None)
                return i, dict(start=start, end=end, dir=r['dir'], frames=r['frames'], full=full,
                               style='bubble' if display == 'bubble' else 'inside'), c, None
            except Exception as e:
                err = f'Could not use clip "{c["title"]}": {e}'
        return i, None, None, err

    clips, by_scene = [], {}
    report('Downloading footage', 0.11)
    done = 0
    with ThreadPoolExecutor(3) as ex:
        for i, clip, c, err in ex.map(fetch, jobs):
            done += 1
            report(f'Preparing footage ({done}/{len(jobs)})', 0.11 + 0.03 * done / max(len(jobs), 1))
            if clip:
                clips.append(clip)
                by_scene[i] = clip
                used[c['id']] = c
            elif err:
                warnings.append(err)
    clips.sort(key=lambda c: c['start'])
    credits = [x for x in (ftg.credit_line(c) + (' [credit required]' if c['attribution_required'] else '')
                           if ftg.credit_line(c) else None for c in used.values()) if x]
    return clips, by_scene, credits, warnings


# ----------------------------------------------------------------------------------------- the whole job

def make_video(script_text, out_dir, mode='edge', voice='en-US-AndrewNeural', speed=0, audio_path=None,
               fmt='vertical', quality='final', fps=24, captions=True, seconds=None, progress=None, images=None,
               look=None, music=None, live_path=None, video_clips=None):
    """mode: 'edge' (neural voices, needs internet), 'windows' (offline) or 'file' (use audio_path).
    look: dict(set_mode='auto'|theme, camera='dynamic'|'static', caption_style='bold'|'box'|'minimal'|'off', overrides={})
    music: dict(path=..., volume=0..1) or None.
    video_clips: dict(sources=[...], display='screen'|'full'|'mix', all=True) to use footage, or None."""
    def report(msg, frac=None):
        if progress:
            progress(msg, frac)

    look = look or {}
    os.makedirs(out_dir, exist_ok=True)
    report('Reading the script', 0.0)
    sentences = parse_script(script_text)
    if not sentences:
        raise ValueError('The script is empty. Paste some narration first.')

    audio = os.path.join(out_dir, 'voice.mp3' if mode != 'windows' else 'voice.wav')
    if mode == 'file':
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError('No audio file was uploaded.')
        ext = os.path.splitext(audio_path)[1] or '.mp3'
        audio = os.path.join(out_dir, 'voice' + ext)
        shutil.copyfile(audio_path, audio)
    else:
        report('Generating the voiceover', 0.02)
        speech.synthesize(spoken_text(sentences), mode, voice, speed, audio,
                          progress=lambda m, f: report(m, 0.02 + 0.05 * f))

    report('Listening to the audio', 0.07)
    analysis = speech.analyze(audio, fps)
    words = speech.load_words(audio) if mode == 'edge' else None
    match = speech.align_words(sentences, words, analysis['duration']) if words else 0.0
    if match < 0.6:      # no word timings (Windows voice, own recording) or a poor match: fall back to pause detection
        for s in sentences:
            s.pop('word_times', None)
        speech.align_sentences(sentences, analysis['norm'], analysis['hop'], analysis['duration'])

    report('Designing the sets', 0.08)
    blocks = plan_blocks(sentences, look.get('set_mode', 'auto'), look.get('overrides'), script_key(script_text),
                         look.get('stage', 'mix'))

    W, H = SIZES[(fmt, quality)]
    pictures, credits, warnings, clips, by_scene = [], [], [], [], {}
    tagged = any(s.get('clip_query') for s in sentences)
    if video_clips or tagged:
        vopts = dict(video_clips or {}, all=bool(video_clips) and (video_clips or {}).get('all', True))
        clips, by_scene, c2, w2 = pick_footage(sentences, vopts, fmt, W, H, fps, seconds, report)
        credits += c2
        warnings += w2
    if images and images.get('mode') in ('auto', 'chosen'):
        p1, c1, w1 = pick_pictures(sentences, images, fmt, report, skip_scenes=set(by_scene))
        pictures, credits, warnings = p1, c1 + credits, w1 + warnings
    style = look.get('caption_style', 'bold' if captions else 'off')
    if not captions:
        style = 'off'
    cfg = build_config(sentences, analysis, W, H, fps, blocks, seconds=seconds, caption_style=style,
                       camera=look.get('camera', 'dynamic'), pictures=pictures, character=look.get('character'),
                       clips=clips, show_overlays=look.get('overlays', True))

    name = 'preview' if seconds else 'video'
    out_mp4 = os.path.join(out_dir, f'{name}.mp4')
    out_srt = os.path.join(out_dir, f'{name}.srt')
    write_srt(cfg, out_srt)
    credits_path = None
    if credits:
        credits_path = os.path.join(out_dir, f'{name}_image_credits.txt')
        with open(credits_path, 'w', encoding='utf-8') as f:
            f.write('Pictures and footage used in this video (paste into your video description):\n\n' + '\n'.join(credits) + '\n')
    report('Animating the character', 0.15)
    render_video(cfg, audio, out_mp4, quality, progress=lambda f: report('Animating the character', 0.15 + 0.82 * f),
                 music=music, live_path=live_path)

    poster = os.path.join(out_dir, f'{name}_poster.jpg')
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-ss', f'{min(2.0, cfg["duration"] / 2):.2f}', '-i', out_mp4,
                    '-frames:v', '1', '-vf', 'scale=640:-2', poster], creationflags=NO_WINDOW)
    report('Done', 1.0)
    return dict(video=out_mp4, srt=out_srt, audio=audio, credits=credits_path, warnings=warnings,
                poster=poster if os.path.exists(poster) else None, images_used=len(pictures), clips_used=len(clips), seconds=cfg['duration'],
                sentences=len(sentences), sets=[dict(theme=b['theme'], title=b['title']) for b in blocks])
