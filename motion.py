"""Poses, head actions and the per-frame motion solver for the character rig."""
import math
import random

from rig import EXPRESSIONS

# arm angles (upper arm, forearm) in degrees: 0 = hanging down, 90 = out sideways, 180 = straight up, negative = across
# the body. hands: fist / open / point / thumb. front: arms drawn over the head. osc: (side, joint, degrees, speed).
POSES = {
    'rest':      dict(L=(10, 6), R=(10, 6)),
    'explain':   dict(L=(28, 105), R=(28, 105), hands='open', talk=('L', 'R')),
    'open':      dict(L=(40, 85), R=(40, 85), hands='open', talk=('L', 'R')),
    'point':     dict(L=(14, 8), R=(46, 125), hR='point', talk=('R',)),
    'point_up':  dict(L=(14, 8), R=(22, 172), hR='point', osc=[('R', 2, 4, 3.0)]),
    'think':     dict(L=(14, 8), R=(-22, -140), front=('R',), osc=[('R', 2, 3, 2.0)]),
    'celebrate': dict(L=(52, 160), R=(52, 160), hands='open', osc=[('L', 2, 10, 7.0), ('R', 2, 10, 7.0)], bounce=1),
    'thumbs':    dict(L=(14, 8), R=(30, 150), hR='thumb'),
    'wave':      dict(L=(14, 8), R=(36, 160), hR='open', osc=[('R', 2, 22, 9.0)]),
    'present':   dict(L=(38, 90), R=(20, 8), hL='open', talk=('L',)),
    'shrug':     dict(L=(46, 110), R=(46, 110), hands='open', shrug=1.0, tilt=7),
    'facepalm':  dict(L=(12, 6), R=(-160, -105), hR='open', front=('R',), tilt=-6, nod=1),
    'clap':      dict(L=(-20, -80), R=(-20, -80), hands='open', front=('L', 'R'),
                      osc=[('L', 2, 11, 15.0), ('R', 2, 11, 15.0)]),
    'count':     dict(L=(26, 120), R=(34, 132), hL='point', hR='open', talk=('R',)),
    'stop':      dict(L=(12, 6), R=(34, 118), hR='open'),
    'fist':      dict(L=(14, 8), R=(32, 168), osc=[('R', 1, 9, 9.0)], bounce=1),
    'type':      dict(L=(-10, -68), R=(-10, -68), hands='open', osc=[('L', 2, 6, 23.0), ('R', 2, 6, 19.0)], look=(0, 10)),
    'dance':     dict(L=(48, 140), R=(48, 140), hands='open', osc=[('L', 1, 14, 6.0), ('R', 1, -14, 6.0)], bounce=2, sway=1),
}
ACTIONS = ('nod', 'shake', 'bounce', 'jump', 'lookaround', 'lean', 'tilt')

AUTO_RULES = [   # (words, pose, emotion, action) used when the script has no tag for that part
    (('nobody knows', 'who knows', 'maybe', 'perhaps', 'no one knows', 'unclear'), 'shrug', 'confused', None),
    (('oops', 'mistake', 'terrible idea', 'went wrong', 'failed', 'disaster'), 'facepalm', 'tired', None),
    (('congratulations', 'well done', 'applause', 'bravo'), 'clap', 'happy', 'bounce'),
    (('first,', 'second,', 'third,', 'number one', 'number two', 'step one', 'firstly', 'secondly'), 'count', None, None),
    (('look up', 'the sky', 'above us', 'stars above', 'up there'), 'point_up', 'amazed', None),
    (('hello', 'hi there', 'welcome', 'goodbye', 'see you'), 'wave', 'happy', None),
    ((' love', 'adore', 'favourite', 'favorite'), None, 'love', None),
    (('amazing', 'incredible', 'mind-blowing', 'unbelievable', 'astonishing'), None, 'amazed', None),
    (('funny', 'joke', 'hilarious', 'ridiculous', 'laugh'), None, 'laugh', 'bounce'),
    (('strange', 'weird', 'bizarre', 'mysterious', 'confusing'), None, 'confused', 'tilt'),
    (('shocking', 'terrifying', 'horrifying', 'gruesome', 'deadly'), None, 'shocked', None),
    ((' died', 'tragic', 'sadly', 'lost forever', 'heartbreaking'), None, 'cry', None),
    ((' yes', 'exactly', "that's right", 'indeed', 'of course'), None, None, 'nod'),
    ((' no,', 'not true', ' never ', ' myth', ' wrong'), None, None, 'shake'),
    ((' stop', ' wait', 'hold on'), 'stop', 'focused', None),
    (('victory', ' won ', ' win ', 'champion'), 'fist', 'excited', 'jump'),
]


def auto_act(spoken):
    low = ' ' + spoken.lower() + ' '
    for words, pose, emo, action in AUTO_RULES:
        if any(w in low for w in words):
            return pose, emo, action
    return None, None, None


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _hands(p):
    h = p.get('hands', 'fist')
    return {'L': p.get('hL', h), 'R': p.get('hR', h)}


