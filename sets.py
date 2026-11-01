"""Procedurally generated sets: the room behind the character, built from what the script is about.

Each set has a back wall with a pattern, a big feature behind the character (window, porthole, bookshelf,
evidence board, monitor wall, aquarium...), a framed panel for pictures or a title, side decorations,
desk props, lighting and small animations (blinking lights, flames, snow, fish, rain, dust).

The same theme + seed always gives the same set, so the scene planner preview matches the final video.
"""
import hashlib
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = r'C:\Windows\Fonts'
_fonts = {}


def font(px, kind='bold'):
    names = {
        'bold': ['segoeuib.ttf', 'arialbd.ttf'],
        'black': ['seguibl.ttf', 'ariblk.ttf', 'arialbd.ttf'],
        'impact': ['impact.ttf', 'ariblk.ttf', 'arialbd.ttf'],
        'serif': ['georgiab.ttf', 'arialbd.ttf'],
        'mono': ['consolab.ttf', 'consola.ttf', 'arialbd.ttf'],
        'hand': ['segoepr.ttf', 'comicbd.ttf', 'arialbd.ttf'],
    }[kind]
    key = (int(px), kind)
    if key not in _fonts:
        for n in names:
            p = os.path.join(FONT_DIR, n)
            if os.path.exists(p):
                _fonts[key] = ImageFont.truetype(p, max(6, int(px)))
                break
        else:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def dark(c, f):
    return tuple(max(0, int(v * f)) for v in c[:3])


def light(c, f):
    return tuple(min(255, int(v + (255 - v) * f)) for v in c[:3])


# ----------------------------------------------------------------------------------------- themes

THEMES = {
    'studio': dict(label='Night studio', icon='mic', accent=(10, 140, 255),
                   words=[]),
    'christmas': dict(label='Cosy Christmas', icon='tree', accent=(255, 196, 70),
                      words=['christmas', 'santa', 'xmas', 'december', 'reindeer', 'snow', 'winter', 'festive', 'gift', 'gifts',
                             'presents', 'elf', 'elves', 'carol', 'mistletoe', 'evergreen', 'evergreens', 'yule', 'nativity',
                             'holiday', 'holidays', 'ornament', 'tinsel', 'sleigh', 'stocking', 'eve']),
    'halloween': dict(label='Spooky night', icon='moon', accent=(255, 140, 40),
                      words=['halloween', 'ghost', 'ghosts', 'spooky', 'witch', 'witches', 'pumpkin', 'pumpkins', 'haunted',
                             'skeleton', 'vampire', 'samhain', 'october', 'monster', 'monsters', 'zombie', 'grave', 'graves',
                             'horror', 'curse', 'cursed', 'demon', 'spirit', 'spirits', 'trick', 'costume', 'creepy', 'dead']),
    'history': dict(label='Old library', icon='book', accent=(232, 186, 92),
                    words=['ancient', 'medieval', 'roman', 'romans', 'rome', 'empire', 'king', 'queen', 'castle', 'war', 'history',
                           'historians', 'historian', 'century', 'centuries', 'pharaoh', 'egypt', 'viking', 'vikings', 'knight',
                           'knights', 'greek', 'greeks', 'myth', 'myths', 'legend', 'legends', 'church', 'monks', 'pagan',
                           'tradition', 'traditions', 'origin', 'origins', 'record', 'records', 'play', 'emperor', 'kingdom']),
    'space': dict(label='Space deck', icon='planet', accent=(140, 120, 255),
                  words=['space', 'planet', 'planets', 'star', 'stars', 'galaxy', 'nasa', 'moon', 'mars', 'rocket', 'astronaut',
                         'universe', 'orbit', 'cosmic', 'alien', 'aliens', 'telescope', 'solar', 'comet', 'asteroid', 'gravity']),
    'tech': dict(label='Neon lab', icon='cpu', accent=(40, 230, 220),
                 words=['computer', 'computers', 'code', 'software', 'ai', 'robot', 'robots', 'internet', 'app', 'apps', 'phone',
                        'technology', 'tech', 'data', 'digital', 'hacker', 'programming', 'gaming', 'game', 'games', 'online',
                        'website', 'algorithm', 'chip', 'device', 'pc', 'console']),
    'nature': dict(label='Forest cabin', icon='leaf', accent=(120, 210, 110),
                   words=['forest', 'forests', 'animal', 'animals', 'river', 'mountain', 'mountains', 'nature', 'wildlife', 'plant',
                          'plants', 'flower', 'flowers', 'garden', 'weather', 'bird', 'birds', 'wolf', 'bear', 'insect', 'camping',
                          'hiking', 'woods', 'wild']),
    'ocean': dict(label='Ocean room', icon='wave', accent=(60, 200, 230),
                  words=['ocean', 'sea', 'seas', 'fish', 'shark', 'sharks', 'whale', 'whales', 'beach', 'ship', 'ships', 'sailor',
                         'sailors', 'pirate', 'pirates', 'underwater', 'coral', 'island', 'boat', 'titanic', 'navy', 'tide']),
    'mystery': dict(label='Detective office', icon='search', accent=(230, 170, 80),
                    words=['mystery', 'mysteries', 'secret', 'secrets', 'unsolved', 'detective', 'crime', 'crimes', 'case', 'clue',
                           'clues', 'conspiracy', 'hidden', 'murder', 'police', 'evidence', 'suspect', 'disappeared', 'missing',
                           'strange', 'truth', 'dark']),
}
THEME_ORDER = ['studio', 'christmas', 'halloween', 'history', 'space', 'tech', 'nature', 'ocean', 'mystery']


def detect_theme(text, fallback='studio'):
    """Scores the text against each theme's keywords; returns (best theme, scores)."""
    words = [w.strip(".,!?;:'\"()[]*-").lower() for w in text.split()]
    scores = {}
    for name, th in THEMES.items():
        bag = set(th['words'])
        scores[name] = sum(1 for w in words if w in bag)
    best = max(scores, key=lambda n: scores[n])
    if scores[best] < 2:
        return fallback, scores
    return best, scores


def seed_for(text, extra=0):
    return int(hashlib.sha1((text + '|' + str(extra)).encode('utf-8')).hexdigest()[:8], 16)


# ----------------------------------------------------------------------------------------- layout

def layout_for(W, H):
    """Where things go on screen. Shared with the renderer so sets and character line up."""
    portrait = H > W
    if portrait:
        k = W / 1000.0
        cx = 0.0
        cy = H - 1100 * k
    else:
        k = H / 1100.0 * 0.93
        cx = W * 0.70 - 500 * k
        cy = H - 1100 * k
    char_x = cx + 500 * k
    desk_y = cy + 905 * k
    if portrait:
        panel = (W * 0.05, H * 0.045, W * 0.95, H * 0.345)
        feature = (W * 0.13, H * 0.375, W * 0.87, H * 0.672)
        side_l = (0, H * 0.36, W * 0.13, desk_y)
        side_r = (W * 0.87, H * 0.36, W, desk_y)
        captions = (W * 0.05, H * 0.775, W * 0.95, H * 0.965)
    else:
        panel = (W * 0.035, H * 0.075, W * 0.465, H * 0.585)
        feature = (max(W * 0.5, char_x - W * 0.19), H * 0.06, min(W * 0.985, char_x + W * 0.19), H * 0.66)
        side_l = (W * 0.465, H * 0.05, feature[0], desk_y)
        side_r = (feature[2], H * 0.05, W, desk_y)
        captions = (W * 0.035, H * 0.62, W * 0.465, H * 0.95)
    return dict(W=W, H=H, portrait=portrait, k=k, cx=cx, cy=cy, char_x=char_x, head_y=cy + 390 * k, desk_y=desk_y,
                panel=panel, feature=feature, side_l=side_l, side_r=side_r, captions=captions,
                prop_l=(char_x - 395 * k, desk_y), prop_r=(char_x + 395 * k, desk_y))


# ----------------------------------------------------------------------------------------- drawing surface

_radial = None


def radial_mask(size):
    """Soft round falloff, 255 in the middle to 0 at the edge."""
    global _radial
    if _radial is None:
        m = Image.new('L', (256, 256), 0)
        d = ImageDraw.Draw(m)
        for i in range(128, 0, -2):
            v = int(255 * (1 - i / 128.0) ** 1.8)
            d.ellipse([128 - i, 128 - i, 128 + i, 128 + i], fill=v)
        _radial = m.filter(ImageFilter.GaussianBlur(2))
    return _radial.resize((max(1, int(size[0])), max(1, int(size[1]))), Image.BILINEAR)


class Canvas:
    """Supersampled RGBA canvas with simple shape helpers in 1x coordinates."""

    def __init__(self, W, H, ss=2, fill=(0, 0, 0, 0)):
        self.W, self.H, self.ss = W, H, ss
        self.im = Image.new('RGBA', (int(W * ss), int(H * ss)), fill)
        self.d = ImageDraw.Draw(self.im)

    def _b(self, x0, y0, x1, y1):
        s = self.ss
        return [x0 * s, y0 * s, max(x0, x1) * s, max(y0, y1) * s]

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=0, r=0):
        if r > 0:
            self.d.rounded_rectangle(self._b(x0, y0, x1, y1), radius=r * self.ss, fill=fill, outline=outline,
                                     width=int(w * self.ss) if outline else 0)
        else:
            self.d.rectangle(self._b(x0, y0, x1, y1), fill=fill, outline=outline, width=int(w * self.ss) if outline else 0)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, w=0):
        self.d.ellipse(self._b(cx - rx, cy - ry, cx + rx, cy + ry), fill=fill, outline=outline, width=int(w * self.ss) if outline else 0)

    def poly(self, pts, fill):
        s = self.ss
        self.d.polygon([(x * s, y * s) for x, y in pts], fill=fill)

    def line(self, pts, fill, w=2):
        s = self.ss
        self.d.line([(x * s, y * s) for x, y in pts], fill=fill, width=max(1, int(w * s)), joint='curve')

    def arc(self, cx, cy, rx, ry, a0, a1, fill, w=2):
        self.d.arc(self._b(cx - rx, cy - ry, cx + rx, cy + ry), a0, a1, fill=fill, width=max(1, int(w * s_or1(self))))

    def text(self, xy, txt, px, fill, kind='bold', anchor='mm'):
        self.d.text((xy[0] * self.ss, xy[1] * self.ss), txt, font=font(px * self.ss, kind), fill=fill, anchor=anchor)

    def text_width(self, txt, px, kind='bold'):
        return font(px * self.ss, kind).getlength(txt) / self.ss

    def _composite_mask(self, mask, X0, Y0, color):
        layer = Image.new('RGBA', mask.size, tuple(color[:3]) + (255,))
        layer.putalpha(mask)
        self.im.alpha_composite(layer, (int(X0), int(Y0)))

    def tpoly(self, pts, color, alpha, blur=0):
        s = self.ss
        xs = [p[0] * s for p in pts]
        ys = [p[1] * s for p in pts]
        pad = int(blur * s * 3) + 2
        X0, Y0 = max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad)
        X1, Y1 = min(self.im.width, int(max(xs)) + pad), min(self.im.height, int(max(ys)) + pad)
        if X1 - X0 < 2 or Y1 - Y0 < 2:
            return
        m = Image.new('L', (X1 - X0, Y1 - Y0), 0)
        ImageDraw.Draw(m).polygon([(x - X0, y - Y0) for x, y in zip(xs, ys)], fill=int(255 * alpha))
        if blur:
            m = m.filter(ImageFilter.GaussianBlur(blur * s))
        self._composite_mask(m, X0, Y0, color)

    def trect(self, x0, y0, x1, y1, color, alpha, blur=0):
        self.tpoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], color, alpha, blur)

    def tellipse(self, cx, cy, rx, ry, color, alpha, blur=0):
        s = self.ss
        pad = int(blur * s * 3) + 2
        X0, Y0 = max(0, int((cx - rx) * s) - pad), max(0, int((cy - ry) * s) - pad)
        X1, Y1 = min(self.im.width, int((cx + rx) * s) + pad), min(self.im.height, int((cy + ry) * s) + pad)
        if X1 - X0 < 2 or Y1 - Y0 < 2:
            return
        m = Image.new('L', (X1 - X0, Y1 - Y0), 0)
        ImageDraw.Draw(m).ellipse([(cx - rx) * s - X0, (cy - ry) * s - Y0, (cx + rx) * s - X0, (cy + ry) * s - Y0], fill=int(255 * alpha))
        if blur:
            m = m.filter(ImageFilter.GaussianBlur(blur * s))
        self._composite_mask(m, X0, Y0, color)

    def glow(self, cx, cy, rx, ry, color, alpha):
        s = self.ss
        m = radial_mask((2 * rx * s, 2 * ry * s))
        if alpha < 1:
            m = m.point(lambda v: int(v * alpha))
        X0, Y0 = int((cx - rx) * s), int((cy - ry) * s)
        layer = Image.new('RGBA', m.size, tuple(color[:3]) + (255,))
        layer.putalpha(m)
        big = Image.new('RGBA', self.im.size, (0, 0, 0, 0))
        big.paste(layer, (X0, Y0))
        self.im.alpha_composite(big)

    def paste(self, img, x, y):
        s = self.ss
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS) if s != 1 else img
        self.im.alpha_composite(img, (int(x * s), int(y * s)))

    def result(self):
        if self.ss == 1:
            return self.im
        return self.im.resize((self.W, self.H), Image.LANCZOS)


