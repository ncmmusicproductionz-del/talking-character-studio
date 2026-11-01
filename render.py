"""Frame renderer: the character in a procedurally generated set, with camera moves, captions and music."""
import math
import multiprocessing as mp
import os
import random
import subprocess
from bisect import bisect_right

from PIL import Image, ImageChops, ImageDraw, ImageFilter

import motion
import overlays as ovl
import puppet
import rig
import sets
from scriptparse import split_caption_chunks
from speech import FFMPEG, NO_WINDOW

SS = 2
CAPTION_STYLES = ('bold', 'box', 'minimal', 'off')
SHOT_ZOOM = {'wide': 1.0, 'medium': 1.17, 'close': 1.36}
SHOT_FOCUS = {'wide': 0.0, 'medium': 0.6, 'close': 0.85}


def font(px, kind='bold'):
    return sets.font(px, kind)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def pop(x):
    x = max(0.0, min(1.0, x))
    return 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2


def lerp(a, b, w):
    return a + (b - a) * w


# ----------------------------------------------------------------------------------------- config

def build_config(sentences, analysis, W, H, fps, blocks, seconds=None, caption_style='bold', camera='dynamic',
                 pictures=None, show_chapters=True, character=None, clips=None, show_overlays=True):
    """blocks: list of dict(idx=[sentence indexes], theme, seed, title)."""
    dur = analysis['duration']
    portrait = H > W
    maxw = 6 if portrait else 9
    chunks = []
    for s in sentences:
        parts = split_caption_chunks(s['tokens'], maxw)
        wt = s.get('word_times')
        if wt and len(wt) == len(s['tokens']):
            # exact timings from the voice: every caption word lights up when it is said
            k = 0
            for p in parts:
                words = []
                for w, hl in p:
                    ws, we = wt[k]
                    k += 1
                    words.append(dict(w=w, hl=hl, s=ws, e=we))
                chunks.append(dict(start=words[0]['s'] - 0.04, end=words[-1]['e'], words=words))
            continue
        lens = [max(sum(len(w) + 1 for w, _ in p), 1) for p in parts]
        tot = float(sum(lens))
        span = max(s['end'] - s['start'], 0.3)
        acc = 0.0
        for p, ln in zip(parts, lens):
            a = s['start'] + span * acc / tot
            acc += ln
            b = s['start'] + span * acc / tot
            wl = [len(w) + 1 for w, _ in p]
            tw = float(sum(wl)) or 1.0
            words, acc2 = [], 0.0
            for (w, hl), l in zip(p, wl):
                ws = a + (b - a) * acc2 / tw
                acc2 += l
                words.append(dict(w=w, hl=hl, s=ws, e=a + (b - a) * acc2 / tw))
            chunks.append(dict(start=a, end=b, words=words))

    chunks.sort(key=lambda c: c['start'])
    for a, b in zip(chunks, chunks[1:]):
        if 0 < b['start'] - a['end'] < 0.7:     # keep a caption up through short pauses instead of flickering off
            a['end'] = b['start']
        a['end'] = min(a['end'], b['start'])

    out_blocks, shots = [], []
    kinds = ['wide', 'medium', 'close', 'medium']
    for bi, blk in enumerate(blocks):
        idx = blk['idx']
        start = 0.0 if bi == 0 else sentences[idx[0]]['start']
        end = sentences[idx[-1]]['end']
        out_blocks.append(dict(start=start, end=end, theme=blk['theme'], seed=blk['seed'], title=blk.get('title', ''),
                               stage=blk.get('stage', 'room')))
        shots.append(dict(start=start, kind='wide', block=bi, punch=False))
        if camera != 'dynamic':
            continue
        n, count = 0, 0
        for si in idx[1:]:
            s = sentences[si]
            count += 1
            if count >= 2 or (s['end'] - s['start']) > 7:
                n += 1
                count = 0
                shots.append(dict(start=s['start'], kind=kinds[n % len(kinds)], block=bi,
                                  punch=s['spoken'].rstrip('"\') ').endswith('!')))

    ovs = ovl.find_overlays(sentences) if show_overlays else []
    beats = sorted(w['s'] for c in chunks for w in c['words'] if w['hl'])

    rnd = random.Random(7)
    blinks, t = [], 1.2
    while t < dur + 1:
        blinks.append(t)
        t += rnd.uniform(2.2, 4.8)
    total = dur + 0.6
    if seconds:
        total = min(total, seconds)
    return dict(
        W=W, H=H, fps=fps, n_frames=max(1, int(total * fps)), duration=total, env=analysis['env'],
        sentences=[dict(start=s['start'], end=s['end'], pose=s['pose'], emotion=s['emotion'], idea=s['idea'],
                        action=s.get('action'), chapter=s['chapter'] if show_chapters else None) for s in sentences],
        character=character or dict(mode='classic'),
        chunks=chunks, blinks=blinks, caption_style=caption_style if caption_style in CAPTION_STYLES else 'bold',
        camera=camera, blocks=out_blocks, shots=shots, pictures=pictures or [], clips=clips or [], overlays=ovs, beats=beats)


