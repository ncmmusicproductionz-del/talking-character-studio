"""On-screen callouts that follow what the character is saying.

Found automatically in the script and timed to the exact spoken word:
  * years        "in 1848", "the 1800s"           -> a date stamp
  * numbers      "$5,000", "40%", "3 million years" -> a big number with its unit
  * places       "Germany", "New York"            -> a map pin card
  * key words    *highlighted* words              -> a sticker
  * notes        [note: Not Coca-Cola!]           -> a fact bar (also [overlay: ...])
At most one callout shows at a time, so the screen never gets cluttered.
"""
import math
import re

from PIL import Image, ImageDraw, ImageFilter

import sets
from sets import dark, light, mix

PLACES = '''Afghanistan Albania Algeria Argentina Armenia Australia Austria Babylon Bangladesh Belgium Bolivia Brazil Britain
Bulgaria Cambodia Canada Chile China Colombia Croatia Cuba Cyprus Czechia Denmark Egypt England Estonia Ethiopia Europe Finland
France Germany Ghana Greece Greenland Hawaii Holland Hungary Iceland India Indonesia Iran Iraq Ireland Israel Italy Jamaica Japan
Jordan Kenya Korea Latvia Lebanon Libya Lithuania Malaysia Mesopotamia Mexico Mongolia Morocco Nepal Netherlands Nigeria Norway
Pakistan Persia Peru Philippines Poland Portugal Prussia Romania Rome Russia Scandinavia Scotland Serbia Siberia Singapore
Slovakia Spain Sparta Sumer Sweden Switzerland Syria Taiwan Thailand Tibet Turkey Ukraine Vietnam Wales Yemen Africa Asia America
Antarctica Arctic Amsterdam Athens Baghdad Bangkok Barcelona Beijing Berlin Boston Cairo Chicago Constantinople Dublin Edinburgh
Florence Glasgow Istanbul Jerusalem Kyoto Lisbon London Madrid Manchester Mecca Milan Moscow Mumbai Munich Naples Paris Philadelphia
Prague Rio Salem Seoul Shanghai Sydney Tokyo Toronto Venice Vienna Warsaw Byzantium Pennsylvania California Texas Alaska Florida
Virginia Carolina Massachusetts Bavaria Normandy Transylvania Galway Cork Kilkenny Belfast Bethlehem Babylonia Persia Pompeii Troy
Punxsutawney Plymouth Gaul Carthage Phoenicia Macedonia'''.split()
MULTI_PLACES = ['New York', 'United States', 'United Kingdom', 'New Orleans', 'Los Angeles', 'San Francisco', 'South America',
                'North America', 'New Zealand', 'South Africa', 'Hong Kong', 'Ancient Egypt', 'Ancient Rome', 'Ancient Greece',
                'Washington', 'the Arctic', 'North Pole', 'South Pole', 'Middle East', 'Roman Empire', 'Sri Lanka', 'Costa Rica']
PLACE_SET = {p.lower() for p in PLACES}
YEAR_RE = re.compile(r"^(?:AD|BC)?((?:1[0-9]|20)\d\d)(s|'s)?$")
NUM_RE = re.compile(r'^(\$|£|€)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%|k|m|bn)?$', re.I)
UNITS = {'years', 'year', 'people', 'million', 'billion', 'thousand', 'hundred', 'miles', 'kilometres', 'kilometers', 'days',
         'times', 'pounds', 'dollars', 'percent', 'feet', 'metres', 'meters', 'tons', 'tonnes', 'trees', 'hours', 'minutes',
         'centuries', 'children', 'soldiers', 'kids', 'kg', 'km', 'degrees', 'species', 'eggs', 'letters', 'cards', 'votes'}
NUMBER_WORDS = {'million', 'billion', 'thousand', 'hundred'}
SMALL_WORDS = {'one', 'two', 'three', 'a', 'an', 'the'}


def _clean(tok):
    return tok.strip('.,!?;:"\'()[]—–-…')