def s_or1(c):
    return c.ss


# ----------------------------------------------------------------------------------------- walls

def wall(c, L, top, bottom, pattern, rnd, accent):
    W, H = L['W'], L['H']
    s = c.ss
    for y in range(0, int(H * s), 2):
        f = y / (H * s)
        c.d.line([(0, y), (W * s, y)], fill=mix(top, bottom, f) + (255,), width=2)
    line_col = dark(mix(top, bottom, 0.5), 0.72) + (255,)
    hi_col = light(mix(top, bottom, 0.5), 0.06) + (255,)
    if pattern == 'panels':
        step = W / (7 if not L['portrait'] else 4)
        x = step / 2
        while x < W:
            c.rect(x - 1.5, 0, x + 1.5, H, fill=line_col)
            c.rect(x + 1.5, 0, x + 3, H, fill=hi_col)
            x += step
        c.rect(0, H * 0.70, W, H * 0.71, fill=line_col)
    elif pattern == 'stripes':
        step = W / (16 if not L['portrait'] else 9)
        x = 0
        alt = dark(mix(top, bottom, 0.4), 0.88) + (255,)
        while x < W:
            c.rect(x, 0, x + step / 2, H, fill=None)
            c.trect(x, 0, x + step / 2, H, alt[:3], 0.35)
            x += step
    elif pattern == 'bricks':
        bh = H / (26 if not L['portrait'] else 40)
        bw = bh * 2.6
        row = 0
        y = 0
        while y < H:
            off = (bw / 2) if row % 2 else 0
            c.rect(0, y, W, y + 1.4, fill=line_col)
            x = -off
            while x < W:
                c.rect(x, y, x + 1.4, y + bh, fill=line_col)
                if rnd.random() < 0.25:
                    c.trect(x + 2, y + 2, x + bw - 2, y + bh - 2, (0, 0, 0), 0.10)
                x += bw
            y += bh
            row += 1
    elif pattern == 'stone':
        y = 0
        while y < H:
            bh = rnd.uniform(H * 0.05, H * 0.08) if not L['portrait'] else rnd.uniform(H * 0.03, H * 0.05)
            x = -rnd.uniform(0, 60)
            while x < W:
                bw = rnd.uniform(bh * 1.2, bh * 2.4)
                shade = rnd.uniform(0.85, 1.12)
                col = tuple(min(255, int(v * shade)) for v in mix(top, bottom, y / H))
                c.rect(x + 2, y + 2, x + bw - 2, y + bh - 2, fill=col + (255,), r=4)
                x += bw
            y += bh
    elif pattern == 'logs':
        lh = H / (14 if not L['portrait'] else 24)
        y = 0
        while y < H:
            c.rect(0, y, W, y + lh, fill=mix(top, bottom, y / H) + (255,), r=lh / 2)
            c.rect(0, y + lh * 0.15, W, y + lh * 0.22, fill=hi_col)
            c.rect(0, y + lh - 2, W, y + lh, fill=line_col)
            y += lh
    elif pattern == 'planks':
        ph = H / (20 if not L['portrait'] else 34)
        y = 0
        while y < H:
            c.rect(0, y, W, y + 1.5, fill=line_col)
            x = rnd.uniform(-200, 0)
            while x < W:
                c.rect(x, y, x + 1.5, y + ph, fill=line_col)
                x += rnd.uniform(W * 0.15, W * 0.35)
            y += ph
    elif pattern == 'metal':
        pw = W / (6 if not L['portrait'] else 3)
        ph = H / (4 if not L['portrait'] else 7)
        y = 0
        while y < H:
            x = 0
            while x < W:
                c.rect(x + 3, y + 3, x + pw - 3, y + ph - 3, outline=line_col, w=2, r=10)
                for (rx, ry) in ((x + 14, y + 14), (x + pw - 14, y + 14), (x + 14, y + ph - 14), (x + pw - 14, y + ph - 14)):
                    c.ellipse(rx, ry, 3, 3, fill=hi_col)
                x += pw
            y += ph
    elif pattern == 'grid':
        step = W / (24 if not L['portrait'] else 14)
        gc = accent
        x = 0
        while x < W:
            c.trect(x, 0, x + 1.2, H, gc, 0.10)
            x += step
        y = 0
        while y < H:
            c.trect(0, y, W, y + 1.2, gc, 0.10)
            y += step
    elif pattern == 'acoustic':
        size = W / (12 if not L['portrait'] else 7)
        y = H * 0.02
        row = 0
        while y < H * 0.75:
            x = (size / 2 if row % 2 else 0) + W * 0.01
            while x < W:
                pts = [(x + size * 0.5 * math.cos(math.radians(a)) + size * 0.5, y + size * 0.5 * math.sin(math.radians(a)) + size * 0.5)
                       for a in range(30, 390, 60)]
                c.poly(pts, fill=dark(mix(top, bottom, y / H), rnd.uniform(0.75, 0.95)) + (255,))
                x += size * 1.0
            y += size * 0.86
            row += 1


# ----------------------------------------------------------------------------------------- outside views

