"""Turns a pasted or uploaded script into sentences the animator can act out.

Supported script features (all optional):
  * Plain paragraphs of narration.
  * Lines starting with '#' become on-screen chapter titles.
  * Markdown scripts: '**VO:** narration' is used, '**Visual:**' / '**Note...' / '---' lines are skipped.
  * *word* highlights a word in the captions.
  * [tags] anywhere in a sentence control the character:
      gestures  [explain] [open] [point] [point up] [think] [celebrate] [thumbs] [wave] [present] [shrug]
                [facepalm] [clap] [count] [stop] [fist] [type] [dance] [rest]
      faces     [happy] [excited] [surprised] [angry] [mad] [tired] [sleepy] [focused] [determined] [sad] [cry]
                [wink] [love] [amazed] [dizzy] [shocked] [suspicious] [laugh] [confused] [cool] [normal]
      moves     [nod] [shake] [bounce] [jump] [look around] [lean] [tilt]
      extras    [idea]  (shows a lightbulb)
  * Pictures: [image: roman festival] picks what to search for, [noimage] keeps the set's own panel.
  * Overlays: years, numbers, places and *highlighted* words pop up automatically; [note: Not Coca-Cola!] adds a fact card.
  * Footage: [clip: rocket launch] plays a video clip (on the set's screen or full screen, as chosen in the app),
    [broll: city at night] always plays it full screen with the character in a corner bubble.
"""
import re

from motion import ACTIONS, POSES, auto_act
from rig import EXPRESSIONS

POSE_TAGS = set(POSES)
EMOTION_TAGS = set(EXPRESSIONS)
ACTION_TAGS = set(ACTIONS)
ALIASES = {'point up': 'point_up', 'pointup': 'point_up', 'thumbs up': 'thumbs', 'thumbsup': 'thumbs', 'face palm': 'facepalm',
           'look around': 'lookaround', 'typing': 'type', 'clapping': 'clap', 'waving': 'wave', 'angry face': 'angry',
           'heart eyes': 'love', 'star eyes': 'amazed', 'crying': 'cry', 'sunglasses': 'cool', 'sleep': 'sleepy',
           'shook': 'shocked', 'nodding': 'nod', 'head shake': 'shake', 'surprise': 'surprised', 'hearts': 'love'}
TAG_RE = re.compile(r'\[([A-Za-z _]{2,14})\]')
IMAGE_RE = re.compile(r'\[image:\s*([^\]]{2,80})\]', re.I)
NOTE_RE = re.compile(r'\[(?:note|overlay|fact):\s*([^\]]{2,90})\]', re.I)
CLIP_RE = re.compile(r'\[(clip|video|footage|broll|b-roll):\s*([^\]]{2,80})\]', re.I)
SET_RE = re.compile(r'\[set:\s*([A-Za-z]{2,20})\]', re.I)
PROTECT = str.maketrans({'.': '\x01', '!': '\x02', '?': '\x03', '…': '\x04'})
UNPROTECT = str.maketrans({'\x01': '.', '\x02': '!', '\x03': '?', '\x04': '…'})
LEAD_TAGS_RE =re.compile(r'^((?:\s*\[[^\]]{2,90}\])+)\s*')
SPLIT_RE =re.compile(r'(?<=[.!?…])["\')\]]*\s+')
IDEA_WORDS = ('idea', 'discover', 'clue', 'realize', 'realise', 'secret', 'twist')
SKIP_PREFIXES = ('**visual', '**note', '**editor', '**scene', 'visual:', 'note for', 'editor note', '---', '___', '***')
WEAK_END = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'at', 'for', 'with', 'and', 'or', 'but', 'that', 'is', 'was', 'so',
            'it', 'its', 'by', 'from', 'as', 'than', 'into', 'their', 'your', 'our', 'his', 'her', 'my', 'this', 'they'}
AUTO_POSES = ['explain', 'open', 'point', 'explain', 'rest', 'open', 'present', 'explain']


def _clean_markdown(line):
    line = line.replace('**', '')
    line = re.sub(r'^\s*[-+>]\s+', '', line)
    return line.strip()


def _tokens(text):
    toks, hl = [], False
    for raw in text.split():
        if raw.startswith('*'):
            hl = True
        end = '*' in raw[1:]
        tok = raw.replace('*', '')
        if tok:
            bare = re.sub(r'[^A-Za-z0-9]', '', tok)
            auto = any(c.isdigit() for c in bare) or (len(bare) >= 3 and bare.isupper())
            toks.append((tok, hl or auto))
        if end:
            hl = False
    return toks