# ----------------------------------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W, self.H, self.fps = cfg['W'], cfg['H'], cfg['fps']
        self.env = cfg['env']
        self.sent = cfg['sentences']
        self.starts = [s['start'] for s in self.sent]
        self.chunks = cfg['chunks']
        self.cstarts = [c['start'] for c in self.chunks]
        self.blinks = cfg['blinks']
        self.blocks = cfg['blocks'] or [dict(start=0, end=1e9, theme='studio', seed=1, title='')]
        self.bstarts = [b['start'] for b in self.blocks]
        self.shots = cfg['shots']
        self.shstarts = [s['start'] for s in self.shots]
        self.pictures = cfg.get('pictures') or []
        self.pstarts = [p['start'] for p in self.pictures]
        self.vclips = cfg.get('clips') or []
        self.overlays = cfg.get('overlays') or []
        self.ostarts = [o['start'] for o in self.overlays]
        self.beats = cfg.get('beats') or []
        self.card_cache = {}
        self.vframe_cache = {}
        self.bubble_cache = {}
        self.style = cfg.get('caption_style', 'bold')
        L = sets.layout_for(self.W, self.H)
        self.L = L
        self.portrait = L['portrait']
        self.k, self.cx, self.cy = L['k'], L['cx'], L['cy']
        self.S = SS * self.k
        self.character = cfg.get('character') or dict(mode='classic')
        self.rigs = {}
        self.laptop = self._build_laptop()
        self.bulb = self._build_bulb()
        self.black = Image.new('RGB', (self.W, self.H), (0, 0, 0))
        self.set_cache = {}
        self.pic_cache = {}
        self.text_cache = {}

    # -------------------------------------------------------------------- static pieces
    def _build_laptop(self):
        k = self.k
        w, h = int(430 * k), int(260 * k)
        S = 2
        im = Image.new('RGBA', (w * S, (h + int(26 * k)) * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w * S - 1, h * S], radius=int(26 * k * S), fill=(36, 38, 52), outline=(8, 70, 150), width=max(1, int(6 * k * S)))
        d.rectangle([int(10 * k * S), h * S - int(4 * k * S), w * S - int(10 * k * S), h * S + int(20 * k * S)], fill=(26, 28, 38))
        bx, by, bs = w * S // 2, h * S // 2, int(62 * k * S)
        d.rounded_rectangle([bx - bs, by - int(bs * 0.72), bx + bs, by + int(bs * 0.72)], radius=max(1, int(bs * 0.35)), fill=(10, 140, 255))
        d.polygon([(bx - bs * 0.22, by - bs * 0.34), (bx - bs * 0.22, by + bs * 0.34), (bx + bs * 0.38, by)], fill=(255, 255, 255))
        return im.resize((max(1, w), max(1, h + int(26 * k))), Image.LANCZOS)

    def _build_bulb(self):
        s = max(8, int(150 * self.k))
        im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = s
        for a in range(0, 360, 40):
            r0, r1 = s * 0.62, s * 0.84
            d.line([c + math.cos(math.radians(a)) * r0, c + math.sin(math.radians(a)) * r0 * 0.95,
                    c + math.cos(math.radians(a)) * r1, c + math.sin(math.radians(a)) * r1 * 0.95], fill=(255, 220, 90), width=max(3, int(s * 0.06)))
        d.ellipse([c - s * 0.42, c - s * 0.5, c + s * 0.42, c + s * 0.34], fill=(255, 214, 72))
        d.ellipse([c - s * 0.24, c - s * 0.34, c - s * 0.06, c - s * 0.12], fill=(255, 245, 200))
        d.rounded_rectangle([c - s * 0.2, c + s * 0.28, c + s * 0.2, c + s * 0.5], radius=max(1, int(s * 0.06)), fill=(150, 156, 170))
        return im.resize((s, s), Image.LANCZOS)

    # -------------------------------------------------------------------- sets and pictures
    def _set(self, bi):
        if bi in self.set_cache:
            return self.set_cache[bi]
        if len(self.set_cache) >= 2:
            self.set_cache.pop(next(iter(self.set_cache)))
        b = self.blocks[bi]
        S = sets.build_set(b['theme'], b['seed'], self.W, self.H, b.get('title', ''), stage=b.get('stage', 'room'))
        bbox = S.desk.getbbox() or (0, 0, 1, 1)
        entry = (S, S.desk.crop(bbox), (bbox[0], bbox[1]))
        self.set_cache[bi] = entry
        return entry

    def _pic(self, path, size):
        key = (path, size)
        if key in self.pic_cache:
            return self.pic_cache[key]
        if len(self.pic_cache) >= 3:
            self.pic_cache.pop(next(iter(self.pic_cache)))
        try:
            src = Image.open(path).convert('RGB')
        except Exception:
            src = Image.new('RGB', size, (20, 20, 30))
        tw, th = size
        s = max(tw / src.width, th / src.height)
        src = src.resize((max(tw, int(src.width * s + 0.5)), max(th, int(src.height * s + 0.5))), Image.LANCZOS)
        l, t = (src.width - tw) // 2, (src.height - th) // 2
        img = src.crop((l, t, l + tw, t + th))
        self.pic_cache[key] = img
        return img

    def _pic_frame(self, pi, t, pw, ph):
        p = self.pictures[pi]
        big = self._pic(p['path'], (int(pw * 1.14), int(ph * 1.14)))
        prog = max(0.0, min(1.0, (t - p['start']) / max(p['end'] - p['start'], 1.0)))
        z = 1.0 + 0.11 * prog
        cw, chh = big.width / z, big.height / z
        dr = 1 if pi % 2 == 0 else -1
        cxp = big.width / 2 + dr * (big.width - cw) * 0.45 * (2 * prog - 1)
        x0 = max(0, min(big.width - cw, cxp - cw / 2))
        y0 = (big.height - chh) / 2
        return big.resize((pw, ph), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + chh))

    # -------------------------------------------------------------------- footage
    def _clip_at(self, t, full, tail=0.0):
        for c in self.vclips:
            if c['full'] == full and c['start'] <= t < c['end'] + tail:
                return c
        return None

    def _clip_frame(self, c, t, size=None):
        n = max(1, c['frames'])
        idx = int(max(0.0, t - c['start']) * self.fps) % n + 1
        key = (c['dir'], idx, size)
        if key in self.vframe_cache:
            return self.vframe_cache[key]
        if len(self.vframe_cache) > 6:
            self.vframe_cache.pop(next(iter(self.vframe_cache)))
        try:
            img = Image.open(os.path.join(c['dir'], '%05d.jpg' % idx)).convert('RGB')
        except Exception:
            img = Image.new('RGB', size or (self.W, self.H), (10, 12, 20))
        if size and img.size != size:
            sc = max(size[0] / img.width, size[1] / img.height)
            img = img.resize((max(size[0], round(img.width * sc)), max(size[1], round(img.height * sc))), Image.BILINEAR)
            l, tp = (img.width - size[0]) // 2, (img.height - size[1]) // 2
            img = img.crop((l, tp, l + size[0], tp + size[1]))
        self.vframe_cache[key] = img
        return img

    def _draw_panel_clip(self, frame, S, t):
        c = self._clip_at(t, False)
        if not c:
            return False
        x0, y0, x1, y1 = [int(v) for v in S.panel]
        pw, ph = x1 - x0, y1 - y0
        if pw < 4 or ph < 4:
            return False
        cur = self._clip_frame(c, t, (pw, ph))
        local = t - c['start']
        if local < 0.4:
            cur = Image.blend(frame.crop((x0, y0, x1, y1)), cur, ease(local / 0.4))
        frame.paste(cur, (x0, y0))
        return True

    def _bubble_parts(self, D, accent):
        key = (D, accent)
        if key not in self.bubble_cache:
            SSB = 3
            m = Image.new('L', (D * SSB, D * SSB), 0)
            ImageDraw.Draw(m).ellipse([0, 0, D * SSB - 1, D * SSB - 1], fill=255)
            mask = m.resize((D, D), Image.LANCZOS)
            pad = max(6, D // 14)
            ring = Image.new('RGBA', ((D + 2 * pad) * SSB,) * 2, (0, 0, 0, 0))
            rd = ImageDraw.Draw(ring)
            rd.ellipse([pad * SSB * 0.4, pad * SSB * 0.9, (D + pad * 1.6) * SSB, (D + pad * 2.1) * SSB], fill=(0, 0, 0, 120))
            ring = ring.filter(ImageFilter.GaussianBlur(pad * SSB * 0.35))
            rd = ImageDraw.Draw(ring)
            w = max(2, D // 40) * SSB
            rd.ellipse([pad * SSB - w, pad * SSB - w, (pad + D) * SSB + w, (pad + D) * SSB + w], outline=accent + (255,), width=w)
            ring = ring.resize((D + 2 * pad,) * 2, Image.LANCZOS)
            self.bubble_cache[key] = (mask, ring, pad)
        return self.bubble_cache[key]

    def _clip_alpha(self, c, t):
        local, after = t - c['start'], t - c['end']
        return ease(local / 0.3) if after < 0 else 1 - ease(after / 0.3)

    def _inside_layout(self):
        if self.portrait:
            ko = 0.62 * self.W / 1000.0
            return ko, self.W - 1000 * ko * 0.80, self.H - 1100 * ko + 230 * ko
        ko = 0.80 * self.H / 1100.0
        return ko, self.W - 1000 * ko * 0.86, self.H - 1100 * ko + 120 * ko

    def _clip_mood(self, c, t, img):
        """Average colour of the footage (refreshed twice a second), used to light the character like the scene."""
        key = ('mood', c['dir'], int((t - c['start']) * 2))
        if key not in self.vframe_cache:
            self.vframe_cache[key] = img.resize((1, 1), Image.BOX).getpixel((0, 0))
        return self.vframe_cache[key]

    def _inside(self, frame, c, t, i, bi, accent):
        """Draws the character standing in the footage: lit by the footage's colours, with a rim light and a soft
        shadow, sliding in and out, turned towards the action and presenting it."""
        ko, ox, oy = self._inside_layout()
        local, after = t - c['start'], t - c['end']
        slide = (1 - ease(local / 0.45)) if after < 0 else ease(after / 0.3)
        if slide >= 0.999:
            return frame
        R = self._rig(bi, k=ko, accent=accent)
        si = bisect_right(self.starts, t) - 1
        amp = self.env[i] if i < len(self.env) else 0.0
        st = self._state(t, i, si, amp, c, 'left')
        bw, bh = int(1000 * ko), int(1100 * ko)
        layer = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        R.paste_body(layer, 0, 0, st)
        R.paste_head(layer, 0, 0, st, t)
        R.paste_front(layer, 0, 0, st)
        mood = self._clip_mood(c, t, frame)
        alpha = layer.getchannel('A')
        lit = Image.blend(layer.convert('RGB'), Image.new('RGB', layer.size, mood), 0.14)
        rim = ImageChops.subtract(alpha, alpha.filter(ImageFilter.MinFilter(7))).filter(ImageFilter.GaussianBlur(2))
        rim_col = tuple(min(255, int(v * 0.6 + 120)) for v in mood)
        lit.paste(Image.new('RGB', layer.size, rim_col), (0, 0), rim.point(lambda v: int(v * 0.55)))
        x = int(ox + slide * (self.W - ox + 40))
        y = int(oy)
        sh = self._inside_shadow(bw, bh)
        frame.paste(Image.new('RGB', sh.size, (0, 0, 0)), (x - int(bw * 0.15), y + int(bh * 0.05)), sh)
        frame.paste(lit, (x, y), alpha)
        return frame

    def _inside_shadow(self, bw, bh):
        key = ('ish', bw, bh)
        if key not in self.bubble_cache:
            m = sets.radial_mask((int(bw * 1.3), int(bh * 1.1))).point(lambda v: int(v * 0.55))
            self.bubble_cache[key] = m
        return self.bubble_cache[key]

    def _fullscreen_clip(self, frame, world, t, accent, i=0, bi=0):
        c = self._clip_at(t, True, tail=0.3)
        if not c:
            return frame
        if c.get('style', 'inside') == 'inside':
            a = self._clip_alpha(c, t)
            clip = self._clip_frame(c, t, (self.W, self.H))
            out = Image.blend(frame, clip, a) if (frame is not None and a < 0.999) else clip.copy()
            return self._inside(out, c, t, i, bi, accent)
        local, after = t - c['start'], t - c['end']
        a = ease(local / 0.3) if after < 0 else 1 - ease(after / 0.3)
        clip = self._clip_frame(c, t, (self.W, self.H))
        out = Image.blend(frame, clip, a) if a < 0.999 else clip.copy()
        # the character keeps presenting from a round bubble in the corner
        L, k = self.L, self.k
        D = int((0.36 if self.portrait else 0.27) * min(self.W, self.H) * (1 if self.portrait else 1.25))
        side = int(780 * k)
        cx, cy = L['char_x'], L['head_y'] + 70 * k
        box = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
        face = world.crop(box).resize((D, D), Image.BILINEAR)
        mask, ring, pad = self._bubble_parts(D, tuple(accent))
        sc = pop(local / 0.4) if after < 0 else max(0.0, 1 - ease(after / 0.3))
        if sc <= 0.02:
            return out
        if self.portrait:
            bx, by = self.W - D - int(0.05 * self.W), int(L['captions'][1] - D - 0.015 * self.H)
        else:
            bx, by = self.W - D - int(0.03 * self.W), self.H - D - int(0.05 * self.H)
        if sc < 0.999:
            d2 = max(4, int(D * sc))
            face, mask_s = face.resize((d2, d2), Image.BILINEAR), mask.resize((d2, d2), Image.BILINEAR)
            ring_s = ring.resize((d2 + 2 * int(pad * sc),) * 2, Image.BILINEAR)
            off = (D - d2) // 2
            out.paste(ring_s, (bx + off - int(pad * sc), by + off - int(pad * sc)), ring_s)
            out.paste(face, (bx + off, by + off), mask_s)
        else:
            out.paste(ring, (bx - pad, by - pad), ring)
            out.paste(face, (bx, by), mask)
        return out

    def _draw_picture(self, frame, S, t):
        if self._draw_panel_clip(frame, S, t):
            return
        if not self.pictures:
            return
        pi = bisect_right(self.pstarts, t) - 1
        if pi < 0 or t > self.pictures[pi]['end'] + 0.3:
            return
        x0, y0, x1, y1 = S.panel
        pw, ph = x1 - x0, y1 - y0
        if pw < 4 or ph < 4:
            return
        cur = self._pic_frame(pi, t, pw, ph)
        local = t - self.pictures[pi]['start']
        if local < 0.5:
            a = ease(local / 0.5)
            if pi > 0 and self.pictures[pi - 1]['end'] >= self.pictures[pi]['start'] - 0.2:
                under = self._pic_frame(pi - 1, t, pw, ph)
            else:
                under = frame.crop((x0, y0, x1, y1))
            cur = Image.blend(under, cur, a)
        frame.paste(cur, (x0, y0))

    # -------------------------------------------------------------------- character
    def style_for(self, bi):
        b = self.blocks[bi]
        c = self.character
        return rig.make_style(c.get('mode', 'classic'), b['theme'], b['seed'] + int(c.get('seed', 0)), c.get('custom'))

    def _rig(self, bi, k=None, accent=None):
        """The character for a scene: the built-in rig in that scene's style, or an uploaded character."""
        k = k or self.k
        c = self.character
        if c.get('mode') == 'image' and puppet.exists(c.get('image_id')):
            key = ('img', c['image_id'], round(k, 4))
            if key not in self.rigs:
                if len(self.rigs) >= 3:
                    self.rigs.pop(next(iter(self.rigs)))
                self.rigs[key] = puppet.Puppet(c['image_id'], k, accent or (10, 140, 255))
            return self.rigs[key]
        style = self.style_for(bi)
        key = rig.style_key(style) + (round(k, 4),)
        if key not in self.rigs:
            if len(self.rigs) >= 3:
                self.rigs.pop(next(iter(self.rigs)))
            self.rigs[key] = rig.Rig(style, k)
        return self.rigs[key]

    def _state(self, t, i, si, amp, clip=None, toward='left'):
        """Motion for this frame. While footage plays, the character turns to it and presents it for a couple of seconds."""
        sent = self.sent
        nxt = self.starts[si + 1] if 0 <= si + 1 < len(self.starts) else None
        if clip is not None and si >= 0:
            local = t - clip['start']
            s = sent[si]
            if local < 2.6 and s['pose'] in ('rest', 'explain', 'open', 'point', 'count', 'stop') and abs(s['start'] - clip['start']) < 0.6:
                sent = list(sent)
                sent[si] = dict(s, pose='point_up' if toward == 'up' else 'present')
        st = motion.motion_state(sent, si, t, amp, self._blink(t), nxt, allow_type=getattr(self, '_has_desk', True))
        b = bisect_right(self.beats, t + 0.04) - 1
        if b >= 0 and t - self.beats[b] < 0.35:
            # a small nod on every emphasised word, exactly when it is spoken
            st['head_dy'] += 10 * math.sin(max(0.0, t - self.beats[b] + 0.04) / 0.35 * math.pi)
        if clip is not None:
            local = t - clip['start']
            w = ease(local / 0.4) * (1 - ease((local - 2.4) / 0.5))
            lx, ly = st['look']
            st['look'] = (lx - 9 * w, ly - (9 * w if toward == 'up' else 0)) if toward in ('left', 'up') else (lx + 9 * w, ly)
            st['tilt'] += (4 if toward == 'left' else 0) * w
        return st

    def _blink(self, t):
        j = bisect_right(self.blinks, t) - 1
        if j < 0:
            return 0.0
        d = t - self.blinks[j]
        return 1 - abs(d - 0.1) / 0.1 if 0 <= d < 0.2 else 0.0

    def _world(self, t, i, bi):
        """Everything that the camera sees: set, picture, character, props, particles."""
        S, desk_crop, desk_pos = self._set(bi)
        k = self.k
        amp = self.env[i] if i < len(self.env) else 0.0
        si = bisect_right(self.starts, t) - 1
        frame = S.base.copy()
        self._draw_picture(frame, S, t)
        S.draw_back(frame, t)

        R = self._rig(bi, accent=S.accent)
        panel_clip = self._clip_at(t, False) if self.vclips else None
        self._has_desk = S.has_desk
        st = self._state(t, i, si, amp, panel_clip, 'up' if self.portrait else 'left')
        R.paste_body(frame, self.cx, self.cy, st)

        if S.has_desk:
            frame.paste(desk_crop, desk_pos, desk_crop)
            lx = int(self.cx + 500 * k - self.laptop.width / 2)
            frame.paste(self.laptop, (lx, int(S.desk_y - 235 * k)), self.laptop)
        S.draw_front(frame, t)
        R.paste_head(frame, self.cx, self.cy, st, t)
        R.paste_front(frame, self.cx, self.cy, st)

        if si >= 0:
            s = self.sent[si]
            local = t - s['start']
            if s['idea'] and 0 <= local < 1.9:
                sc = pop(local / 0.35) * (1 if local < 1.6 else (1.9 - local) / 0.3)
                size = max(8, int(self.bulb.width * max(sc, 0.05)))
                b = self.bulb.resize((size, size), Image.BILINEAR)
                frame.paste(b, (int(self.cx + 800 * k - size / 2), int(self.cy + 140 * k - size / 2 + 6 * math.sin(t * 5))), b)
            if s['emotion'] == 'think' and local >= 0:
                a = ease(local / 0.3)
                col = tuple(int(lerp(x, y, a)) for x, y in zip((20, 26, 50), S.accent))
                ImageDraw.Draw(frame).text((self.cx + 805 * k, self.cy + 210 * k + 8 * math.sin(t * 3)), '?',
                                           font=font(int(150 * k), 'black'), fill=col, anchor='mm')
        S.draw_room(frame, t)
        return frame, S

    # -------------------------------------------------------------------- camera
    def _camera(self, frame, t):
        if not self.shots or self.cfg.get('camera') != 'dynamic':
            return frame
        j = bisect_right(self.shstarts, t) - 1
        if j < 0:
            return frame
        sh = self.shots[j]
        nxt = self.shots[j + 1]['start'] if j + 1 < len(self.shots) else self.cfg['duration']
        prog = max(0.0, min(1.0, (t - sh['start']) / max(nxt - sh['start'], 1.0)))
        z = SHOT_ZOOM[sh['kind']] * (1 + 0.035 * prog)
        if sh.get('punch'):
            z *= 1 + 0.05 * ease((t - sh['start']) / 0.25)
        if z <= 1.001:
            return frame
        a = SHOT_FOCUS[sh['kind']]
        L = self.L
        fx = lerp(self.W / 2, L['char_x'], a)
        fy = lerp(self.H / 2, L['head_y'] + 40 * self.k, a)
        cw, chh = self.W / z, self.H / z
        x0 = max(0.0, min(self.W - cw, fx - cw / 2))
        y0 = max(0.0, min(self.H - chh, fy - chh / 2))
        return frame.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + chh))

    # -------------------------------------------------------------------- captions
    def _caption_zone(self):
        x0, y0, x1, y1 = self.L['captions']
        if self.portrait and getattr(self, '_inside_now', False):
            up = 0.30 * self.H          # the character stands at the bottom of the shot, so captions move above him
            return x0, y0 - up, x1, y1 - up
        return x0, y0, x1, y1

    def _text_img(self, key, builder):
        if key in self.text_cache:
            return self.text_cache[key]
        if len(self.text_cache) > 400:
            self.text_cache.clear()
        im = builder()
        self.text_cache[key] = im
        return im

    def _bold_groups(self, ci):
        key = ('groups', ci)
        if key in self.text_cache:
            return self.text_cache[key]
        words = self.chunks[ci]['words']
        limit = 15 if self.portrait else 20
        groups, cur, n = [], [], 0
        for wi, w in enumerate(words):
            if cur and n + len(w['w']) > limit:
                groups.append(cur)
                cur, n = [], 0
            cur.append(wi)
            n += len(w['w']) + 1
            if w['w'][-1:] in ',.;:!?' and len(cur) >= 1 and n > limit * 0.5:
                groups.append(cur)
                cur, n = [], 0
        if cur:
            groups.append(cur)
        self.text_cache[key] = groups
        return groups

    def _draw_bold(self, frame, t, ci, accent):
        c = self.chunks[ci]
        words = c['words']
        groups = self._bold_groups(ci)
        gi = 0
        for g_i, g in enumerate(groups):
            if t >= words[g[0]]['s'] - 0.01:
                gi = g_i
        g = groups[gi]
        active = -1
        for wi in g:
            if words[wi]['s'] <= t:
                active = wi
        zx0, zy0, zx1, zy1 = self._caption_zone()
        zone_w = zx1 - zx0
        px = int(self.W * 0.105) if self.portrait else int(self.H * 0.088)
        hl_col = (255, 214, 60) if accent == (10, 140, 255) else sets.light(accent, 0.25)

        def build():
            txts = [words[wi]['w'].upper() for wi in g]
            size = px
            f = font(size, 'impact')
            while True:
                space = f.getlength(' ')
                total = sum(f.getlength(x) for x in txts) + space * (len(txts) - 1)
                if total <= zone_w * 0.96 or size < 20:
                    break
                size = int(size * 0.9)
                f = font(size, 'impact')
            stroke = max(3, int(size * 0.09))
            w_img = int(total + stroke * 4 + 10)
            h_img = int(size * 1.35 + stroke * 4)
            im = Image.new('RGBA', (w_img, h_img), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            x = stroke * 2 + 5
            for j, (wi, tx) in enumerate(zip(g, txts)):
                col = hl_col if wi == active or words[wi]['hl'] and wi == active else (255, 255, 255)
                if wi == active:
                    col = hl_col
                d.text((x + 4, h_img / 2 + 5), tx, font=f, fill=(0, 0, 0, 140), anchor='lm')
                d.text((x, h_img / 2), tx, font=f, fill=col, anchor='lm', stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += f.getlength(tx) + space
            return im

        im = self._text_img(('bold', ci, gi, active, px), build)
        appear = t - words[g[0]]['s']
        sc = 0.82 + 0.18 * pop(appear / 0.16) if appear < 0.16 else 1.0
        if sc < 0.999:
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
        cxz = (zx0 + zx1) / 2
        cyz = (zy0 + zy1) / 2
        frame.paste(im, (int(cxz - im.width / 2), int(cyz - im.height / 2)), im)

    def _card(self, ci, accent, minimal):
        def build():
            toks = [(w['w'], w['hl']) for w in self.chunks[ci]['words']]
            zx0, zy0, zx1, zy1 = self._caption_zone()
            fsz = int(self.W * 0.066) if self.portrait else int(self.H * 0.064)
            if minimal:
                fsz = int(fsz * 0.92)
            f = font(fsz, 'bold')
            space = f.getlength(' ')
            pad = int(fsz * 0.5)
            maxw = (zx1 - zx0) - 2 * pad
            lines, cur, curw = [], [], 0.0
            for word, hl in toks:
                ww = f.getlength(word)
                if cur and curw + space + ww > maxw:
                    lines.append((cur, curw))
                    cur, curw = [], 0.0
                curw += (space if cur else 0) + ww
                cur.append((word, hl, ww))
            lines.append((cur, curw))
            lh = int(fsz * 1.24)
            w = int(max(l[1] for l in lines)) + 2 * pad
            h = lh * len(lines) + 2 * pad - int(fsz * 0.1)
            im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            if not minimal:
                d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(fsz * 0.42), fill=(7, 13, 34, 232), outline=accent, width=3)
            hl_col = sets.light(accent, 0.35)
            for n, (cur, cw) in enumerate(lines):
                x = (w - cw) / 2 if (self.portrait or minimal) else pad
                y = pad + lh * n + lh / 2 - fsz * 0.04
                for word, hl, ww in cur:
                    if minimal:
                        d.text((x, y), word, font=f, fill=hl_col if hl else (255, 255, 255), anchor='lm',
                               stroke_width=max(2, fsz // 14), stroke_fill=(0, 0, 0))
                    else:
                        d.text((x, y), word, font=f, fill=hl_col if hl else (255, 255, 255), anchor='lm')
                    x += ww + space
            return im
        return self._text_img(('card', ci, minimal, accent), build)

    def _draw_captions(self, frame, t, accent):
        if self.style == 'off' or not self.chunks:
            return
        ci = bisect_right(self.cstarts, t) - 1
        if ci < 0 or t > self.chunks[ci]['end'] + 0.25:
            return
        if self.style == 'bold':
            self._draw_bold(frame, t, ci, accent)
            return
        card = self._card(ci, accent, self.style == 'minimal')
        slide = (1 - ease((t - self.chunks[ci]['start']) / 0.14)) * 16
        zx0, zy0, zx1, zy1 = self._caption_zone()
        if self.portrait or self.style == 'minimal':
            x = int((zx0 + zx1) / 2 - card.width / 2)
        else:
            x = int(zx0)
        y = int((zy0 + zy1) / 2 - card.height / 2 + slide)
        frame.paste(card, (x, y), card)

    def _draw_chapter(self, frame, t, accent):
        si = bisect_right(self.starts, t) - 1
        if si < 0:
            return
        s = self.sent[si]
        local = t - s['start']
        if not s['chapter'] or local < 0 or local > 3.4:
            return
        f_in = ease(local / 0.35)
        f_out = ease((3.4 - local) / 0.35)
        a = min(f_in, f_out)

        def build():
            fsz = int(self.W * 0.045) if self.portrait else int(self.H * 0.042)
            f = font(fsz, 'black')
            tw = f.getlength(s['chapter'])
            pad = int(fsz * 0.55)
            w, h = int(tw + pad * 2.6 + fsz * 0.5), int(fsz * 1.9)
            im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(8, 12, 30, 235))
            d.rounded_rectangle([0, 0, int(fsz * 0.5 + pad), h - 1], radius=h // 2, fill=accent)
            d.text((fsz * 0.5 + pad * 1.6, h / 2), s['chapter'], font=f, fill=(255, 255, 255), anchor='lm')
            return im

        im = self._text_img(('chap', si, accent), build)
        m = im.getchannel('A').point(lambda v: int(v * a))
        L = self.L
        if self.portrait:
            x = int((self.W - im.width) / 2)
            y = int(L['panel'][3] + 0.012 * self.H)
        else:
            x = int(L['captions'][0] - (1 - f_in) * 60)
            y = int(L['panel'][3] + 0.012 * self.H)
        frame.paste(im, (x, y), m)

    # -------------------------------------------------------------------- frame
    def render_image(self, i):
        t = i / self.fps
        bi = max(0, bisect_right(self.bstarts, t) - 1)
        fc = self._clip_at(t, True, tail=0.3) if self.vclips else None
        self._inside_now = bool(fc and fc.get('style', 'inside') == 'inside' and self._clip_alpha(fc, t) > 0.5)
        if fc and fc.get('style', 'inside') == 'inside' and self._clip_alpha(fc, t) >= 0.999:
            S = self._set(bi)[0]          # the set is hidden by the footage: don't spend time drawing it
            frame = self._fullscreen_clip(None, None, t, S.accent, i, bi)
        else:
            world, S = self._world(t, i, bi)
            frame = self._camera(world, t)
            if fc:
                frame = self._fullscreen_clip(frame, world, t, S.accent, i, bi)
        if bi > 0:
            d = t - self.blocks[bi]['start']
            if 0 <= d < 0.22:
                frame = Image.blend(self.black, frame, ease(d / 0.22))
        if bi + 1 < len(self.blocks):
            d = self.blocks[bi + 1]['start'] - t
            if 0 <= d < 0.18:
                frame = Image.blend(self.black, frame, ease(d / 0.18))
        self._draw_overlay(frame, t, S.accent)
        self._draw_chapter(frame, t, S.accent)
        self._draw_captions(frame, t, S.accent)
        return frame

    def _draw_overlay(self, frame, t, accent):
        j = bisect_right(self.ostarts, t) - 1
        if j < 0:
            return
        o = self.overlays[j]
        if t > o['end'] + 0.3:
            return
        key = (j, tuple(accent))
        if key not in self.card_cache:
            if len(self.card_cache) > 4:
                self.card_cache.pop(next(iter(self.card_cache)))
            scale = (self.W / 1080.0) if self.portrait else (self.H / 1080.0 * 0.85)
            self.card_cache[key] = ovl.render_card(o, scale, accent)
        ovl.draw(frame, o, self.card_cache[key], t, self.L)

    def render(self, i):
        return self.render_image(i).tobytes()


def still_frame(theme, seed, title, W, H, character=None, stage='room'):
    """One frame of the character in a set (for the scene planner)."""
    cfg = dict(W=W, H=H, fps=24, n_frames=1, duration=1.0, env=[], sentences=[], chunks=[], blinks=[],
               caption_style='off', camera='static', blocks=[dict(start=0, end=10, theme=theme, seed=seed, title=title, stage=stage)],
               shots=[], pictures=[], character=character)
    return Renderer(cfg).render_image(12)


# ----------------------------------------------------------------------------------------- workers and encoding

_R = None
_ERR = None


def _init(cfg):
    global _R, _ERR
    try:
        _R = Renderer(cfg)
    except Exception:
        import traceback
        _ERR = traceback.format_exc()


def _work(i):
    if _R is None:
        raise RuntimeError('Renderer failed to start:\n' + (_ERR or 'unknown error'))
    return _R.render(i)


def render_video(cfg, audio_path, out_path, quality='final', progress=None, workers=None, music=None, live_path=None):
    """music: None or dict(path=..., volume=0..1). live_path: a JPEG updated now and then with the latest frame."""
    n = cfg['n_frames']
    W, H, fps = cfg['W'], cfg['H'], cfg['fps']
    dur = n / fps
    crf, preset = ('18', 'medium') if quality == 'final' else ('25', 'veryfast')
    cmd = [FFMPEG, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
           '-i', audio_path]
    if music and music.get('path') and os.path.exists(music['path']):
        vol = max(0.0, min(1.0, float(music.get('volume', 0.25))))
        cmd += ['-stream_loop', '-1', '-i', music['path'], '-filter_complex',
                f'[2:a]volume={vol:.3f},aformat=channel_layouts=stereo[m];[1:a]aformat=channel_layouts=stereo,asplit=2[v1][v2];'
                f'[m][v1]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[duck];'
                f'[v2][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,'
                f'afade=t=out:st={max(0.0, dur - 1.2):.2f}:d=1.2[aout]',
                '-map', '0:v', '-map', '[aout]']
    else:
        cmd += ['-map', '0:v', '-map', '1:a']
    cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', crf, '-preset', preset,
            '-c:a', 'aac', '-b:a', '192k', '-t', f'{dur:.3f}', '-movflags', '+faststart', out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=NO_WINDOW)
    workers = workers or max(1, min(6, (os.cpu_count() or 2) - 1))
    try:
        with mp.get_context('spawn').Pool(workers, initializer=_init, initargs=(cfg,)) as pool:
            for i, buf in enumerate(pool.imap(_work, range(n), chunksize=4)):
                p.stdin.write(buf)
                if progress and i % 12 == 0:
                    progress(i / n)
                if live_path and i % (fps * 2) == 0:
                    try:
                        im = Image.frombytes('RGB', (W, H), buf)
                        im.thumbnail((640, 640))
                        tmp = live_path + '.tmp.jpg'
                        im.save(tmp, 'JPEG', quality=80)
                        os.replace(tmp, live_path)
                    except Exception:
                        pass
    finally:
        try:
            p.stdin.close()
        except Exception:
            pass
        p.wait()
    if p.returncode != 0:
        raise RuntimeError('ffmpeg failed while encoding the video')
    if progress:
        progress(1.0)


def write_srt(cfg, path):
    def ts(x):
        h, rem = divmod(x, 3600)
        m, s = divmod(rem, 60)
        return f'{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}'
    with open(path, 'w', encoding='utf-8') as f:
        for n, c in enumerate(cfg['chunks'], 1):
            f.write(f"{n}\n{ts(c['start'])} --> {ts(c['end'])}\n{' '.join(w['w'] for w in c['words'])}\n\n")
