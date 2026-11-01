"""Characters you upload yourself, animated PNGtuber-style.

A character is one picture (required) plus optional "talking" and "blinking" pictures drawn on the same canvas.
The studio removes a plain background, swaps to the talking picture while the voice is loud, blinks, and gives the whole
character squash-and-stretch, breathing, bounces, jumps, leans and head tilts from the same motion data the built-in
character uses. Expression effects (hearts, tears, zzz, ?, sparkles...) float around its head.
"""
import io
import json
import math
import os
import re
import time
import uuid

from PIL import Image, ImageDraw, ImageFilter

import rig

ROOT = os.path.dirname(os.path.abspath(__file__))
CHAR_DIR = os.path.join(ROOT, 'assets', 'characters')
SLOTS = ('idle', 'talk', 'blink')
MAX_SIDE = 1600
EXTRA_FOR = {k: v.get('extras', ()) for k, v in rig.EXPRESSIONS.items()}
EXTRA_FOR.update(confused=('question',), think=('question',), excited=('sparkles',), surprised=('sweat',), happy=('blush',),
                 wink=('blush',), angry=('vein',))
# blush and tears need to know where the face is, which an uploaded picture doesn't tell us
EXTRA_FOR = {k: tuple(e for e in v if e not in ('blush', 'tears')) for k, v in EXTRA_FOR.items()}


# ------------------------------------------------------------------ storage
def _safe_id(cid):
    return cid if isinstance(cid, str) and re.fullmatch(r'[a-f0-9]{10}', cid) else None


def list_characters():
    out = []
    if os.path.isdir(CHAR_DIR):
        for cid in sorted(os.listdir(CHAR_DIR)):
            meta = os.path.join(CHAR_DIR, cid, 'meta.json')
            if _safe_id(cid) and os.path.exists(meta):
                with open(meta, encoding='utf-8') as f:
                    m = json.load(f)
                m['id'] = cid
                m['slots'] = [s for s in SLOTS if os.path.exists(os.path.join(CHAR_DIR, cid, s + '.png'))]
                out.append(m)
    return sorted(out, key=lambda m: -m.get('created', 0))


def remove_background(img, tolerance=38):
    """Makes a plain background transparent: flood-fills from the corners, so the character's own matching colours stay."""
    img = img.convert('RGBA')
    a = img.getchannel('A')
    if a.getextrema()[0] < 250:      # already has transparency
        return img
    rgb = img.convert('RGB')
    w, h = rgb.size
    marker = (255, 0, 255)
    work = rgb.copy()
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0)):
        if work.getpixel((x, y)) != marker:
            ImageDraw.floodfill(work, (x, y), marker, thresh=tolerance)
    mask = Image.eval(Image.merge('RGB', [work.getchannel(c).point(lambda v, t=t: 255 if v == t else 0)
                                          for c, t in zip('RGB', marker)]).convert('L'), lambda v: 255 if v == 255 else 0)
    alpha = Image.eval(mask, lambda v: 0 if v else 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    img.putalpha(alpha)
    return img


def save_character(name, files):
    """files: {slot: bytes}. The idle picture is required. Returns the new character's id."""
    if 'idle' not in files:
        raise ValueError('Add the main picture of your character first.')
    cid = uuid.uuid4().hex[:10]
    d = os.path.join(CHAR_DIR, cid)
    os.makedirs(d, exist_ok=True)
    try:
        base = None
        for slot in SLOTS:
            if slot not in files:
                continue
            im = Image.open(io.BytesIO(files[slot]))
            im.load()
            im = remove_background(im)
            if base is None:
                if max(im.size) > MAX_SIDE:
                    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                base = im.size
            elif im.size != base:
                im = im.resize(base, Image.LANCZOS)
            if not im.getchannel('A').getbbox():
                raise ValueError(f'The {slot} picture came out empty after removing the background.')
            im.save(os.path.join(d, slot + '.png'))
        with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(name=(name or 'My character').strip()[:40], created=time.time()), f)
    except Exception:
        for fn in os.listdir(d):
            os.remove(os.path.join(d, fn))
        os.rmdir(d)
        raise
    return cid


def delete_character(cid):
    cid = _safe_id(cid)
    d = os.path.join(CHAR_DIR, cid) if cid else None
    if d and os.path.isdir(d):
        for fn in os.listdir(d):
            os.remove(os.path.join(d, fn))
        os.rmdir(d)