def parse_script(text):
    """Returns a list of sentence dicts: spoken, tokens, pose, emotion, idea, chapter."""
    lines = []
    chapter = None
    for raw in text.replace('\r', '').split('\n'):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if line.startswith('#'):
            chapter = re.sub(r'\(.*?\)', '', line.lstrip('#')).strip(' -:')
            continue
        if low.startswith(SKIP_PREFIXES):
            continue
        m = re.match(r'^\**\s*(vo|narrator|voice[- ]?over|voiceover)\s*:\**\s*(.*)$', line, re.I)
        if m:
            line = m.group(2)
        line = _clean_markdown(line).strip('"“”')
        if line:
            lines.append((line, chapter))
            chapter = None
    sentences = []
    for line, chap in lines:
        # punctuation inside [tags] must not end a sentence ("[note: Not Coca-Cola!]")
        line = re.sub(r'\[[^\]]*\]', lambda m: m.group(0).translate(PROTECT), line)
        parts = [s.strip().translate(UNPROTECT) for s in SPLIT_RE.split(line) if s.strip()]
        # tags written right after a full stop belong to the sentence before them: "It's loud. [clip: rocket] Then..."
        for n in range(1, len(parts)):
            m = LEAD_TAGS_RE.match(parts[n])
            if m:
                parts[n - 1] += ' ' + m.group(1).strip()
                parts[n] = parts[n][m.end():].strip()
        parts = [p for p in parts if p]
        for n, part in enumerate(parts):
            im = IMAGE_RE.search(part)
            image_query = im.group(1).strip() if im else None
            part = IMAGE_RE.sub('', part)
            nm = NOTE_RE.search(part)
            note = nm.group(1).strip() if nm else None
            part = NOTE_RE.sub('', part)
            cm = CLIP_RE.search(part)
            clip_query = cm.group(2).strip() if cm else None
            clip_full = bool(cm) and cm.group(1).lower() in ('broll', 'b-roll')
            clip_at = None
            if clip_query:
                tm = re.search(r'@\s*(?:(\d+):)?(\d{1,2})(?:\.(\d))?\s*$', clip_query)
                if tm:
                    clip_at = int(tm.group(1) or 0) * 60 + int(tm.group(2)) + int(tm.group(3) or 0) / 10
                    clip_query = clip_query[:tm.start()].strip() or clip_query
            part = CLIP_RE.sub('', part)
            sm = SET_RE.search(part)
            set_theme = sm.group(1).strip().lower() if sm else None
            part = SET_RE.sub('', part)
            tags = [t.lower().strip() for t in TAG_RE.findall(part)]
            tags = [ALIASES.get(t, t) for t in tags]
            part = TAG_RE.sub('', part).strip()
            if not re.search(r'[A-Za-z0-9]', part):
                if sentences:    # tags standing alone after a full stop belong to the sentence before them
                    last = sentences[-1]
                    last['image_query'] = last['image_query'] or image_query
                    last['note'] = last.get('note') or note
                    if clip_query and not last['clip_query']:
                        last['clip_query'], last['clip_full'], last['clip_at'] = clip_query, clip_full, clip_at
                    last['set_theme'] = last['set_theme'] or set_theme
                    last['no_image'] = last['no_image'] or bool({'noimage', 'no image'} & set(tags))
                    last['pose'] = last['pose'] or next((t for t in tags if t in POSE_TAGS), None)
                    last['emotion'] = last['emotion'] or next((t for t in tags if t in EMOTION_TAGS), None)
                    last['idea'] = last['idea'] or ('idea' in tags)
                    last['action'] = last['action'] or next((t for t in tags if t in ACTION_TAGS), None)
                continue
            spoken = part.replace('*', '')
            pose = next((t for t in tags if t in POSE_TAGS), None)
            emotion = next((t for t in tags if t in EMOTION_TAGS), None)
            action = next((t for t in tags if t in ACTION_TAGS), None)
            if 'think' in tags and not emotion:
                emotion = None
            sentences.append(dict(
                spoken=spoken, tokens=_tokens(part), pose=pose, emotion=emotion, action=action,
                idea=('idea' in tags) or any(w in spoken.lower() for w in IDEA_WORDS),
                image_query=image_query, clip_query=clip_query, clip_full=clip_full, clip_at=clip_at, note=note, no_image=bool({'noimage', 'no image'} & set(tags)), set_theme=set_theme,
                chapter=chap if n == 0 else None))
    for i, s in enumerate(sentences):
        q = s['spoken'].rstrip('"\')').endswith('?')
        ex = s['spoken'].rstrip('"\')').endswith('!')
        a_pose, a_emo, a_act = auto_act(s['spoken'])
        s['pose'] = s['pose'] or a_pose
        s['emotion'] = s['emotion'] or a_emo
        s['action'] = s['action'] or a_act
        if not s['pose']:
            if q:
                s['pose'] = 'think'
            elif i == 0:
                s['pose'] = 'point'
            elif i == len(sentences) - 1 and len(sentences) > 2:
                s['pose'] = 'thumbs'
            elif ex:
                s['pose'] = 'celebrate'
            else:
                s['pose'] = AUTO_POSES[i % len(AUTO_POSES)]
        if not s['emotion']:
            if s['pose'] == 'think':
                s['emotion'] = 'think'
            elif q:
                s['emotion'] = 'think'
            elif ex:
                s['emotion'] = 'excited'
            elif i == len(sentences) - 1 and len(sentences) > 2:
                s['emotion'] = 'happy'
            elif s['pose'] == 'thumbs':
                s['emotion'] = 'happy'
            else:
                s['emotion'] = 'normal'
    return sentences


def spoken_text(sentences):
    return ' '.join(s['spoken'] for s in sentences)


def split_caption_chunks(tokens, max_words):
    """Break a sentence's tokens into caption-sized chunks, preferring commas."""
    if len(tokens) <= max_words:
        return [tokens]
    chunks, cur = [], []
    for tok in tokens:
        cur.append(tok)
        w = tok[0]
        if len(cur) >= max_words or (len(cur) >= 3 and w[-1:] in ',;:'):
            carry = []
            while len(cur) > 2 and cur[-1][0].lower().strip(',;:') in WEAK_END and cur[-1][0][-1:] not in ',;:':
                carry.insert(0, cur.pop())
            chunks.append(cur)
            cur = carry
    if cur:
        if chunks and len(cur) <= 2:
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return chunks