def view_image(kind, w, h, rnd, ss, accent=(10, 140, 255)):
    """Returns an RGBA picture of what you see through a window (size w x h in 1x units)."""
    c = Canvas(w, h, ss, (0, 0, 0, 255))

    def sky(top, bottom):
        for y in range(0, int(h * ss), 2):
            f = y / (h * ss)
            c.d.line([(0, y), (w * ss, y)], fill=mix(top, bottom, f) + (255,), width=2)

    def stars(n, area=1.0):
        for _ in range(n):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h * area)
            r = rnd.choice([0.8, 1.0, 1.3, 1.8])
            c.ellipse(x, y, r, r, fill=(255, 255, 255, rnd.randint(150, 255)))

    if kind == 'city_night':
        sky((10, 14, 40), (52, 36, 92))
        stars(int(w * h / 3000), 0.5)
        c.glow(w * 0.78, h * 0.2, h * 0.16, h * 0.16, (230, 230, 255), 0.5)
        c.ellipse(w * 0.78, h * 0.2, h * 0.055, h * 0.055, fill=(240, 240, 255, 255))
        for layer, col, lit in ((0, (40, 38, 82), 0.12), (1, (22, 22, 48), 0.25)):
            x = -10
            while x < w:
                bw = rnd.uniform(w * 0.06, w * 0.14)
                bh = rnd.uniform(h * (0.25 + layer * 0.1), h * (0.55 + layer * 0.15))
                top = h - bh
                c.rect(x, top, x + bw, h, fill=col + (255,))
                wx = x + 6
                while wx < x + bw - 8:
                    wy = top + 8
                    while wy < h - 6:
                        if rnd.random() < lit:
                            c.rect(wx, wy, wx + 4, wy + 6, fill=(255, 214, 120, 255) if rnd.random() < 0.8 else (140, 210, 255, 255))
                        wy += 12
                    wx += 9
                x += bw + rnd.uniform(-4, 6)
    elif kind == 'snow_night':
        sky((14, 24, 64), (60, 84, 140))
        stars(int(w * h / 2500), 0.45)
        c.glow(w * 0.25, h * 0.2, h * 0.15, h * 0.15, (235, 240, 255), 0.45)
        c.ellipse(w * 0.25, h * 0.2, h * 0.05, h * 0.05, fill=(245, 245, 255, 255))
        c.ellipse(w * 0.3, h * 1.05, w * 0.7, h * 0.42, fill=(170, 190, 225, 255))
        c.ellipse(w * 0.85, h * 1.1, w * 0.6, h * 0.45, fill=(200, 215, 240, 255))
        for _ in range(int(w / 22)):
            x = rnd.uniform(0, w)
            base = h * rnd.uniform(0.72, 0.95)
            th = rnd.uniform(h * 0.12, h * 0.26)
            tw = th * 0.42
            c.poly([(x, base - th), (x - tw / 2, base), (x + tw / 2, base)], fill=(18, 52, 48, 255))
            c.poly([(x, base - th), (x - tw * 0.22, base - th * 0.55), (x + tw * 0.22, base - th * 0.55)], fill=(230, 240, 255, 255))
        hx = w * rnd.uniform(0.45, 0.65)
        hy = h * 0.8
        c.rect(hx, hy, hx + w * 0.1, hy + h * 0.09, fill=(60, 36, 40, 255))
        c.poly([(hx - 6, hy), (hx + w * 0.05, hy - h * 0.07), (hx + w * 0.1 + 6, hy)], fill=(235, 242, 255, 255))
        c.rect(hx + w * 0.035, hy + h * 0.025, hx + w * 0.065, hy + h * 0.06, fill=(255, 205, 110, 255))
        for _ in range(int(w * h / 900)):
            c.ellipse(rnd.uniform(0, w), rnd.uniform(0, h), 1.2, 1.2, fill=(255, 255, 255, 200))
    elif kind == 'moon_hills':
        sky((14, 8, 30), (70, 30, 80))
        stars(int(w * h / 3500), 0.6)
        mx, my = w * 0.62, h * 0.33
        c.glow(mx, my, h * 0.34, h * 0.34, (255, 210, 140), 0.55)
        c.ellipse(mx, my, h * 0.14, h * 0.14, fill=(255, 232, 170, 255))
        c.ellipse(mx - h * 0.04, my - h * 0.03, h * 0.025, h * 0.02, fill=(235, 205, 140, 255))
        c.ellipse(mx + h * 0.05, my + h * 0.04, h * 0.02, h * 0.016, fill=(235, 205, 140, 255))
        c.ellipse(w * 0.2, h * 1.05, w * 0.6, h * 0.3, fill=(16, 8, 24, 255))
        c.ellipse(w * 0.9, h * 1.08, w * 0.55, h * 0.34, fill=(10, 4, 16, 255))
        tx, ty = w * 0.22, h * 0.82
        c.line([(tx, ty), (tx + 3, ty - h * 0.3)], (10, 4, 16, 255), 7)
        for i in range(7):
            a = math.radians(rnd.uniform(-160, -20))
            ln = rnd.uniform(h * 0.07, h * 0.16)
            sy = ty - h * rnd.uniform(0.12, 0.3)
            c.line([(tx + 2, sy), (tx + 2 + math.cos(a) * ln, sy + math.sin(a) * ln)], (10, 4, 16, 255), 3)
        for _ in range(3):
            bx, by = rnd.uniform(w * 0.3, w * 0.9), rnd.uniform(h * 0.1, h * 0.45)
            sz = rnd.uniform(6, 11)
            c.poly([(bx - sz, by - sz * 0.3), (bx - sz * 0.4, by), (bx, by - sz * 0.15), (bx + sz * 0.4, by), (bx + sz, by - sz * 0.3),
                    (bx + sz * 0.3, by + sz * 0.35), (bx, by + sz * 0.15), (bx - sz * 0.3, by + sz * 0.35)], fill=(8, 2, 12, 255))
        c.trect(0, h * 0.7, w, h, (120, 90, 150), 0.18, blur=10)
    elif kind == 'dusk_castle':
        sky((40, 30, 80), (250, 150, 90))
        c.glow(w * 0.7, h * 0.72, h * 0.4, h * 0.3, (255, 200, 120), 0.6)
        c.ellipse(w * 0.7, h * 0.72, h * 0.09, h * 0.09, fill=(255, 220, 150, 255))
        c.ellipse(w * 0.5, h * 1.15, w * 0.8, h * 0.45, fill=(42, 24, 40, 255))
        bx, by = w * 0.22, h * 0.72
        col = (36, 20, 36, 255)
        c.rect(bx, by - h * 0.14, bx + w * 0.3, by + h * 0.1, fill=col)
        for tx in (bx - w * 0.02, bx + w * 0.12, bx + w * 0.28):
            c.rect(tx, by - h * 0.26, tx + w * 0.05, by, fill=col)
            c.poly([(tx - 3, by - h * 0.26), (tx + w * 0.025, by - h * 0.34), (tx + w * 0.05 + 3, by - h * 0.26)], fill=col)
        x = bx
        while x < bx + w * 0.3:
            c.rect(x, by - h * 0.16, x + 6, by - h * 0.14, fill=col)
            x += 12
        for _ in range(4):
            px, py = rnd.uniform(w * 0.4, w * 0.9), rnd.uniform(h * 0.15, h * 0.4)
            c.line([(px - 7, py), (px, py + 3), (px + 7, py)], (40, 20, 40, 255), 2)
    elif kind == 'space':
        sky((2, 2, 10), (10, 6, 30))
        for col, cx, cy, r in (((120, 60, 200), 0.3, 0.4, 0.45), ((40, 120, 220), 0.75, 0.6, 0.4), ((200, 60, 140), 0.55, 0.2, 0.3)):
            c.glow(w * cx, h * cy, w * r, h * r, col, 0.35)
        stars(int(w * h / 900), 1.0)
        px, py, pr = w * 0.68, h * 0.58, min(w, h) * 0.26
        c.ellipse(px, py, pr, pr, fill=(200, 140, 90, 255))
        for i in range(5):
            yy = py - pr + (i + 0.5) * 2 * pr / 5
            c.tellipse(px, yy, pr * 0.98, pr * 0.07, (150, 90, 60), 0.5)
        c.tellipse(px - pr * 0.35, py - pr * 0.35, pr * 0.55, pr * 0.55, (255, 230, 200), 0.25, blur=pr * 0.15)
        c.tellipse(px + pr * 0.25, py + pr * 0.25, pr * 0.9, pr * 0.9, (0, 0, 0), 0.45, blur=pr * 0.2)
        c.d.arc(c._b(px - pr * 1.7, py - pr * 0.35, px + pr * 1.7, py + pr * 0.35), 160, 380, fill=(230, 200, 160, 255), width=int(5 * ss))
        c.ellipse(w * 0.18, h * 0.25, min(w, h) * 0.05, min(w, h) * 0.05, fill=(160, 180, 200, 255))
    elif kind == 'forest_day':
        sky((120, 190, 245), (200, 232, 250))
        c.glow(w * 0.8, h * 0.18, h * 0.25, h * 0.25, (255, 250, 210), 0.7)
        c.ellipse(w * 0.8, h * 0.18, h * 0.07, h * 0.07, fill=(255, 250, 220, 255))
        for i in range(3):
            cx = rnd.uniform(0, w)
            c.tellipse(cx, h * 0.25 + i * 10, w * 0.12, h * 0.04, (255, 255, 255), 0.85)
        c.poly([(0, h * 0.6), (w * 0.25, h * 0.3), (w * 0.5, h * 0.6)], fill=(130, 160, 190, 255))
        c.poly([(w * 0.35, h * 0.65), (w * 0.65, h * 0.25), (w * 0.95, h * 0.65)], fill=(110, 140, 175, 255))
        c.poly([(w * 0.6, h * 0.25 + h * 0.07), (w * 0.65, h * 0.25), (w * 0.7, h * 0.25 + h * 0.07)], fill=(250, 250, 255, 255))
        c.rect(0, h * 0.62, w, h, fill=(90, 150, 80, 255))
        for row, col in ((0.75, (50, 110, 60)), (0.95, (30, 80, 45))):
            x = -10
            while x < w + 10:
                th = rnd.uniform(h * 0.18, h * 0.3)
                tw = th * 0.45
                base = h * row
                c.poly([(x, base - th), (x - tw / 2, base), (x + tw / 2, base)], fill=col + (255,))
                x += tw * rnd.uniform(0.5, 0.8)
    elif kind == 'underwater':
        sky((20, 110, 170), (6, 30, 70))
        for i in range(6):
            x = w * (0.1 + i * 0.17)
            c.tpoly([(x, 0), (x + w * 0.06, 0), (x + w * 0.16, h), (x + w * 0.04, h)], (180, 230, 255), 0.10, blur=6)
        c.ellipse(w * 0.5, h * 1.08, w * 0.7, h * 0.2, fill=(190, 170, 120, 255))
        for _ in range(int(w / 40)):
            x = rnd.uniform(0, w)
            base = h * rnd.uniform(0.92, 1.0)
            hh = rnd.uniform(h * 0.12, h * 0.3)
            col = rnd.choice([(30, 140, 90), (60, 170, 110), (200, 80, 110), (240, 140, 80)])
            pts = []
            for j in range(9):
                f = j / 8
                pts.append((x + math.sin(f * 6 + x) * 6, base - hh * f))
            c.line(pts, col + (255,), rnd.uniform(4, 8))
        for _ in range(int(w * h / 1200)):
            c.ellipse(rnd.uniform(0, w), rnd.uniform(0, h), 1, 1, fill=(220, 240, 255, 120))
    elif kind == 'rain_city':
        sky((10, 20, 30), (30, 50, 64))
        x = -10
        while x < w:
            bw = rnd.uniform(w * 0.07, w * 0.15)
            bh = rnd.uniform(h * 0.4, h * 0.85)
            c.rect(x, h - bh, x + bw, h, fill=(14, 22, 30, 255))
            wx = x + 6
            while wx < x + bw - 6:
                wy = h - bh + 8
                while wy < h - 5:
                    if rnd.random() < 0.18:
                        c.rect(wx, wy, wx + 4, wy + 6, fill=(255, 200, 110, 255))
                    wy += 13
                wx += 10
            x += bw + 3
        for _ in range(int(w * h / 500)):
            rx, ry = rnd.uniform(0, w), rnd.uniform(0, h)
            c.line([(rx, ry), (rx - 3, ry + 14)], (150, 180, 200, 90), 1)
        c.trect(0, h * 0.6, w, h, (255, 190, 120), 0.08, blur=12)
    else:
        sky((20, 30, 60), (40, 60, 110))
    return c.result()


# ----------------------------------------------------------------------------------------- features (behind the character)

def window_feature(c, rect, view, frame_col, rnd, ss, accent, arched=False, mullions=True):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    fw = max(8, min(w, h) * 0.045)
    c.tellipse((x0 + x1) / 2, y1 + 6, w * 0.55, 18, (0, 0, 0), 0.35, blur=10)
    c.rect(x0 - fw, y0 - fw, x1 + fw, y1 + fw, fill=frame_col + (255,), r=fw * 0.6)
    img = view_image(view, int(w), int(h), rnd, ss, accent)
    mask = Image.new('L', img.size, 0)
    md = ImageDraw.Draw(mask)
    if arched:
        md.rectangle([0, h * 0.3, w, h], fill=255)
        md.ellipse([0, 0, w, h * 0.6], fill=255)
    else:
        md.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=255)
    img.putalpha(mask)
    c.paste(img, x0, y0)
    c.tpoly([(x0 + w * 0.05, y0), (x0 + w * 0.32, y0), (x0 + w * 0.12, y1), (x0, y1), (x0, y0 + h * 0.3)], (255, 255, 255), 0.06)
    if mullions:
        mc = dark(frame_col, 0.9) + (255,)
        c.rect((x0 + x1) / 2 - fw * 0.35, y0, (x0 + x1) / 2 + fw * 0.35, y1, fill=mc)
        c.rect(x0, y0 + h * 0.42 - fw * 0.3, x1, y0 + h * 0.42 + fw * 0.3, fill=mc)
    c.rect(x0 - fw * 1.6, y1 + fw * 0.6, x1 + fw * 1.6, y1 + fw * 1.6, fill=light(frame_col, 0.08) + (255,), r=3)
    return (x0, y0, x1, y1)


def porthole_feature(c, rect, view, rnd, ss, accent):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) * 0.48
    c.glow(cx, cy, r * 1.5, r * 1.5, accent, 0.35)
    c.ellipse(cx, cy, r * 1.14, r * 1.14, fill=(60, 66, 84, 255))
    c.ellipse(cx, cy, r * 1.06, r * 1.06, fill=(30, 34, 46, 255))
    img = view_image(view, int(2 * r), int(2 * r), rnd, ss, accent)
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, img.width - 1, img.height - 1], fill=255)
    img.putalpha(mask)
    c.paste(img, cx - r, cy - r)
    c.d.arc(c._b(cx - r, cy - r, cx + r, cy + r), 200, 250, fill=(255, 255, 255, 70), width=int(6 * ss))
    for a in range(0, 360, 30):
        ra = math.radians(a)
        c.ellipse(cx + math.cos(ra) * r * 1.1, cy + math.sin(ra) * r * 1.1, 4, 4, fill=(120, 128, 150, 255))
    c.d.ellipse(c._b(cx - r * 1.14, cy - r * 1.14, cx + r * 1.14, cy + r * 1.14), outline=accent + (255,), width=int(3 * ss))
    return (cx - r, cy - r, cx + r, cy + r)


def bookshelf(c, rect, rnd, wood=(92, 60, 36), book_cols=None, shelves=None):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    book_cols = book_cols or [(120, 40, 40), (40, 70, 110), (50, 90, 60), (140, 110, 50), (90, 50, 90), (170, 140, 100), (60, 50, 40)]
    c.rect(x0 - 10, y0 - 10, x1 + 10, y1 + 6, fill=dark(wood, 0.7) + (255,), r=4)
    c.rect(x0, y0, x1, y1, fill=dark(wood, 0.45) + (255,))
    n = shelves or max(2, int(h / 95))
    sh = h / n
    for i in range(n):
        base = y0 + (i + 1) * sh
        x = x0 + 4
        while x < x1 - 10:
            bw = rnd.uniform(7, 16)
            bh = rnd.uniform(sh * 0.55, sh * 0.85)
            col = rnd.choice(book_cols)
            if rnd.random() < 0.08:
                c.poly([(x, base - 8), (x + bh * 0.9, base - 8 - bh * 0.25), (x + bh * 0.9 + bw, base - 8 - bh * 0.25 + 3), (x + bw, base - 8)], fill=col + (255,))
                x += bh * 0.8
                continue
            if rnd.random() < 0.06:
                c.ellipse(x + 10, base - 14, 9, 9, fill=(200, 200, 210, 255))
                x += 24
                continue
            c.rect(x, base - 8 - bh, x + bw, base - 8, fill=col + (255,), r=1.5)
            c.rect(x + 1.5, base - 8 - bh * 0.8, x + bw - 1.5, base - 8 - bh * 0.74, fill=light(col, 0.35) + (255,))
            x += bw + rnd.uniform(0, 2)
        c.rect(x0 - 4, base - 8, x1 + 4, base, fill=wood + (255,))
        c.rect(x0 - 4, base - 8, x1 + 4, base - 6.5, fill=light(wood, 0.25) + (255,))
    return rect