def find_overlays(sentences, notes=None):
    """sentences need 'tokens' and 'word_times' (or start/end). Returns a list of callouts sorted by time."""
    found = []
    for si, s in enumerate(sentences):
        toks = [t for t, _ in s['tokens']]
        hls = [h for _, h in s['tokens']]
        wt = s.get('word_times') or []
        if len(wt) != len(toks):
            span = max(s['end'] - s['start'], 0.3)
            wt = [(s['start'] + span * i / max(len(toks), 1), s['start'] + span * (i + 1) / max(len(toks), 1)) for i in range(len(toks))]
        for i, raw in enumerate(toks):
            w = _clean(raw)
            if not w:
                continue
            t0 = wt[i][0]
            m = YEAR_RE.match(w)
            if m:
                label = m.group(1) + ('s' if m.group(2) else '')
                found.append(dict(t=t0, kind='year', text=label, sub='YEAR', prio=3, si=si))
                continue
            m = NUM_RE.match(w)
            if m:
                value = m.group(2)
                nxt = _clean(toks[i + 1]).lower() if i + 1 < len(toks) else ''
                nxt2 = _clean(toks[i + 2]).lower() if i + 2 < len(toks) else ''
                big = len(value.replace(',', '')) >= 2 or m.group(1) or m.group(3) or nxt in NUMBER_WORDS
                if not big:
                    continue
                text = (m.group(1) or '') + value + (m.group(3) or '')
                sub = ''
                if nxt in NUMBER_WORDS:
                    text += ' ' + nxt.upper()[0] + nxt[1:]
                    sub = nxt2 if nxt2 in UNITS else ''
                elif nxt in UNITS:
                    sub = nxt
                found.append(dict(t=t0, kind='number', text=text, sub=sub.upper(), prio=3, si=si))
                continue
            pair = (w + ' ' + _clean(toks[i + 1])) if i + 1 < len(toks) else ''
            mp = next((p for p in MULTI_PLACES if p.lower() == pair.lower()), None)
            if mp or (w.lower() in PLACE_SET and w[0].isupper()):
                found.append(dict(t=t0, kind='place', text=mp or w, sub='', prio=2, si=si))
                continue
            if hls[i] and len(w) >= 3 and not w.isdigit():
                # explicit *highlight* words become stickers; join a highlighted phrase
                j = i
                phrase = [w]
                while j + 1 < len(toks) and hls[j + 1] and len(phrase) < 3:
                    j += 1
                    phrase.append(_clean(toks[j]))
                if i > 0 and hls[i - 1]:
                    continue
                found.append(dict(t=t0, kind='keyword', text=' '.join(phrase), sub='', prio=1, si=si))
        if s.get('note'):
            found.append(dict(t=s['start'] + 0.2, kind='note', text=s['note'], sub='', prio=4, si=si))
    found.sort(key=lambda o: o['t'])
    out = []
    for o in found:
        if out and o['t'] - out[-1]['t'] < 2.4:
            if o['prio'] > out[-1]['prio'] and o['t'] - out[-1]['t'] < 0.8:
                out[-1] = o
            continue
        out.append(o)
    for a, b in zip(out, out[1:]):
        a['end'] = min(a['t'] + 2.8, b['t'] - 0.15)
    if out:
        out[-1]['end'] = out[-1]['t'] + 2.8
    return [dict(start=o['t'] - 0.08, end=o['end'], kind=o['kind'], text=o['text'], sub=o['sub']) for o in out]


# ------------------------------------------------------------------ drawing
def _shadowed(card, radius, blur, off=8):
    pad = blur * 3
    out = Image.new('RGBA', (card.width + pad * 2, card.height + pad * 2 + off), (0, 0, 0, 0))
    m = Image.new('L', out.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad + off, pad + card.width, pad + off + card.height], radius=radius, fill=150)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    sh = Image.new('RGBA', out.size, (0, 0, 0, 255))
    sh.putalpha(m)
    out.alpha_composite(sh)
    out.alpha_composite(card, (pad, pad))
    return out


def _pin(d, cx, cy, r, col):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.polygon([(cx - r * 0.82, cy + r * 0.45), (cx + r * 0.82, cy + r * 0.45), (cx, cy + r * 2.1)], fill=col)
    d.ellipse([cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42], fill=(255, 255, 255))