def _saccade(t, seed=0):
    """Small eye darts: the gaze jumps to a new spot every second or two, quickly, like real eyes."""
    n = int(t / 1.6)
    r = random.Random(n * 31 + seed)
    tx, ty = r.uniform(-7, 7), r.uniform(-4, 3)
    r0 = random.Random((n - 1) * 31 + seed)
    px, py = r0.uniform(-7, 7), r0.uniform(-4, 3)
    w = min(1.0, (t - n * 1.6) / 0.08)
    return (px + (tx - px) * w, py + (ty - py) * w)


def motion_state(sent, si, t, amp, blink, nxt_start=None, allow_type=True):
    """Everything the rig needs for one frame: arms, hands, body and head motion, eyes."""
    cur_s = sent[si] if si >= 0 else None
    typing = (allow_type and cur_s is not None and t > cur_s['end'] + 0.35
              and (nxt_start is None or nxt_start - cur_s['end'] > 1.4))
    prev_name = sent[si - 1]['pose'] if si > 0 else 'rest'
    if typing:
        cur, prev, start = POSES['type'], POSES.get(cur_s['pose'], POSES['rest']), cur_s['end'] + 0.35
    else:
        cur = POSES.get(cur_s['pose'] if cur_s else 'rest', POSES['rest'])
        prev = POSES.get(prev_name, POSES['rest'])
        start = cur_s['start'] if cur_s else 0.0
    w = ease((t - start) / 0.42)
    arms = {}
    for side in ('L', 'R'):
        a1 = prev[side][0] + (cur[side][0] - prev[side][0]) * w
        a2 = prev[side][1] + (cur[side][1] - prev[side][1]) * w
        if side in cur.get('talk', ()):
            a2 += amp * 12 * math.sin(t * 6.3 + (0 if side == 'L' else 1.9))
            a1 += amp * 5 * math.sin(t * 4.1 + (0 if side == 'L' else 0.8))
        arms[side] = [a1, a2]
    for side, joint, deg, speed in cur.get('osc', ()):
        arms[side][joint - 1] += deg * w * math.sin(t * speed + (0 if side == 'L' else 0.5))
    src = cur if w > 0.5 else prev
    st = dict(arms={s_: tuple(v) for s_, v in arms.items()}, hands=_hands(src), front=src.get('front', ()))
    st['shrug'] = prev.get('shrug', 0) + (cur.get('shrug', 0) - prev.get('shrug', 0)) * w

    idle = math.sin(t * 1.9)
    dy = idle * 3.0 + amp * 5.0
    dx = 0.0
    tilt = 2.4 * math.sin(t * 1.1) + amp * 3.2 * math.sin(t * 5.3) + cur.get('tilt', 0) * w
    head_dy = -amp * 13 + idle * 4 + (amp * 6 if amp > 0.5 else 0)
    head_dx = 0.0
    look = list(_saccade(t))
    if 'look' in cur:
        look = [look[0] * 0.3 + cur['look'][0] * w, look[1] * 0.3 + cur['look'][1] * w]
    if cur.get('bounce'):
        dy -= abs(math.sin(t * 7.0)) * 10 * cur['bounce'] * w
    if cur.get('sway'):
        dx += math.sin(t * 3.0) * 18 * w
        tilt += math.sin(t * 3.0) * 5 * w

    emotion = cur_s['emotion'] if cur_s else 'normal'
    action = cur_s.get('action') if cur_s else None
    if cur_s:
        local = t - cur_s['start']
        span = max(0.6, min(cur_s['end'] - cur_s['start'], 2.4))
        env = math.sin(max(0.0, min(1.0, local / span)) * math.pi) if local >= 0 else 0.0
        if action == 'nod' or (cur.get('nod') and local < 1.2 and not typing):
            head_dy += 9 * math.sin(local * 11) * env
            tilt *= 0.5
        elif action == 'shake':
            head_dx += 14 * math.sin(local * 13) * env
            tilt += 4 * math.sin(local * 13) * env
            look[0] += 6 * math.sin(local * 13) * env
        elif action == 'bounce':
            dy -= abs(math.sin(local * 8)) * 14 * env
        elif action == 'jump':
            dy -= math.sin(min(max(local, 0.0) / 0.7, 1.0) * math.pi) * 70
        elif action == 'lookaround':
            look = [12 * math.sin(local * 2.4), -2 + 3 * math.sin(local * 4.8)]
            tilt += 6 * math.sin(local * 2.4) * env
        elif action == 'lean':
            dx += 26 * env
            tilt -= 7 * env
        elif action == 'tilt':
            tilt += 11 * env
        if EXPRESSIONS.get(emotion, {}).get('bounce'):
            head_dy -= abs(math.sin(t * 10)) * 6
    open_ = (0.92 + 0.30 * amp) * (1 - 0.92 * blink)
    return dict(st, dy=dy, dx=dx, tilt=tilt, head_dy=head_dy, head_dx=head_dx, look=tuple(look), emotion=emotion,
                open=open_, glow=0.25 + 0.75 * amp)