def evidence_board(c, rect, rnd):
    x0, y0, x1, y1 = rect
    c.rect(x0 - 10, y0 - 10, x1 + 10, y1 + 10, fill=(70, 46, 30, 255), r=5)
    c.rect(x0, y0, x1, y1, fill=(176, 130, 86, 255))
    for _ in range(int((x1 - x0) * (y1 - y0) / 60)):
        c.ellipse(rnd.uniform(x0, x1), rnd.uniform(y0, y1), 1.2, 1.2, fill=(150, 108, 70, 255))
    pins = []
    for _ in range(7):
        w = rnd.uniform(60, 110)
        h = w * rnd.uniform(0.7, 1.2)
        x = rnd.uniform(x0 + 8, x1 - w - 8)
        y = rnd.uniform(y0 + 8, y1 - h - 8)
        kind = rnd.random()
        if kind < 0.45:
            c.rect(x, y, x + w, y + h, fill=(245, 242, 232, 255))
            c.rect(x + 6, y + 6, x + w - 6, y + h * 0.72, fill=(70, 80, 90, 255))
            c.ellipse(x + w / 2, y + h * 0.38, w * 0.16, w * 0.16, fill=(110, 120, 130, 255))
        elif kind < 0.8:
            col = rnd.choice([(250, 236, 140), (250, 200, 210), (190, 230, 250)])
            c.rect(x, y, x + w, y + w * 0.9, fill=col + (255,))
            for k in range(4):
                c.rect(x + 8, y + 14 + k * 12, x + w - 8 - rnd.uniform(0, 20), y + 16 + k * 12, fill=(80, 80, 90, 255))
        else:
            c.rect(x, y, x + w, y + h, fill=(240, 236, 220, 255))
            c.text((x + w / 2, y + h / 2), rnd.choice(['?', 'WHO?', '1888', 'X']), w * 0.3, (180, 30, 30, 255), 'hand')
        px, py = x + w / 2, y + 6
        pins.append((px, py))
        c.ellipse(px, py, 5, 5, fill=(200, 30, 30, 255))
    for i in range(len(pins) - 1):
        if rnd.random() < 0.8:
            c.line([pins[i], pins[i + 1]], (200, 20, 30, 255), 2)
    return rect


def monitor_wall(c, rect, rnd, accent):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    screens = []
    gap = w * 0.03
    sw = (w - gap * 2) / 3
    for i in range(3):
        sx = x0 + i * (sw + gap)
        sy = y0 + (h * 0.08 if i != 1 else 0)
        sh = h * (0.62 if i != 1 else 0.7)
        c.glow(sx + sw / 2, sy + sh / 2, sw * 0.8, sh * 0.8, accent, 0.25)
        c.rect(sx, sy, sx + sw, sy + sh, fill=(14, 16, 22, 255), r=8)
        inner = (sx + 8, sy + 8, sx + sw - 8, sy + sh - 8)
        c.rect(*inner, fill=(6, 12, 20, 255), r=4)
        screens.append(inner)
        if i == 1:
            cx = sx + sw / 2
            for k in range(14):
                v = rnd.uniform(0.2, 1.0)
                bw = (sw - 40) / 14
                c.rect(sx + 20 + k * bw, sy + sh * 0.85 - v * sh * 0.5, sx + 20 + k * bw + bw * 0.7, sy + sh * 0.85,
                       fill=mix(accent, (255, 80, 200), k / 14) + (255,))
            c.text((cx, sy + sh * 0.18), 'SYSTEM ONLINE', 14, accent + (255,), 'mono')
        c.rect(sx + sw / 2 - 6, sy + sh, sx + sw / 2 + 6, y1, fill=(30, 32, 40, 255))
    return screens


def aquarium_feature(c, rect, rnd, ss, accent):
    x0, y0, x1, y1 = rect
    c.rect(x0 - 12, y0 - 12, x1 + 12, y1 + 12, fill=(30, 40, 50, 255), r=10)
    img = view_image('underwater', int(x1 - x0), int(y1 - y0), rnd, ss, accent)
    c.paste(img, x0, y0)
    c.tpoly([(x0 + (x1 - x0) * 0.05, y0), (x0 + (x1 - x0) * 0.25, y0), (x0 + (x1 - x0) * 0.1, y1), (x0, y1)], (255, 255, 255), 0.06)
    c.rect(x0 - 12, y0 - 12, x1 + 12, y0 + 6, fill=(44, 56, 70, 255), r=6)
    return rect


def fireplace_feature(c, rect, rnd):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    fx0, fx1 = x0 + w * 0.08, x1 - w * 0.08
    fy0 = y0 + h * 0.35
    c.rect(fx0 - 16, fy0 - 26, fx1 + 16, fy0, fill=(120, 80, 54, 255), r=4)
    c.rect(fx0, fy0, fx1, y1 + 40, fill=(150, 70, 56, 255))
    by = fy0
    row = 0
    while by < y1 + 40:
        c.rect(fx0, by, fx1, by + 2, fill=(110, 50, 40, 255))
        bx = fx0 + (18 if row % 2 else 0)
        while bx < fx1:
            c.rect(bx, by, bx + 2, by + 20, fill=(110, 50, 40, 255))
            bx += 36
        by += 20
        row += 1
    ox0, ox1 = fx0 + (fx1 - fx0) * 0.18, fx1 - (fx1 - fx0) * 0.18
    oy0 = fy0 + h * 0.12
    c.rect(ox0, oy0, ox1, y1 + 40, fill=(20, 10, 10, 255), r=30)
    c.glow((ox0 + ox1) / 2, y1, (ox1 - ox0) * 0.6, h * 0.35, (255, 140, 40), 0.7)
    for i in range(3):
        lx = ox0 + (ox1 - ox0) * (0.25 + i * 0.25)
        c.rect(lx - 30, y1 - 6, lx + 30, y1 + 8, fill=(80, 46, 28, 255), r=6)
    return (ox0, oy0, ox1, y1)


# ----------------------------------------------------------------------------------------- props

def plant(c, x, base, s, rnd, pot=(200, 110, 70)):
    c.tellipse(x, base, 34 * s, 7 * s, (0, 0, 0), 0.35, blur=4 * s)
    c.poly([(x - 30 * s, base - 62 * s), (x + 30 * s, base - 62 * s), (x + 22 * s, base), (x - 22 * s, base)], fill=pot + (255,))
    c.rect(x - 34 * s, base - 70 * s, x + 34 * s, base - 58 * s, fill=light(pot, 0.12) + (255,), r=3 * s)
    for i in range(9):
        a = math.radians(-90 + rnd.uniform(-70, 70))
        ln = rnd.uniform(60, 110) * s
        ex, ey = x + math.cos(a) * ln, base - 64 * s + math.sin(a) * ln
        col = mix((40, 120, 60), (90, 180, 90), rnd.random())
        mx, my = (x + ex) / 2, (base - 64 * s + ey) / 2
        nx, ny = -(ey - (base - 64 * s)) * 0.18, (ex - x) * 0.18
        c.poly([(x, base - 64 * s), (mx + nx, my + ny), (ex, ey), (mx - nx, my - ny)], fill=col + (255,))


def mug(c, x, base, s, col=(230, 230, 236), steam=False):
    c.tellipse(x, base, 28 * s, 6 * s, (0, 0, 0), 0.35, blur=3 * s)
    c.rect(x - 22 * s, base - 50 * s, x + 22 * s, base, fill=col + (255,), r=6 * s)
    c.d.arc(c._b(x + 14 * s, base - 40 * s, x + 38 * s, base - 14 * s), -90, 90, fill=col + (255,), width=int(7 * s * c.ss))
    c.ellipse(x, base - 50 * s, 22 * s, 5 * s, fill=(70, 40, 24, 255))


def desk_lamp(c, x, base, s, col=(40, 44, 56), light_col=(255, 214, 140), on=True, flip=False):
    d = -1 if flip else 1
    c.ellipse(x, base - 4 * s, 36 * s, 8 * s, fill=col + (255,))
    c.line([(x, base - 6 * s), (x + d * 40 * s, base - 120 * s), (x + d * 100 * s, base - 150 * s)], col + (255,), 8 * s)
    hx, hy = x + d * 100 * s, base - 150 * s
    c.poly([(hx - 30 * s, hy - 10 * s), (hx + 30 * s, hy - 10 * s), (hx + 44 * s, hy + 26 * s), (hx - 44 * s, hy + 26 * s)], fill=col + (255,))
    if on:
        c.tpoly([(hx - 40 * s, hy + 26 * s), (hx + 40 * s, hy + 26 * s), (hx + 150 * s, base), (hx - 150 * s, base)], light_col, 0.12, blur=6 * s)
        c.ellipse(hx, hy + 26 * s, 36 * s, 6 * s, fill=light_col + (255,))
        c.glow(hx, base, 170 * s, 30 * s, light_col, 0.4)


def globe(c, x, base, s):
    c.rect(x - 34 * s, base - 8 * s, x + 34 * s, base, fill=(90, 60, 30, 255), r=3 * s)
    c.rect(x - 4 * s, base - 40 * s, x + 4 * s, base - 8 * s, fill=(110, 80, 40, 255))
    r = 52 * s
    gy = base - 40 * s - r
    c.ellipse(x, gy, r, r, fill=(70, 120, 160, 255))
    c.poly([(x - r * 0.5, gy - r * 0.4), (x - r * 0.1, gy - r * 0.6), (x + r * 0.2, gy - r * 0.2), (x - r * 0.2, gy + r * 0.1)], fill=(150, 170, 90, 255))
    c.poly([(x + r * 0.2, gy + r * 0.1), (x + r * 0.6, gy), (x + r * 0.5, gy + r * 0.5), (x + r * 0.15, gy + r * 0.45)], fill=(150, 170, 90, 255))
    c.d.arc(c._b(x - r * 1.15, gy - r * 1.15, x + r * 1.15, gy + r * 1.15), 120, 300, fill=(200, 160, 70, 255), width=int(5 * s * c.ss))


def candle(c, x, base, s, col=(240, 230, 210), height=70):
    c.rect(x - 30 * s, base - 8 * s, x + 30 * s, base, fill=(180, 150, 80, 255), r=4 * s)
    c.rect(x - 12 * s, base - (8 + height) * s, x + 12 * s, base - 8 * s, fill=col + (255,), r=3 * s)
    c.line([(x, base - (8 + height) * s), (x, base - (16 + height) * s)], (40, 30, 20, 255), 2 * s)
    return (x, base - (24 + height) * s)


def pumpkin(c, x, base, s):
    c.tellipse(x, base, 64 * s, 9 * s, (0, 0, 0), 0.4, blur=4 * s)
    for dx, rx in ((-34, 34), (34, 34), (-14, 34), (14, 34), (0, 36)):
        c.ellipse(x + dx * s, base - 42 * s, rx * s, 42 * s, fill=mix((230, 110, 20), (200, 80, 10), abs(dx) / 40) + (255,))
    c.rect(x - 5 * s, base - 96 * s, x + 6 * s, base - 80 * s, fill=(70, 90, 40, 255), r=2 * s)
    face = (40, 14, 6, 255)
    c.poly([(x - 30 * s, base - 58 * s), (x - 14 * s, base - 58 * s), (x - 22 * s, base - 72 * s)], fill=face)
    c.poly([(x + 14 * s, base - 58 * s), (x + 30 * s, base - 58 * s), (x + 22 * s, base - 72 * s)], fill=face)
    c.poly([(x - 32 * s, base - 34 * s), (x + 32 * s, base - 34 * s), (x + 20 * s, base - 18 * s), (x + 8 * s, base - 26 * s),
            (x - 4 * s, base - 16 * s), (x - 16 * s, base - 26 * s), (x - 24 * s, base - 18 * s)], fill=face)
    return (x, base - 45 * s)