def render_card(o, scale, accent):
    """Draws a callout once at its final size (2x supersampled)."""
    S = 2
    u = scale * S
    kind = o['kind']
    acc = tuple(accent)
    if kind == 'year':
        f_big = sets.font(int(96 * u), 'black')
        f_small = sets.font(int(22 * u), 'bold')
        tw = f_big.getlength(o['text'])
        w, h = int(tw + 80 * u), int(170 * u)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(22 * u), fill=(250, 246, 236, 255))
        d.rounded_rectangle([0, 0, w - 1, int(44 * u)], radius=int(22 * u), fill=acc + (255,))
        d.rectangle([0, int(24 * u), w - 1, int(44 * u)], fill=acc + (255,))
        for x in (int(w * 0.25), int(w * 0.75)):
            d.rounded_rectangle([x - int(6 * u), -int(10 * u), x + int(6 * u), int(18 * u)], radius=int(6 * u), fill=dark(acc, 0.5) + (255,))
        d.text((w / 2, int(31 * u)), 'YEAR', font=f_small, fill=(255, 255, 255, 255), anchor='mm')
        d.text((w / 2, int(108 * u)), o['text'], font=f_big, fill=(28, 30, 40, 255), anchor='mm')
        rot = -4
    elif kind == 'number':
        f_big = sets.font(int(104 * u), 'impact')
        f_small = sets.font(int(26 * u), 'bold')
        tw = max(f_big.getlength(o['text']), f_small.getlength(o['sub']) if o['sub'] else 0)
        w, h = int(tw + 70 * u), int((176 if o['sub'] else 140) * u)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(24 * u), fill=(16, 20, 34, 235), outline=acc + (255,), width=int(4 * u))
        d.text((w / 2, int(72 * u)), o['text'], font=f_big, fill=light(acc, 0.35) + (255,), anchor='mm',
               stroke_width=int(2 * u), stroke_fill=dark(acc, 0.4) + (255,))
        if o['sub']:
            d.text((w / 2, int(146 * u)), o['sub'], font=f_small, fill=(230, 236, 250, 255), anchor='mm')
        rot = 3
    elif kind == 'place':
        f = sets.font(int(54 * u), 'black')
        tw = f.getlength(o['text'].upper())
        w, h = int(tw + 150 * u), int(104 * u)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(52 * u), fill=(255, 255, 255, 250))
        d.ellipse([int(14 * u), int(14 * u), int(90 * u), int(90 * u)], fill=mix(acc, (255, 255, 255), 0.82) + (255,))
        _pin(d, int(52 * u), int(42 * u), int(20 * u), (235, 64, 64))
        d.text((int(112 * u), h / 2), o['text'].upper(), font=f, fill=(24, 26, 36, 255), anchor='lm')
        rot = -2
    elif kind == 'note':
        f = sets.font(int(40 * u), 'bold')
        words, lines, cur = o['text'].split(), [], ''
        for wd in words:
            if f.getlength(cur + ' ' + wd) > 620 * u and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + ' ' + wd).strip()
        lines.append(cur)
        tw = max(f.getlength(l) for l in lines)
        w, h = int(tw + 110 * u), int((40 + 52 * len(lines)) * u)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(16 * u), fill=(250, 214, 64, 255))
        d.rounded_rectangle([int(16 * u), int(16 * u), int(30 * u), h - int(16 * u)], radius=int(7 * u), fill=(30, 30, 36, 255))
        for k, l in enumerate(lines):
            d.text((int(56 * u), int((20 + 26 + 52 * k) * u)), l, font=f, fill=(24, 24, 30, 255), anchor='lm')
        rot = 0
    else:
        f = sets.font(int(64 * u), 'impact')
        text = o['text'].upper()
        tw = f.getlength(text)
        w, h = int(tw + 70 * u), int(100 * u)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(18 * u), fill=acc + (255,))
        d.rounded_rectangle([int(6 * u), int(6 * u), w - int(6 * u), h - int(6 * u)], radius=int(14 * u),
                            outline=(255, 255, 255, 200), width=int(3 * u))
        d.text((w / 2, h / 2 + int(2 * u)), text, font=f, fill=(255, 255, 255, 255), anchor='mm',
               stroke_width=int(3 * u), stroke_fill=dark(acc, 0.45) + (255,))
        rot = -3
    card = _shadowed(card, int(22 * u), int(10 * u), int(8 * u))
    if rot:
        card = card.rotate(rot, resample=Image.BICUBIC, expand=True)
    return card.resize((max(1, card.width // S), max(1, card.height // S)), Image.LANCZOS)


def ease_back(x):
    x = max(0.0, min(1.0, x))
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def place_for(L, card):
    W, H = L['W'], L['H']
    if L['portrait']:
        return int(W * 0.05), int(H * 0.29)      # tucked over the bottom corner of the screen, clear of the head
    return int(W * 0.49), int(H * 0.09)


def draw(frame, o, card, t, L):
    local, left = t - o['start'], o['end'] - t
    if local < 0 or left < -0.25:
        return
    sc = ease_back(local / 0.32)
    alpha = 1.0 if left > 0 else max(0.0, 1 + left / 0.25)
    if sc <= 0.02 or alpha <= 0.02:
        return
    x, y = place_for(L, card)
    img = card
    if abs(sc - 1) > 0.01:
        img = card.resize((max(1, int(card.width * sc)), max(1, int(card.height * sc))), Image.BILINEAR)
    if alpha < 0.99:
        a = img.getchannel('A').point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    bob = math.sin(t * 2.2) * 3
    frame.paste(img, (int(x + (card.width - img.width) / 2), int(y + bob + (card.height - img.height) / 2)), img)