def exists(cid):
    cid = _safe_id(cid)
    return bool(cid) and os.path.exists(os.path.join(CHAR_DIR, cid, 'idle.png'))


# ------------------------------------------------------------------ the puppet
class Puppet:
    """Same interface as rig.Rig: paste_body / paste_head / paste_front."""
    BOX_W, BOX_H, BOTTOM = 760, 1010, 1100

    def __init__(self, cid, k, accent=(10, 140, 255)):
        cid = _safe_id(cid)
        self.k = k
        self.accent = accent
        d = os.path.join(CHAR_DIR, cid or '')
        imgs = {}
        for slot in SLOTS:
            p = os.path.join(d, slot + '.png')
            if os.path.exists(p):
                imgs[slot] = Image.open(p).convert('RGBA')
        if 'idle' not in imgs:
            raise ValueError('This character is missing. Pick another one on the Character card.')
        box = None
        for im in imgs.values():
            b = im.getchannel('A').getbbox()
            if b:
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        w, h = box[2] - box[0], box[3] - box[1]
        s = min(self.BOX_W * k / w, self.BOX_H * k / h)
        self.size = (max(1, round(w * s)), max(1, round(h * s)))
        self.sprites = {slot: im.crop(box).resize(self.size, Image.LANCZOS) for slot, im in imgs.items()}
        self.shadow = self._shadow()

    def _shadow(self):
        w = int(self.size[0] * 0.8)
        h = max(4, int(w * 0.12))
        m = Image.new('L', (w + 40, h + 40), 0)
        ImageDraw.Draw(m).ellipse([20, 20, w + 20, h + 20], fill=110)
        m = m.filter(ImageFilter.GaussianBlur(12))
        sh = Image.new('RGBA', m.size, (0, 0, 0, 255))
        sh.putalpha(m)
        return sh

    def _pick(self, st):
        if st.get('open', 1.0) < 0.3 and 'blink' in self.sprites:
            return self.sprites['blink']
        if st.get('glow', 0.25) > 0.42 and 'talk' in self.sprites:
            return self.sprites['talk']
        return self.sprites['idle']

    def paste_body(self, frame, ox, oy, st):
        k = self.k
        amp = max(0.0, (st.get('glow', 0.25) - 0.25) / 0.75)
        spr = self._pick(st)
        sy = 1 + 0.045 * amp - 0.025 * st.get('shrug', 0)
        sx = 1 - 0.5 * (sy - 1)
        w, h = self.size
        if abs(sy - 1) > 0.004:
            spr = spr.resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.BILINEAR)
        tilt = st.get('tilt', 0.0) * 0.6
        bx = ox + 500 * k + (st.get('dx', 0) + st.get('head_dx', 0) * 0.6) * k
        by = oy + self.BOTTOM * k + (st.get('dy', 0) + st.get('head_dy', 0) * 0.5) * k
        lift = max(0.0, -st.get('dy', 0) - 8) * k
        sw = self.shadow
        frame.paste(sw, (int(bx - sw.width / 2), int(oy + self.BOTTOM * k - sw.height * 0.6)), sw)
        if abs(tilt) > 0.6:
            pad = int(spr.height * 0.08)
            big = Image.new('RGBA', (spr.width + 2 * pad, spr.height + pad), (0, 0, 0, 0))
            big.paste(spr, (pad, 0))
            spr = big.rotate(tilt, resample=Image.BILINEAR, center=(big.width / 2, spr.height), expand=False)
        frame.paste(spr, (int(bx - spr.width / 2), int(by - spr.height - lift * 0)), spr)
        self._last = (bx, by - spr.height, spr.width)

    def paste_head(self, frame, ox, oy, st, t):
        extras = EXTRA_FOR.get(st.get('emotion', 'normal'), ())
        if not extras or not getattr(self, '_last', None):
            return
        cx, top, w = self._last
        s = w / 700.0
        T = lambda x, y: (cx + (x - 500) * s, top + (y - 330) * s * 0.9)
        rig.draw_extras(frame, T, s, extras, self.accent, t)

    def paste_front(self, frame, ox, oy, st):
        pass


def preview(cid, size=300, bg=(14, 22, 48)):
    k = size / 760.0
    p = Puppet(cid, k)
    W, H = int(1000 * k), int(1100 * k)
    img = Image.new('RGB', (W, H), bg)
    p.paste_body(img, 0, 0, dict(glow=0.25))
    return img