def mini_tree(c, x, base, s, rnd):
    c.rect(x - 22 * s, base - 30 * s, x + 22 * s, base, fill=(160, 40, 40, 255), r=4 * s)
    c.rect(x - 8 * s, base - 44 * s, x + 8 * s, base - 28 * s, fill=(100, 60, 30, 255))
    bulbs = []
    for i, (w, top) in enumerate(((70, 150), (56, 200), (40, 240))):
        yb = base - 40 * s - i * 46 * s
        c.poly([(x - w * s, yb), (x + w * s, yb), (x, yb - 90 * s)], fill=(30, 110, 60, 255))
        for j in range(4):
            bx = x + rnd.uniform(-w * 0.7, w * 0.7) * s
            by = yb - rnd.uniform(6, 40) * s
            bulbs.append((bx, by))
    tip = (x, base - 40 * s - 2 * 46 * s - 90 * s)
    return bulbs, tip


def books_stack(c, x, base, s, rnd):
    y = base
    for i in range(rnd.randint(2, 4)):
        w = rnd.uniform(70, 100) * s
        h = rnd.uniform(14, 22) * s
        col = rnd.choice([(120, 40, 40), (40, 70, 110), (50, 90, 60), (140, 110, 50), (90, 50, 90)])
        off = rnd.uniform(-8, 8) * s
        c.rect(x - w / 2 + off, y - h, x + w / 2 + off, y, fill=col + (255,), r=2 * s)
        c.rect(x - w / 2 + off + 3 * s, y - h + 3 * s, x + w / 2 + off - 6 * s, y - 3 * s, fill=(236, 228, 210, 255))
        c.rect(x - w / 2 + off, y - h, x - w / 2 + off + 8 * s, y, fill=dark(col, 0.8) + (255,))
        y -= h


def rocket(c, x, base, s):
    c.rect(x - 34 * s, base - 8 * s, x + 34 * s, base, fill=(60, 64, 80, 255), r=3 * s)
    c.poly([(x - 18 * s, base - 40 * s), (x - 40 * s, base - 8 * s), (x - 18 * s, base - 16 * s)], fill=(220, 60, 60, 255))
    c.poly([(x + 18 * s, base - 40 * s), (x + 40 * s, base - 8 * s), (x + 18 * s, base - 16 * s)], fill=(220, 60, 60, 255))
    c.rect(x - 18 * s, base - 130 * s, x + 18 * s, base - 14 * s, fill=(236, 236, 244, 255), r=8 * s)
    c.poly([(x - 18 * s, base - 128 * s), (x + 18 * s, base - 128 * s), (x, base - 176 * s)], fill=(220, 60, 60, 255))
    c.ellipse(x, base - 96 * s, 9 * s, 9 * s, fill=(90, 170, 240, 255))


def telescope(c, x, base, s, flip=False):
    d = -1 if flip else 1
    c.line([(x, base), (x - 26 * s, base - 4 * s)], (60, 60, 70, 255), 5 * s)
    c.line([(x, base), (x + 26 * s, base - 4 * s)], (60, 60, 70, 255), 5 * s)
    c.line([(x, base), (x, base - 80 * s)], (60, 60, 70, 255), 6 * s)
    c.poly([(x - d * 60 * s, base - 70 * s), (x + d * 70 * s, base - 120 * s), (x + d * 78 * s, base - 106 * s), (x - d * 54 * s, base - 58 * s)], fill=(200, 205, 220, 255))
    c.ellipse(x + d * 74 * s, base - 113 * s, 10 * s, 10 * s, fill=(90, 100, 130, 255))


def robot(c, x, base, s, accent):
    c.rect(x - 30 * s, base - 60 * s, x + 30 * s, base, fill=(200, 205, 215, 255), r=10 * s)
    c.rect(x - 34 * s, base - 120 * s, x + 34 * s, base - 64 * s, fill=(225, 230, 238, 255), r=14 * s)
    c.rect(x - 24 * s, base - 108 * s, x + 24 * s, base - 76 * s, fill=(20, 24, 34, 255), r=8 * s)
    c.ellipse(x - 10 * s, base - 92 * s, 5 * s, 5 * s, fill=accent + (255,))
    c.ellipse(x + 10 * s, base - 92 * s, 5 * s, 5 * s, fill=accent + (255,))
    c.line([(x, base - 120 * s), (x, base - 138 * s)], (160, 165, 175, 255), 3 * s)
    c.ellipse(x, base - 140 * s, 6 * s, 6 * s, fill=(255, 80, 80, 255))
    return (x, base - 140 * s)


def bottle_ship(c, x, base, s):
    c.rect(x - 60 * s, base - 8 * s, x + 60 * s, base, fill=(110, 76, 44, 255), r=3 * s)
    c.tellipse(x, base - 46 * s, 80 * s, 38 * s, (180, 230, 230), 0.35)
    c.rect(x + 74 * s, base - 56 * s, x + 100 * s, base - 36 * s, fill=(150, 110, 70, 255), r=4 * s)
    c.poly([(x - 40 * s, base - 30 * s), (x + 40 * s, base - 30 * s), (x + 30 * s, base - 16 * s), (x - 30 * s, base - 16 * s)], fill=(120, 70, 40, 255))
    c.line([(x, base - 30 * s), (x, base - 76 * s)], (90, 60, 30, 255), 3 * s)
    c.poly([(x + 2 * s, base - 74 * s), (x + 30 * s, base - 40 * s), (x + 2 * s, base - 40 * s)], fill=(240, 236, 220, 255))
    c.poly([(x - 2 * s, base - 70 * s), (x - 26 * s, base - 40 * s), (x - 2 * s, base - 40 * s)], fill=(240, 236, 220, 255))
    c.d.ellipse(c._b(x - 80 * s, base - 84 * s, x + 80 * s, base - 8 * s), outline=(210, 240, 240, 200), width=int(3 * s * c.ss))


def fedora(c, x, base, s):
    c.ellipse(x, base - 8 * s, 70 * s, 12 * s, fill=(60, 48, 38, 255))
    c.rect(x - 40 * s, base - 54 * s, x + 40 * s, base - 8 * s, fill=(72, 58, 46, 255), r=14 * s)
    c.rect(x - 40 * s, base - 22 * s, x + 40 * s, base - 12 * s, fill=(30, 22, 18, 255))


def neon_sign(c, cx, cy, txt, px, color, kind='bold'):
    c.glow(cx, cy, px * len(txt) * 0.5, px * 1.2, color, 0.45)
    c.text((cx, cy), txt, px, light(color, 0.55) + (255,), kind)


def garland(c, x0, x1, y, sag, rnd):
    pts = []
    for i in range(41):
        f = i / 40
        pts.append((x0 + (x1 - x0) * f, y + math.sin(f * math.pi) * sag))
    c.line(pts, (30, 90, 50, 255), 10)
    c.line(pts, (50, 130, 70, 255), 5)
    bulbs = []
    for i in range(1, 20):
        f = i / 20
        bulbs.append((x0 + (x1 - x0) * f, y + math.sin(f * math.pi) * sag + 8))
    return bulbs


def cobweb(c, x, y, r, flip_x=False, flip_y=False):
    sx = -1 if flip_x else 1
    sy = -1 if flip_y else 1
    for a in range(0, 91, 18):
        ra = math.radians(a)
        c.line([(x, y), (x + sx * math.cos(ra) * r, y + sy * math.sin(ra) * r)], (200, 200, 210, 110), 1.2)
    for k in range(1, 5):
        rr = r * k / 5
        pts = [(x + sx * math.cos(math.radians(a)) * rr, y + sy * math.sin(math.radians(a)) * rr) for a in range(0, 91, 18)]
        c.line(pts, (200, 200, 210, 100), 1.0)


def column(c, x0, y0, x1, y1, col=(170, 160, 140)):
    c.rect(x0 - 10, y0, x1 + 10, y0 + 24, fill=light(col, 0.1) + (255,), r=3)
    c.rect(x0, y0 + 24, x1, y1, fill=col + (255,))
    w = x1 - x0
    for i in range(1, 5):
        fx = x0 + w * i / 5
        c.rect(fx - 1.5, y0 + 30, fx + 1.5, y1, fill=dark(col, 0.8) + (255,))
    c.trect(x0, y0, x0 + w * 0.3, y1, (255, 255, 255), 0.08)


def server_rack(c, x0, y0, x1, y1, rnd):
    c.rect(x0, y0, x1, y1, fill=(18, 20, 26, 255), r=6)
    leds = []
    y = y0 + 14
    while y < y1 - 20:
        c.rect(x0 + 8, y, x1 - 8, y + 22, fill=(32, 36, 46, 255), r=3)
        for k in range(3):
            leds.append((x0 + 18 + k * 10, y + 11))
        y += 30
    return leds


def life_ring(c, cx, cy, r):
    c.ellipse(cx, cy, r, r, fill=(240, 240, 240, 255))
    c.ellipse(cx, cy, r * 0.55, r * 0.55, fill=(0, 0, 0, 0))
    for a in (0, 90, 180, 270):
        c.d.arc(c._b(cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78), a - 20, a + 20, fill=(220, 50, 50, 255), width=int(r * 0.45 * c.ss))


def anchor(c, cx, cy, s, col=(200, 200, 210)):
    c.line([(cx, cy - 60 * s), (cx, cy + 50 * s)], col + (255,), 8 * s)
    c.line([(cx - 30 * s, cy - 40 * s), (cx + 30 * s, cy - 40 * s)], col + (255,), 7 * s)
    c.d.ellipse(c._b(cx - 12 * s, cy - 82 * s, cx + 12 * s, cy - 58 * s), outline=col + (255,), width=int(6 * s * c.ss))
    c.d.arc(c._b(cx - 50 * s, cy - 10 * s, cx + 50 * s, cy + 60 * s), 20, 160, fill=col + (255,), width=int(8 * s * c.ss))


def framed_art(c, x0, y0, x1, y1, frame_col, rnd, kind='landscape'):
    c.tellipse((x0 + x1) / 2, y1 + 4, (x1 - x0) * 0.5, 8, (0, 0, 0), 0.3, blur=5)
    c.rect(x0 - 8, y0 - 8, x1 + 8, y1 + 8, fill=frame_col + (255,), r=2)
    img = view_image(rnd.choice(['forest_day', 'dusk_castle', 'snow_night']) if kind == 'landscape' else kind,
                     int(x1 - x0), int(y1 - y0), rnd, c.ss)
    c.paste(img, x0, y0)


def wall_clock(c, cx, cy, r, col=(240, 236, 226)):
    c.ellipse(cx, cy, r + 6, r + 6, fill=(60, 40, 30, 255))
    c.ellipse(cx, cy, r, r, fill=col + (255,))
    for i in range(12):
        a = math.radians(i * 30)
        c.line([(cx + math.cos(a) * r * 0.8, cy + math.sin(a) * r * 0.8), (cx + math.cos(a) * r * 0.92, cy + math.sin(a) * r * 0.92)], (40, 40, 40, 255), 2)
    c.line([(cx, cy), (cx + r * 0.5, cy - r * 0.2)], (30, 30, 30, 255), 3)
    c.line([(cx, cy), (cx - r * 0.1, cy - r * 0.7)], (30, 30, 30, 255), 2)


def floor_lamp(c, x, base, top, s, col=(255, 210, 150)):
    c.ellipse(x, base - 4, 30 * s, 7 * s, fill=(40, 40, 46, 255))
    c.rect(x - 3 * s, top + 40 * s, x + 3 * s, base, fill=(50, 50, 56, 255))
    c.glow(x, top + 30 * s, 160 * s, 120 * s, col, 0.5)
    c.poly([(x - 30 * s, top), (x + 30 * s, top), (x + 48 * s, top + 52 * s), (x - 48 * s, top + 52 * s)], fill=light(col, 0.3) + (255,))


# ----------------------------------------------------------------------------------------- panel (pictures / titles)

PANEL_STYLES = {
    'studio': ('screen', (24, 28, 38)),
    'christmas': ('frame', (150, 100, 56)),
    'halloween': ('frame', (40, 28, 44)),
    'history': ('frame', (176, 132, 60)),
    'space': ('screen', (60, 66, 84)),
    'tech': ('screen', (20, 24, 32)),
    'nature': ('frame', (120, 84, 50)),
    'ocean': ('frame', (90, 110, 120)),
    'mystery': ('board', (60, 44, 32)),
}


def draw_panel(c, rect, theme, accent, title, rnd):
    """Draws the frame around the picture panel and an idle title card inside it.
    Returns (inner rect, idle RGB image of the inner area)."""
    x0, y0, x1, y1 = rect
    style, col = PANEL_STYLES.get(theme, ('screen', (24, 28, 38)))
    w, h = x1 - x0, y1 - y0
    c.tellipse((x0 + x1) / 2, y1 + 10, w * 0.5, 16, (0, 0, 0), 0.4, blur=10)
    if style == 'screen':
        c.glow((x0 + x1) / 2, (y0 + y1) / 2, w * 0.7, h * 0.75, accent, 0.18)
        c.rect(x0, y0, x1, y1, fill=col + (255,), r=16)
        bw = max(10, w * 0.022)
        inner = (x0 + bw, y0 + bw, x1 - bw, y1 - bw)
        c.ellipse((x0 + x1) / 2, y1 - bw / 2, 3, 3, fill=accent + (255,))
    elif style == 'board':
        bw = max(14, w * 0.03)
        c.rect(x0, y0, x1, y1, fill=col + (255,), r=6)
        inner = (x0 + bw, y0 + bw, x1 - bw, y1 - bw)
    else:
        bw = max(16, w * 0.035)
        c.rect(x0, y0, x1, y1, fill=col + (255,), r=4)
        c.rect(x0 + bw * 0.3, y0 + bw * 0.3, x1 - bw * 0.3, y1 - bw * 0.3, fill=light(col, 0.15) + (255,), r=3)
        c.rect(x0 + bw * 0.6, y0 + bw * 0.6, x1 - bw * 0.6, y1 - bw * 0.6, fill=dark(col, 0.75) + (255,), r=2)
        inner = (x0 + bw, y0 + bw, x1 - bw, y1 - bw)
    iw, ih = int(inner[2] - inner[0]), int(inner[3] - inner[1])
    idle = Canvas(iw, ih, c.ss, (0, 0, 0, 255))
    if style == 'board':
        idle.rect(0, 0, iw, ih, fill=(34, 52, 44, 255))
        for _ in range(int(iw * ih / 2000)):
            idle.ellipse(rnd.uniform(0, iw), rnd.uniform(0, ih), 1.2, 1.2, fill=(60, 80, 70, 255))
        tcol = (236, 236, 226, 255)
        tkind = 'hand'
    elif style == 'screen':
        for yy in range(0, int(ih * idle.ss), 2):
            f = yy / (ih * idle.ss)
            idle.d.line([(0, yy), (iw * idle.ss, yy)], fill=mix(dark(accent, 0.25), (6, 8, 20), f) + (255,), width=2)
        for yy in range(0, ih, 6):
            idle.trect(0, yy, iw, yy + 1, (0, 0, 0), 0.18)
        tcol = (255, 255, 255, 255)
        tkind = 'black'
    else:
        paper = (238, 226, 196) if theme in ('history', 'christmas', 'nature') else (40, 34, 50)
        idle.rect(0, 0, iw, ih, fill=paper + (255,))
        idle.trect(0, 0, iw, ih, (120, 90, 40), 0.15, blur=30)
        tcol = (70, 46, 26, 255) if theme in ('history', 'christmas', 'nature') else (240, 200, 140, 255)
        tkind = 'serif'
    words = (title or THEMES.get(theme, {}).get('label', '')).upper().split()
    px = ih * 0.16
    lines, cur = [], ''
    for wd in words:
        test = (cur + ' ' + wd).strip()
        if idle.text_width(test, px, tkind) > iw * 0.82 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = test
    if cur:
        lines.append(cur)
    lines = lines[:3]
    while lines and max(idle.text_width(l, px, tkind) for l in lines) > iw * 0.86:
        px *= 0.9
    total = len(lines) * px * 1.15
    for i, ln in enumerate(lines):
        idle.text((iw / 2, ih / 2 - total / 2 + px * 0.6 + i * px * 1.15), ln, px, tcol, tkind)
    if style == 'screen':
        idle.rect(iw * 0.35, ih / 2 + total / 2 + px * 0.35, iw * 0.65, ih / 2 + total / 2 + px * 0.35 + 4, fill=accent + (255,), r=2)
    idle_img = idle.result().convert('RGB')
    c.paste(idle_img, inner[0], inner[1])
    return inner, idle_img


# ----------------------------------------------------------------------------------------- the set

class SetScene:
    """A built set. base: RGB background; desk: RGBA overlay drawn in front of the character's body;
    panel: inner rect for pictures; dynamic elements are drawn every frame."""

    def __init__(self):
        self.base = None
        self.desk = None
        self.desk_pos = (0, 0)
        self.panel = None
        self.panel_idle = None
        self.accent = (10, 140, 255)
        self.theme = 'studio'
        self.has_desk = True
        self.stage = 'room'
        self.back = []
        self.front = []
        self.room = []

    def draw_back(self, img, t):
        d = ImageDraw.Draw(img)
        for f in self.back:
            f(img, d, t)

    def draw_front(self, img, t):
        d = ImageDraw.Draw(img)
        for f in self.front:
            f(img, d, t)

    def draw_room(self, img, t):
        d = ImageDraw.Draw(img)
        for f in self.room:
            f(img, d, t)


def _blinker(points, colors, period, phase_seed, r):
    rnd = random.Random(phase_seed)
    data = [(p, rnd.choice(colors), rnd.uniform(0, math.pi * 2), rnd.uniform(0.7, 1.3)) for p in points]

    def f(img, d, t):
        for (x, y), col, ph, sp in data:
            on = 0.5 + 0.5 * math.sin(t * sp * 2 * math.pi / period + ph)
            c2 = mix(dark(col, 0.35), col, on)
            if on > 0.6:
                d.ellipse([x - r * 1.9, y - r * 1.9, x + r * 1.9, y + r * 1.9], fill=mix((30, 30, 30), col, 0.35 * on))
            d.ellipse([x - r, y - r, x + r, y + r], fill=c2)
    return f


def _flames(points, scale):
    sprites = []
    for strength in (0.55, 0.75, 0.95):
        g = Canvas(int(140 * scale) + 2, int(140 * scale) + 2, 1)
        g.glow(70 * scale, 70 * scale, 70 * scale, 70 * scale, (255, 170, 60), strength)
        sprites.append(g.im)

    def f(img, d, t):
        for i, (x, y) in enumerate(points):
            k = int((math.sin(t * 13 + i * 2.1) + math.sin(t * 7.3 + i)) * 0.75 + 1.5)
            k = max(0, min(2, k))
            sp = sprites[k]
            img.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)
            fh = (10 + 3 * math.sin(t * 17 + i)) * scale
            d.polygon([(x - 4 * scale, y + 4 * scale), (x + 4 * scale, y + 4 * scale), (x + math.sin(t * 9 + i) * 2 * scale, y - fh)],
                      fill=(255, 220, 120))
            d.ellipse([x - 2.5 * scale, y - 1 * scale, x + 2.5 * scale, y + 4 * scale], fill=(255, 255, 220))
    return f


def _snow_in(rect, n, seed, speed=1.0, color=(255, 255, 255)):
    x0, y0, x1, y1 = rect
    rnd = random.Random(seed)
    flakes = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(0.6, 1.6), rnd.uniform(0, 6.28)) for _ in range(n)]
    w, h = x1 - x0, y1 - y0

    def f(img, d, t):
        for fx, fy, sz, ph in flakes:
            y = (fy * h + t * 22 * sz * speed) % h
            x = (fx * w + math.sin(t * 0.8 + ph) * 10) % w
            r = sz * 1.3
            d.ellipse([x0 + x - r, y0 + y - r, x0 + x + r, y0 + y + r], fill=color)
    return f


def _rain_in(rect, n, seed):
    x0, y0, x1, y1 = rect
    rnd = random.Random(seed)
    drops = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(0.8, 1.4)) for _ in range(n)]
    w, h = x1 - x0, y1 - y0

    def f(img, d, t):
        for fx, fy, sp in drops:
            y = (fy * h + t * 420 * sp) % h
            x = fx * w
            d.line([(x0 + x, y0 + y), (x0 + x - 2, y0 + min(h, y + 12))], fill=(150, 175, 195), width=1)
    return f


def _twinkle(rect, n, seed):
    x0, y0, x1, y1 = rect
    rnd = random.Random(seed)
    st = [(rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(0, 6.28), rnd.uniform(1, 3)) for _ in range(n)]

    def f(img, d, t):
        for x, y, ph, sp in st:
            v = 0.5 + 0.5 * math.sin(t * sp + ph)
            if v > 0.75:
                r = 1.2 + v
                d.line([(x - r * 2, y), (x + r * 2, y)], fill=(255, 255, 255))
                d.line([(x, y - r * 2), (x, y + r * 2)], fill=(255, 255, 255))
    return f


def _fish(rect, n, seed):
    x0, y0, x1, y1 = rect
    rnd = random.Random(seed)
    fish = [(rnd.uniform(0.1, 0.9), rnd.uniform(14, 26), rnd.uniform(0.03, 0.08), rnd.choice([1, -1]),
             rnd.choice([(255, 150, 40), (255, 220, 60), (90, 200, 255), (255, 100, 120)]), rnd.uniform(0, 1)) for _ in range(n)]
    w, h = x1 - x0, y1 - y0

    def f(img, d, t):
        for fy, sz, sp, dr, col, ph in fish:
            u = (ph + t * sp) % 1.2 - 0.1
            x = x0 + (u if dr > 0 else 1 - u) * w
            y = y0 + fy * h + math.sin(t * 2 + ph * 10) * 6
            if x < x0 + sz or x > x1 - sz:
                continue
            d.ellipse([x - sz, y - sz * 0.5, x + sz, y + sz * 0.5], fill=col)
            tx = x - dr * sz
            d.polygon([(tx, y), (tx - dr * sz * 0.7, y - sz * 0.5), (tx - dr * sz * 0.7, y + sz * 0.5)], fill=col)
            d.ellipse([x + dr * sz * 0.5 - 2, y - 3, x + dr * sz * 0.5 + 2, y + 1], fill=(20, 20, 30))
    return f


def _bubbles(rect, n, seed):
    x0, y0, x1, y1 = rect
    rnd = random.Random(seed)
    bub = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(2, 5), rnd.uniform(0.5, 1.2)) for _ in range(n)]
    w, h = x1 - x0, y1 - y0

    def f(img, d, t):
        for fx, fy, r, sp in bub:
            y = y1 - ((fy * h + t * 40 * sp) % h)
            x = x0 + fx * w + math.sin(t * 3 + fx * 20) * 4
            d.ellipse([x - r, y - r, x + r, y + r], outline=(210, 240, 255), width=1)
    return f


def _motes(W, H, n, seed, color, rise=False, size=(1.0, 2.2)):
    rnd = random.Random(seed)
    m = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(*size), rnd.uniform(0.3, 1.0), rnd.uniform(0, 6.28)) for _ in range(n)]

    def f(img, d, t):
        for fx, fy, r, sp, ph in m:
            if rise:
                y = H - ((fy * H + t * 30 * sp) % H)
            else:
                y = (fy * H + math.sin(t * 0.3 * sp + ph) * 40) % H
            x = (fx * W + math.sin(t * 0.5 * sp + ph) * 30) % W
            v = 0.5 + 0.5 * math.sin(t * 2 * sp + ph)
            if v < 0.25:
                continue
            col = mix((40, 40, 50), color, v)
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    return f


def _steam(x, y, s):
    def f(img, d, t):
        for i in range(3):
            u = (t * 0.45 + i / 3) % 1.0
            yy = y - u * 60 * s
            xx = x + math.sin(u * 6 + i) * 8 * s
            r = (3 + u * 8) * s
            col = mix((120, 120, 130), (220, 220, 230), 1 - u)
            if u < 0.85:
                d.ellipse([xx - r, yy - r, xx + r, yy + r], outline=col, width=1)
    return f


def _code_scroll(screens, seed, accent):
    rnd = random.Random(seed)
    sprites = []
    for (x0, y0, x1, y1) in screens[:1] + screens[2:3]:
        w, h = int(x1 - x0), int(y1 - y0)
        strip = Image.new('RGB', (max(1, w), max(1, h * 3)), (6, 12, 20))
        d = ImageDraw.Draw(strip)
        y = 4
        while y < strip.height - 10:
            indent = rnd.choice([0, 0, 1, 2]) * 10
            x = 6 + indent
            for _ in range(rnd.randint(1, 4)):
                if x >= w - 10:
                    break
                ln = rnd.randint(10, 50)
                col = rnd.choice([accent, (255, 120, 200), (240, 240, 250), (140, 160, 180), (255, 210, 90)])
                d.rectangle([x, y, min(w - 4, x + ln), y + 4], fill=col)
                x += ln + 6
            y += 11
        sprites.append(((int(x0), int(y0), w, h), strip))

    def f(img, d, t):
        for (x0, y0, w, h), strip in sprites:
            off = int((t * 18) % (strip.height - h))
            img.paste(strip.crop((0, off, w, off + h)), (x0, y0))
    return f


def build_set(theme, seed, W, H, title='', ss=2, stage='room'):
    """Builds a whole set for frame size W x H. stage: 'room' (desk, wall, props) or 'open' (standing in the world)."""
    if stage == 'open':
        return build_open_set(theme, seed, W, H, title, ss)
    theme = theme if theme in THEMES else 'studio'
    L = layout_for(W, H)
    rnd = random.Random(seed)
    accent = THEMES[theme]['accent']
    k = L['k']
    S = SetScene()
    S.theme = theme
    S.accent = accent
    c = Canvas(W, H, ss, (0, 0, 0, 255))
    dk = Canvas(W, H, ss, (0, 0, 0, 0))
    fx0, fy0, fx1, fy1 = L['feature']
    pl = L['prop_l']
    pr = L['prop_r']
    ps = k * (0.95 if L['portrait'] else 1.0)
    desk_col = (26, 21, 31)
    desk_edge = (8, 70, 150)

    if theme == 'studio':
        wall(c, L, (16, 22, 50), (26, 38, 82), 'acoustic', rnd, accent)
        window_feature(c, L['feature'], 'city_night', (34, 38, 56), rnd, ss, accent)
        S.back.append(_twinkle(L['feature'], 10, seed))
        sl = L['side_l']
        sr = L['side_r']
        if sr[2] - sr[0] > 60 * k:
            floor_lamp(c, (sr[0] + sr[2]) / 2, L['desk_y'], fy0 + 40, k * 1.1, (150, 190, 255))
        if L['portrait']:
            neon_sign(c, W * 0.5, fy0 - 4, 'ON AIR', 30 * k, (255, 60, 90))
        plant(dk, pl[0], pl[1], ps, rnd)
        mug(dk, pr[0], pr[1], ps, (30, 140, 255), steam=True)
        S.front.append(_steam(pr[0], pr[1] - 58 * ps, ps))
        S.room.append(_motes(W, H, 22, seed + 3, (120, 160, 220)))
    elif theme == 'christmas':
        wall(c, L, (96, 26, 30), (60, 16, 22), 'stripes', rnd, accent)
        c.rect(0, H * 0.72, W, H, fill=(80, 54, 36, 255))
        c.rect(0, H * 0.72, W, H * 0.725, fill=(130, 90, 60, 255))
        if rnd.random() < 0.5 or L['portrait']:
            window_feature(c, L['feature'], 'snow_night', (236, 232, 222), rnd, ss, accent)
            S.back.append(_snow_in(L['feature'], 45, seed, 1.0))
            fw = (fx1 - fx0)
            wr = min(fw, fy1 - fy0) * 0.16
            wx, wy = (fx0 + fx1) / 2, fy0 + wr * 1.2
            for a in range(0, 360, 20):
                ra = math.radians(a)
                c.ellipse(wx + math.cos(ra) * wr, wy + math.sin(ra) * wr, wr * 0.35, wr * 0.35, fill=(30, 110, 60, 255))
            c.poly([(wx - 10, wy + wr), (wx + 10, wy + wr), (wx + 18, wy + wr + 26), (wx - 18, wy + wr + 26)], fill=(200, 30, 40, 255))
        else:
            fire_inner = fireplace_feature(c, L['feature'], rnd)
            S.back.append(_flames([(fire_inner[0] + (fire_inner[2] - fire_inner[0]) * f, fire_inner[3] - 14) for f in (0.3, 0.5, 0.7)], k * 2.4))
        bulbs = garland(c, -20, W + 20, H * 0.03, H * 0.04, rnd)
        S.back.append(_blinker(bulbs, [(255, 70, 70), (255, 210, 80), (90, 220, 120), (90, 170, 255)], 2.2, seed, max(3, 5 * k)))
        sr = L['side_r']
        if sr[2] - sr[0] > 80 * k:
            tb, tip = mini_tree(c, (sr[0] + sr[2]) / 2, L['desk_y'], k * 1.6, rnd)
            S.back.append(_blinker(tb, [(255, 80, 80), (255, 220, 90), (120, 200, 255)], 1.6, seed + 1, max(2.5, 4 * k)))
        tb2, tip2 = mini_tree(dk, pl[0], pl[1], ps * 0.85, rnd)
        S.front.append(_blinker(tb2, [(255, 80, 80), (255, 220, 90), (120, 200, 255), (120, 255, 150)], 1.4, seed + 2, max(2, 3.2 * ps)))
        mug(dk, pr[0] - 40 * ps, pr[1], ps, (200, 40, 50))
        S.front.append(_steam(pr[0] - 40 * ps, pr[1] - 58 * ps, ps))
        fl = candle(dk, pr[0] + 60 * ps, pr[1], ps, (240, 230, 210), 60)
        S.front.append(_flames([fl], ps * 1.4))
        S.room.append(_motes(W, H, 18, seed + 3, (255, 210, 140), size=(1.5, 3.0)))
        desk_col = (70, 44, 30)
        desk_edge = (150, 100, 56)
    elif theme == 'halloween':
        wall(c, L, (44, 36, 54), (26, 20, 34), 'stone', rnd, accent)
        window_feature(c, L['feature'], 'moon_hills', (30, 22, 34), rnd, ss, accent, arched=True, mullions=False)
        S.back.append(_twinkle(L['feature'], 6, seed))
        cobweb(c, 0, 0, H * 0.18)
        cobweb(c, W, 0, H * 0.18, flip_x=True)
        sl = L['side_l']
        if not L['portrait'] and sl[2] - sl[0] > 50:
            for i in range(3):
                bx = sl[0] + (sl[2] - sl[0]) * (0.3 + i * 0.2)
                c.line([(bx, 0), (bx, H * (0.08 + i * 0.05))], (30, 20, 30, 255), 1.5)
        pk = pumpkin(dk, pl[0], pl[1], ps)
        S.front.append(_flames([(pk[0], pk[1] + 6 * ps)], ps * 1.8))
        f1 = candle(dk, pr[0] - 30 * ps, pr[1], ps, (220, 210, 190), 80)
        f2 = candle(dk, pr[0] + 30 * ps, pr[1], ps * 0.85, (200, 190, 170), 50)
        S.front.append(_flames([f1, f2], ps * 1.3))
        S.room.append(_motes(W, H, 26, seed + 3, (255, 140, 60), rise=True, size=(1.0, 2.0)))
        accent_light = (255, 140, 40)
        c.glow(L['char_x'], L['head_y'], W * 0.35, H * 0.4, (120, 60, 160), 0.25)
        desk_col = (30, 22, 30)
        desk_edge = (255, 120, 30)
    elif theme == 'history':
        wall(c, L, (78, 52, 34), (52, 34, 22), 'panels', rnd, accent)
        bookshelf(c, L['feature'], rnd, wood=(110, 72, 40))
        c.glow(L['char_x'], L['head_y'], W * 0.4, H * 0.45, (255, 200, 120), 0.18)
        sl, sr = L['side_l'], L['side_r']
        if sr[2] - sr[0] > 50:
            column(c, sr[0] + (sr[2] - sr[0]) * 0.25, H * 0.04, sr[0] + (sr[2] - sr[0]) * 0.75, L['desk_y'])
        if L['portrait']:
            column(c, sl[0] + (sl[2] - sl[0]) * 0.25, H * 0.36, sl[0] + (sl[2] - sl[0]) * 0.75, L['desk_y'])
        globe(dk, pl[0], pl[1], ps)
        books_stack(dk, pr[0] + 30 * ps, pr[1], ps, rnd)
        fl = candle(dk, pr[0] - 50 * ps, pr[1], ps, (236, 226, 200), 70)
        S.front.append(_flames([fl], ps * 1.4))
        S.room.append(_motes(W, H, 30, seed + 3, (255, 220, 160), size=(0.8, 1.8)))
        desk_col = (66, 42, 26)
        desk_edge = (176, 132, 60)
    elif theme == 'space':
        wall(c, L, (26, 30, 44), (16, 18, 28), 'metal', rnd, accent)
        porthole_feature(c, L['feature'], 'space', rnd, ss, accent)
        fr = L['feature']
        cxp, cyp = (fr[0] + fr[2]) / 2, (fr[1] + fr[3]) / 2
        rr = min(fr[2] - fr[0], fr[3] - fr[1]) * 0.48
        S.back.append(_twinkle((cxp - rr * 0.8, cyp - rr * 0.8, cxp + rr * 0.8, cyp + rr * 0.2), 10, seed))
        leds = []
        for side in (L['side_l'], L['side_r']):
            if side[2] - side[0] > 40:
                px0 = side[0] + (side[2] - side[0]) * 0.18
                px1 = side[2] - (side[2] - side[0]) * 0.18
                py0, py1 = H * (0.12 if not L['portrait'] else 0.42), H * (0.55 if not L['portrait'] else 0.64)
                c.rect(px0, py0, px1, py1, fill=(36, 40, 56, 255), r=8)
                yy = py0 + 16
                while yy < py1 - 12:
                    xx = px0 + 12
                    while xx < px1 - 10:
                        leds.append((xx, yy))
                        xx += 14
                    yy += 18
        S.back.append(_blinker(leds, [accent, (255, 80, 80), (90, 255, 140), (255, 210, 80)], 1.3, seed, max(2, 2.6 * k)))
        rocket(dk, pl[0], pl[1], ps)
        telescope(dk, pr[0], pr[1], ps, flip=True)
        desk_col = (30, 34, 46)
        desk_edge = accent
    elif theme == 'tech':
        wall(c, L, (12, 10, 26), (8, 6, 18), 'grid', rnd, accent)
        screens = monitor_wall(c, L['feature'], rnd, accent)
        S.back.append(_code_scroll(screens, seed, accent))
        c.rect(0, H * 0.02, W, H * 0.026, fill=(255, 60, 200, 255))
        c.glow(W / 2, H * 0.023, W * 0.6, H * 0.06, (255, 60, 200), 0.4)
        sl, sr = L['side_l'], L['side_r']
        leds = []
        if sr[2] - sr[0] > 60:
            leds += server_rack(c, sr[0] + (sr[2] - sr[0]) * 0.15, H * 0.12, sr[2] - (sr[2] - sr[0]) * 0.15, L['desk_y'], rnd)
        if not L['portrait'] and sl[2] - sl[0] > 40:
            neon_sign(c, (sl[0] + sl[2]) / 2, H * 0.62, '</>', 34 * k / 0.85, accent, 'mono')
        if L['portrait']:
            neon_sign(c, W / 2, H * 0.36, '< / >', 26 * k, accent, 'mono')
        S.back.append(_blinker(leds, [accent, (90, 255, 140), (255, 200, 60)], 0.9, seed, max(2, 2.4 * k)))
        robot(dk, pl[0], pl[1], ps, accent)
        mug(dk, pr[0], pr[1], ps, (255, 60, 200))
        S.room.append(_motes(W, H, 26, seed + 3, accent, rise=True, size=(0.8, 1.6)))
        desk_col = (16, 14, 26)
        desk_edge = (255, 60, 200)
    elif theme == 'nature':
        wall(c, L, (128, 86, 52), (98, 64, 38), 'logs', rnd, accent)
        window_feature(c, L['feature'], 'forest_day', (86, 58, 34), rnd, ss, accent)
        sl, sr = L['side_l'], L['side_r']
        for side in (sl, sr):
            if side[2] - side[0] > 60:
                hx = (side[0] + side[2]) / 2
                c.line([(hx, 0), (hx, H * 0.12)], (60, 50, 40, 255), 2)
                plant(c, hx, H * 0.2, k * 0.8, rnd, pot=(220, 210, 190))
        plant(dk, pl[0], pl[1], ps, rnd, pot=(180, 120, 80))
        mug(dk, pr[0], pr[1], ps, (240, 236, 226))
        S.front.append(_steam(pr[0], pr[1] - 58 * ps, ps))
        S.room.append(_motes(W, H, 20, seed + 3, (255, 240, 160), size=(1.2, 2.4)))
        desk_col = (90, 60, 36)
        desk_edge = (140, 100, 60)
    elif theme == 'ocean':
        wall(c, L, (60, 84, 104), (40, 58, 76), 'planks', rnd, accent)
        aquarium_feature(c, L['feature'], rnd, ss, accent)
        S.back.append(_fish(L['feature'], 6, seed))
        S.back.append(_bubbles(L['feature'], 18, seed + 1))
        sl, sr = L['side_l'], L['side_r']
        if sr[2] - sr[0] > 70:
            life_ring(c, (sr[0] + sr[2]) / 2, H * 0.3, min(sr[2] - sr[0], H * 0.2) * 0.35)
        if sl[2] - sl[0] > 70 and not L['portrait']:
            anchor(c, (sl[0] + sl[2]) / 2, H * 0.68, k * 0.9)
        bottle_ship(dk, pl[0], pl[1], ps)
        mug(dk, pr[0], pr[1], ps, (240, 240, 240))
        desk_col = (60, 44, 34)
        desk_edge = (60, 200, 230)
    elif theme == 'mystery':
        wall(c, L, (54, 38, 28), (30, 20, 16), 'panels', rnd, accent)
        evidence_board(c, L['feature'], rnd)
        sl, sr = L['side_l'], L['side_r']
        side = sr if sr[2] - sr[0] > sl[2] - sl[0] else sl
        if side[2] - side[0] > 60:
            wr = (side[0] + 12, H * (0.1 if not L['portrait'] else 0.4), side[2] - 12, H * (0.5 if not L['portrait'] else 0.62))
            window_feature(c, wr, 'rain_city', (40, 30, 24), rnd, ss, accent, mullions=False)
            for i in range(9):
                yy = wr[1] + (wr[3] - wr[1]) * (i + 0.5) / 9
                c.rect(wr[0], yy, wr[2], yy + 5, fill=(70, 56, 40, 255))
            S.back.append(_rain_in(wr, 30, seed))
        c.tpoly([(0, 0), (W, 0), (W, H), (0, H)], (0, 0, 0), 0.18)
        desk_lamp(dk, pr[0] + 30 * ps, pr[1], ps * 1.1, (40, 60, 40), (255, 220, 150), True, flip=True)
        fedora(dk, pl[0], pl[1], ps)
        S.room.append(_motes(W, H, 24, seed + 3, (200, 190, 170), size=(0.8, 1.6)))
        desk_col = (44, 30, 22)
        desk_edge = (150, 110, 60)

    # picture panel and its idle title
    inner, idle = draw_panel(c, L['panel'], theme, accent, title, rnd)
    S.panel = tuple(int(v) for v in inner)
    S.panel_idle = idle

    # light pooling behind the character and a soft vignette
    c.glow(L['char_x'], L['head_y'] + 40 * k, 360 * k, 330 * k, light(accent, 0.2), 0.22)
    vig = Image.new('L', (int(W * ss), int(H * ss)), 0)
    vd = ImageDraw.Draw(vig)
    steps = 24
    for i in range(steps):
        f = i / steps
        a = int(150 * (1 - f) ** 2.2)
        vd.rectangle([f * W * ss * 0.18, f * H * ss * 0.18, W * ss * (1 - f * 0.18), H * ss * (1 - f * 0.18)], outline=a, width=int(W * ss * 0.18 / steps) + 1)
    vig = vig.filter(ImageFilter.GaussianBlur(W * ss * 0.03))
    black = Image.new('RGBA', vig.size, (0, 0, 6, 255))
    black.putalpha(vig)
    c.im.alpha_composite(black)
    S.base = c.result().convert('RGB')

    # desk surface in front of the character (drawn on the desk layer under the props)
    desk_layer = Canvas(W, H, ss, (0, 0, 0, 0))
    dy = L['desk_y']
    desk_layer.rect(0, dy, W, H, fill=desk_col + (255,))
    desk_layer.rect(0, dy, W, dy + max(3, 5 * k), fill=desk_edge + (255,))
    desk_layer.trect(0, dy + 6 * k, W, dy + 40 * k, (0, 0, 0), 0.25, blur=6 * k)
    desk_layer.im.alpha_composite(dk.im)
    S.desk = desk_layer.result()
    S.desk_y = dy
    S.layout = L
    return S


# ----------------------------------------------------------------------------------------- open scenes (no desk)

OPEN_VIEWS = {
    'studio': ['city_night', 'rain_city'], 'christmas': ['snow_night'], 'halloween': ['moon_hills', 'dusk_castle'],
    'history': ['dusk_castle'], 'space': ['space'], 'tech': ['rain_city', 'city_night'], 'nature': ['forest_day'],
    'ocean': ['underwater'], 'mystery': ['rain_city'],
}
STAGES = ('room', 'open')


def build_open_set(theme, seed, W, H, title='', ss=2):
    """The character stands in the world itself: a full-screen environment (softly out of focus, like a camera with
    shallow depth of field), weather and particles, a spotlight, and a floating glass screen for pictures and titles."""
    theme = theme if theme in THEMES else 'studio'
    L = layout_for(W, H)
    rnd = random.Random(seed * 3 + 1)
    accent = THEMES[theme]['accent']
    k = L['k']
    S = SetScene()
    S.theme, S.accent, S.has_desk, S.stage = theme, accent, False, 'open'
    kind = rnd.choice(OPEN_VIEWS.get(theme, ['city_night']))
    view = view_image(kind, W, H, rnd, 1, accent).convert('RGB')
    view = view.filter(ImageFilter.GaussianBlur(max(1.0, 2.6 * k)))
    c = Canvas(W, H, 1, (0, 0, 0, 255))
    c.im.paste(view, (0, 0))
    # ground and light
    ground = {'space': (20, 18, 30), 'underwater': (10, 40, 60)}.get(kind, dark(mix(accent, (20, 20, 26), 0.8), 0.4))
    c.tpoly([(0, H * 0.80), (W, H * 0.80), (W, H), (0, H)], ground, 0.55, blur=H * 0.05)
    c.glow(L['char_x'], L['head_y'] + 60 * k, 420 * k, 420 * k, light(accent, 0.5), 0.20)
    c.glow(L['char_x'], H, 520 * k, 160 * k, (0, 0, 0), 0.55)
    # vignette
    vig = radial_mask((W, H)).point(lambda v: 255 - int(v * 0.85))
    black = Image.new('RGBA', (W, H), (0, 0, 6, 255))
    black.putalpha(vig.point(lambda v: int(v * 0.6)))
    c.im.alpha_composite(black)
    # floating glass screen for pictures and the scene title
    px0, py0, px1, py1 = L['panel']
    c.trect(px0, py0, px1, py1, (6, 10, 20), 0.62, blur=0)
    c.rect(px0, py0, px1, py1, outline=light(accent, 0.25) + (200,), w=max(2, 3 * k), r=14 * k)
    c.trect(px0, py0, px1, py0 + (py1 - py0) * 0.5, (255, 255, 255), 0.05)
    inner = (int(px0 + 10 * k), int(py0 + 10 * k), int(px1 - 10 * k), int(py1 - 10 * k))
    if title:
        size = (inner[3] - inner[1]) * 0.16
        words, lines, cur = title.upper().split(), [], ''
        for wd in words:
            if c.text_width(cur + ' ' + wd, size, 'black') > (inner[2] - inner[0]) * 0.85 and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + ' ' + wd).strip()
        lines.append(cur)
        cy = (inner[1] + inner[3]) / 2 - (len(lines) - 1) * size * 0.6
        for i, ln in enumerate(lines[:3]):
            c.text(((inner[0] + inner[2]) / 2, cy + i * size * 1.2), ln, size, (255, 255, 255, 255), 'black')
        c.rect((inner[0] + inner[2]) / 2 - 40 * k, cy + len(lines[:3]) * size * 1.2 - size * 0.3,
               (inner[0] + inner[2]) / 2 + 40 * k, cy + len(lines[:3]) * size * 1.2 - size * 0.3 + 5 * k, fill=accent + (255,), r=3)
    S.panel = inner
    S.panel_idle = c.im.crop(inner).convert('RGB')
    # weather and life
    full = (0, 0, W, H)
    if kind == 'snow_night':
        S.room.append(_snow_in(full, 70, seed, 1.0))
    elif kind in ('rain_city',):
        S.room.append(_rain_in(full, 90, seed))
    elif kind == 'space':
        S.back.append(_twinkle(full, 26, seed))
    elif kind == 'underwater':
        S.back.append(_fish((0, H * 0.35, W, H * 0.75), 5, seed))
        S.room.append(_bubbles(full, 18, seed))
    elif kind == 'forest_day':
        S.room.append(_motes(W, H, 28, seed + 3, (255, 236, 160), size=(1.0, 2.4)))
    elif kind in ('moon_hills', 'dusk_castle'):
        S.room.append(_motes(W, H, 24, seed + 3, (255, 150, 70), rise=True, size=(1.0, 2.0)))
    else:
        S.back.append(_twinkle(full, 14, seed))
    S.base = c.im.convert('RGB')
    S.desk = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    S.desk_y = H + 400 * k
    S.layout = L
    return S


def set_thumbnail(theme, seed, title='', W=480, H=270):
    """A quick still of the set (without the character) for the scene planner."""
    S = build_set(theme, seed, W, H, title, ss=1)
    img = S.base.copy()
    img.paste(S.desk, (0, 0), S.desk)
    S.draw_back(img, 0.3)
    S.draw_front(img, 0.3)
    return img
