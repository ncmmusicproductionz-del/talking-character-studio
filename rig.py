"""Character rig v2: pre-shaded sprites for the body, arms, hands and head, with outfits, hats,
colour variations and a big set of facial expressions.

Coordinates are the same "character units" as before (a 1000 x 1100 box). Sprites are built once per
style at the final pixel scale (supersampled, then downsampled), so each frame only moves, rotates and
pastes them, which is both nicer looking and faster than drawing shapes every frame.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import sets
from sets import dark, light, mix

CW, CH = 1000, 1100
PIVOT = (500, 540)
SHOULDER = {'L': (305, 600, -1), 'R': (695, 600, 1)}
UPPER, FORE = 170, 150
HEAD_WIN = (90, -330, 910, 660)
HEAD_SCALE = 1.12
EYE_Y = 388
VOID = (8, 9, 14)

COLORS = {
    'charcoal': (52, 54, 68), 'midnight': (30, 40, 80), 'black': (26, 26, 32), 'crimson': (152, 34, 46),
    'forest': (34, 94, 62), 'royal': (40, 72, 172), 'plum': (94, 46, 112), 'mustard': (206, 154, 42),
    'cream': (228, 216, 192), 'rose': (214, 112, 142), 'teal': (28, 122, 130), 'olive': (102, 106, 54),
    'sky': (92, 162, 222), 'white': (232, 234, 240), 'orange': (226, 112, 38), 'tan': (178, 142, 98),
}
ACCENTS = {
    'blue': (10, 140, 255), 'cyan': (40, 230, 230), 'mint': (80, 240, 170), 'lime': (160, 240, 60),
    'magenta': (255, 60, 200), 'violet': (150, 110, 255), 'orange': (255, 140, 40), 'gold': (255, 200, 60),
    'red': (255, 70, 70), 'white': (230, 236, 255),
}
OUTFITS = {
    'hoodie': 'Hoodie', 'zip': 'Zip hoodie', 'varsity': 'Varsity jacket', 'puffer': 'Puffer jacket',
    'sweater': 'Knit sweater', 'flannel': 'Flannel shirt', 'labcoat': 'Lab coat', 'suit': 'Suit',
    'trench': 'Trench coat', 'raincoat': 'Raincoat', 'astro': 'Space suit',
}
HATS = {
    'cap': 'Cap', 'cap_back': 'Backwards cap', 'beanie': 'Beanie', 'beanie_pom': 'Bobble hat', 'bucket': 'Bucket hat',
    'santa': 'Santa hat', 'witch': 'Witch hat', 'top': 'Top hat', 'wizard': 'Wizard hat', 'cowboy': 'Cowboy hat',
    'fedora': 'Fedora', 'captain': 'Captain hat', 'helmet': 'Space helmet', 'hood': 'Hood up', 'crown': 'Crown',
    'none': 'No hat',
}
HOOD_OUTFITS = {'hoodie', 'zip', 'raincoat'}
THEME_LOOKS = {
    'studio': dict(outfits=['hoodie', 'zip', 'varsity'], hats=['cap', 'cap_back', 'beanie'], colors=['charcoal', 'midnight', 'royal', 'black'], accents=['blue', 'cyan']),
    'christmas': dict(outfits=['sweater', 'puffer'], hats=['santa', 'beanie_pom'], colors=['crimson', 'forest'], accents=['gold', 'red']),
    'halloween': dict(outfits=['hoodie', 'trench'], hats=['witch', 'wizard'], colors=['plum', 'black', 'orange'], accents=['orange', 'lime']),
    'history': dict(outfits=['suit', 'trench'], hats=['top', 'fedora'], colors=['tan', 'charcoal', 'olive'], accents=['gold']),
    'space': dict(outfits=['astro'], hats=['helmet'], colors=['white'], accents=['violet', 'cyan']),
    'tech': dict(outfits=['zip', 'puffer', 'hoodie'], hats=['beanie', 'cap_back', 'hood'], colors=['black', 'midnight', 'teal'], accents=['cyan', 'magenta']),
    'nature': dict(outfits=['flannel', 'puffer'], hats=['bucket', 'beanie'], colors=['forest', 'olive', 'tan'], accents=['mint', 'lime']),
    'ocean': dict(outfits=['raincoat', 'sweater'], hats=['captain', 'bucket'], colors=['mustard', 'royal', 'white'], accents=['cyan', 'white']),
    'mystery': dict(outfits=['trench'], hats=['fedora'], colors=['tan', 'charcoal'], accents=['gold', 'orange']),
}
CLASSIC = dict(outfit='hoodie', hat='cap', color='charcoal', accent='blue')


def make_style(mode='classic', theme='studio', seed=0, custom=None):
    """mode: classic (your character sheet), theme (dressed for each set), random, or custom."""
    custom = custom or {}
    rnd = random.Random(int(seed) * 7919 + 13)
    if mode == 'custom':
        s = dict(outfit=custom.get('outfit', 'hoodie'), hat=custom.get('hat', 'cap'),
                 color=custom.get('color', 'charcoal'), accent=custom.get('accent', 'blue'))
    elif mode == 'theme':
        look = THEME_LOOKS.get(theme, THEME_LOOKS['studio'])
        s = dict(outfit=rnd.choice(look['outfits']), hat=rnd.choice(look['hats']), color=rnd.choice(look['colors']),
                 accent=rnd.choice(look['accents']))
    elif mode == 'random':
        s = dict(outfit=rnd.choice(list(OUTFITS)), hat=rnd.choice([h for h in HATS if h != 'helmet']),
                 color=rnd.choice(list(COLORS)), accent=rnd.choice(list(ACCENTS)))
    else:
        s = dict(CLASSIC)
    if s['outfit'] not in OUTFITS:
        s['outfit'] = 'hoodie'
    if s['hat'] not in HATS:
        s['hat'] = 'cap'
    if s['color'] not in COLORS:
        s['color'] = 'charcoal'
    if s['accent'] not in ACCENTS:
        s['accent'] = 'blue'
    if s['hat'] == 'helmet' and s['outfit'] != 'astro' and mode != 'custom':
        s['hat'] = 'cap'
    s['variant'] = rnd.randint(0, 9999)
    return s


def style_key(s):
    return (s['outfit'], s['hat'], s['color'], s['accent'], s.get('variant', 0))


# ----------------------------------------------------------------------------------------- painting helpers

def ramp(stops, w, h, axis='y'):
    n = 256
    row = Image.new('RGB', (n, 1))
    px = row.load()
    for i in range(n):
        f = i / (n - 1)
        for j in range(len(stops) - 1):
            p0, c0 = stops[j]
            p1, c1 = stops[j + 1]
            if f <= p1 or j == len(stops) - 2:
                tt = 0.0 if p1 == p0 else min(1.0, max(0.0, (f - p0) / (p1 - p0)))
                px[i, 0] = mix(c0, c1, tt)
                break
    if axis == 'x':
        return row.resize((max(1, w), max(1, h)), Image.BILINEAR)
    return row.rotate(-90, expand=True).resize((max(1, w), max(1, h)), Image.BILINEAR)


def _comp(c, layer, X0, Y0):
    W, H = c.im.size
    x0, y0 = max(0, X0), max(0, Y0)
    x1, y1 = min(W, X0 + layer.width), min(H, Y0 + layer.height)
    if x1 <= x0 or y1 <= y0:
        return
    part = layer.crop((x0 - X0, y0 - Y0, x1 - X0, y1 - Y0))
    c.im.alpha_composite(part, (x0, y0))


def paint(c, kind, geom, stops, axis='y', alpha=255, blur=0, extent=None):
    """Fill a shape with a colour ramp. kind: poly (pts), ellipse (cx, cy, rx, ry), rrect (x0, y0, x1, y1, r).
    extent: (x0, y0, x1, y1) the ramp spans (defaults to the shape's box)."""
    s = c.ss
    if kind == 'poly':
        xs = [p[0] for p in geom]
        ys = [p[1] for p in geom]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    elif kind == 'ellipse':
        cx, cy, rx, ry = geom
        bx0, by0, bx1, by1 = cx - rx, cy - ry, cx + rx, cy + ry
    else:
        bx0, by0, bx1, by1 = geom[:4]
    pad = blur * 3 + 2
    X0, Y0 = int((bx0 - pad) * s), int((by0 - pad) * s)
    X1, Y1 = int((bx1 + pad) * s) + 1, int((by1 + pad) * s) + 1
    w, h = max(1, X1 - X0), max(1, Y1 - Y0)
    m = Image.new('L', (w, h), 0)
    md = ImageDraw.Draw(m)
    if kind == 'poly':
        md.polygon([(x * s - X0, y * s - Y0) for x, y in geom], fill=alpha)
    elif kind == 'ellipse':
        md.ellipse([(cx - rx) * s - X0, (cy - ry) * s - Y0, (cx + rx) * s - X0, (cy + ry) * s - Y0], fill=alpha)
    else:
        md.rounded_rectangle([bx0 * s - X0, by0 * s - Y0, bx1 * s - X0, by1 * s - Y0], radius=geom[4] * s, fill=alpha)
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur * s))
    ex0, ey0, ex1, ey1 = extent or (bx0, by0, bx1, by1)
    row = list(ramp(stops, 256, 1, 'x').getdata())
    if axis == 'y':
        n, o, e0, span = h, Y0, ey0, max(1e-6, ey1 - ey0)
    else:
        n, o, e0, span = w, X0, ex0, max(1e-6, ex1 - ex0)
    data = [row[min(255, max(0, int(((o + j) / s - e0) / span * 255)))] for j in range(n)]
    strip = Image.new('RGB', (1, n) if axis == 'y' else (n, 1))
    strip.putdata(data)
    full = strip.resize((w, h), Image.NEAREST).convert('RGBA')
    full.putalpha(m)
    _comp(c, full, X0, Y0)


def bez(p0, p1, p2, p3, n=16):
    out = []
    for i in range(n + 1):
        t = i / n
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        cc = 3 * (1 - t) * t ** 2
        d = t ** 3
        out.append((a * p0[0] + b * p1[0] + cc * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + cc * p2[1] + d * p3[1]))
    return out


def _glow_line(c, pts, color, w, alpha):
    s = c.ss
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = w * 2 + 4
    X0, Y0 = int((min(xs) - pad) * s), int((min(ys) - pad) * s)
    X1, Y1 = int((max(xs) + pad) * s) + 1, int((max(ys) + pad) * s) + 1
    m = Image.new('L', (max(1, X1 - X0), max(1, Y1 - Y0)), 0)
    ImageDraw.Draw(m).line([(x * s - X0, y * s - Y0) for x, y in pts], fill=int(255 * alpha), width=max(1, int(w * s)), joint='curve')
    m = m.filter(ImageFilter.GaussianBlur(w * s * 0.6))
    layer = Image.new('RGBA', m.size, color + (255,))
    layer.putalpha(m)
    _comp(c, layer, X0, Y0)


def shade_stops(col, top=0.14, bottom=0.55):
    return [(0.0, light(col, top)), (0.35, col), (1.0, dark(col, bottom))]


def cyl_stops(col, rim=None):
    stops = [(0.0, dark(col, 0.55)), (0.32, light(col, 0.10)), (0.62, col), (0.9, dark(col, 0.7))]
    stops.append((1.0, mix(dark(col, 0.7), rim, 0.55) if rim else dark(col, 0.6)))
    return stops


# ----------------------------------------------------------------------------------------- the rig

class Rig:
    def __init__(self, style, k):
        self.style = style
        self.k = k
        self.body_col = COLORS[style['color']]
        self.accent = ACCENTS[style['accent']]
        self.outfit = style['outfit']
        self.hat = style['hat']
        rnd = random.Random(style.get('variant', 0))
        self.rnd = rnd
        self.second = self._second_color(rnd)
        self.glove = (230, 232, 238) if self.outfit == 'astro' else VOID
        self.sleeve = self._sleeve_color()
        self.torso = self._build_torso()
        head = self._build_head()
        bb = head.getbbox() or (0, 0, head.width, head.height)
        bb = (max(0, bb[0] - 4), max(0, bb[1] - 4), min(head.width, bb[2] + 4), min(head.height, bb[3] + 4))
        self.head = head.crop(bb)
        self.head_off = bb[:2]
        self._arm_cache = {}
        hx0, hy0, hx1, hy1 = HEAD_WIN
        self.head_px = (int((hx1 - hx0) * k * HEAD_SCALE), int((hy1 - hy0) * k * HEAD_SCALE))

    # ---------------------------------------------------------------- colours
    def _second_color(self, rnd):
        base = self.body_col
        lum = 0.3 * base[0] + 0.59 * base[1] + 0.11 * base[2]
        if self.outfit == 'varsity':
            return COLORS['cream'] if lum < 140 else COLORS['midnight']
        if self.outfit == 'sweater':
            return COLORS['white'] if lum < 150 else COLORS['crimson']
        if self.outfit == 'flannel':
            return dark(base, 0.55)
        return light(base, 0.35) if lum < 110 else dark(base, 0.7)

    def _sleeve_color(self):
        if self.outfit == 'varsity':
            return self.second
        if self.outfit == 'labcoat':
            return COLORS['white']
        if self.outfit == 'astro':
            return COLORS['white']
        if self.outfit == 'raincoat':
            return self.body_col
        return self.body_col

    def _main(self):
        if self.outfit == 'labcoat':
            return COLORS['white']
        if self.outfit == 'astro':
            return COLORS['white']
        return self.body_col

    # ---------------------------------------------------------------- torso
    def _build_torso(self):
        k = self.k
        c = sets.Canvas(CW, CH, 2 * k)
        col = self._main()
        acc = self.accent
        if self.outfit in HOOD_OUTFITS and self.hat != 'hood':
            paint(c, 'ellipse', (500, 470, 252, 192), shade_stops(dark(col, 0.75), 0.05, 0.6))
            c.tellipse(500, 500, 210, 150, (0, 0, 0), 0.35, blur=18)
        pts = [(390, 556)] + bez((390, 556), (318, 556), (232, 586), (212, 682)) + [(186, 1100), (814, 1100)] + \
            bez((788, 682), (768, 586), (682, 556), (610, 556))
        paint(c, 'poly', pts, shade_stops(col, 0.16, 0.55), extent=(186, 556, 814, 1100))
        c.tpoly([(186, 600), (300, 600), (290, 1100), (186, 1100)], (0, 0, 0), 0.22, blur=26)
        c.tpoly([(700, 600), (814, 600), (814, 1100), (710, 1100)], (0, 0, 0), 0.18, blur=26)
        c.tellipse(300, 615, 90, 34, (255, 255, 255), 0.10, blur=14)
        c.tellipse(700, 615, 90, 34, (255, 255, 255), 0.08, blur=14)
        c.tellipse(500, 585, 120, 40, (0, 0, 0), 0.45, blur=20)
        self._outfit_details(c, col)
        right = bez((788, 682), (768, 586), (682, 556), (640, 556))
        _glow_line(c, [(812, 1100), (788, 682)] + right[:8], acc, 10, 0.55)
        c.line([(812, 1100), (788, 682)] + right[:8], light(acc, 0.2) + (255,), 4)
        left = bez((212, 682), (232, 586), (318, 556), (360, 556))
        c.line([(188, 1100), (212, 682)] + left[:8], dark(acc, 0.6) + (255,), 4)
        return c.im.resize((round(CW * k), round(CH * k)), Image.LANCZOS)

    def _outfit_details(self, c, col):
        o = self.outfit
        acc = self.accent
        sec = self.second
        rnd = self.rnd
        line_col = dark(col, 0.6) + (255,)
        string = (214, 218, 228)
        if o in ('hoodie', 'zip', 'raincoat'):
            if o == 'zip':
                c.rect(495, 600, 505, 1100, fill=(150, 154, 166, 255))
                for y in range(610, 1100, 16):
                    c.rect(491, y, 509, y + 6, fill=(120, 124, 136, 255))
                c.rect(488, 680, 512, 720, fill=(200, 204, 214, 255), r=4)
            if o == 'raincoat':
                for y in (680, 790, 900, 1010):
                    c.rect(470, y, 530, y + 18, fill=dark(col, 0.65) + (255,), r=9)
                    c.ellipse(500, y + 9, 9, 9, fill=(70, 60, 50, 255))
            for x0, x1 in ((468, 458), (532, 542)):
                c.line([(x0, 575), (x0 + (x1 - x0) * 0.6, 640), (x1, 705)], string + (255,), 6)
                c.rect(x1 - 7, 700, x1 + 7, 728, fill=(230, 232, 238, 255), r=4)
            if o == 'hoodie':
                c.line(bez((330, 900), (420, 870), (580, 870), (670, 900)), line_col, 3)
                c.line([(330, 900), (300, 1100)], line_col, 3)
                c.line([(670, 900), (700, 1100)], line_col, 3)
                if rnd.random() < 0.5:
                    c.ellipse(640, 690, 26, 26, fill=acc + (255,))
                    mark = rnd.choice(['star', 'T', 'S', 'N'])
                    if mark == 'star':
                        c.poly(_star(640, 690, 18), (255, 255, 255, 255))
                    else:
                        c.text((640, 690), mark, 30, (255, 255, 255, 255), 'black')
        elif o == 'varsity':
            for i, y in enumerate((560, 572)):
                c.line(bez((390, y), (450, y + 30), (550, y + 30), (610, y)), (sec if i == 0 else acc) + (255,), 9)
            for y in range(640, 1100, 70):
                c.ellipse(560, y, 9, 9, fill=(236, 236, 240, 255))
            c.rect(330, 650, 430, 760, fill=sec + (255,), r=10)
            c.text((380, 705), rnd.choice(['T', 'S', 'C', 'A']), 74, col + (255,), 'black')
        elif o == 'puffer':
            for y in range(640, 1100, 64):
                c.line(bez((200, y), (380, y + 18), (620, y + 18), (800, y)), dark(col, 0.55) + (255,), 4)
                c.tellipse(500, y + 30, 300, 20, (255, 255, 255), 0.10, blur=10)
            c.rect(496, 590, 504, 1100, fill=(130, 134, 146, 255))
            paint(c, 'rrect', (400, 540, 600, 610, 30), shade_stops(col, 0.2, 0.4))
        elif o == 'sweater':
            paint(c, 'rrect', (410, 548, 590, 600, 22), shade_stops(dark(col, 0.85), 0.1, 0.4))
            for y in range(640, 1100, 22):
                for x in range(220, 790, 24):
                    c.line([(x, y), (x + 12, y + 10), (x + 24, y)], dark(col, 0.72) + (255,), 2)
            band_y = 700
            c.rect(205, band_y, 795, band_y + 70, fill=dark(col, 0.85) + (255,))
            for x in range(225, 790, 60):
                mx, my = x + 15, band_y + 35
                if rnd.random() < 0.6:
                    for a in (0, 60, 120):
                        ra = math.radians(a)
                        c.line([(mx - math.cos(ra) * 16, my - math.sin(ra) * 16), (mx + math.cos(ra) * 16, my + math.sin(ra) * 16)], sec + (255,), 4)
                else:
                    c.poly(_heart(mx, my, 1.1), sec + (255,))
            c.rect(205, band_y - 6, 795, band_y, fill=sec + (255,))
            c.rect(205, band_y + 70, 795, band_y + 76, fill=sec + (255,))
        elif o == 'flannel':
            for x in range(200, 820, 70):
                c.trect(x, 560, x + 22, 1100, sec, 0.45)
                c.trect(x + 32, 560, x + 36, 1100, light(col, 0.4), 0.35)
            for y in range(600, 1100, 70):
                c.trect(190, y, 810, y + 22, sec, 0.40)
                c.trect(190, y + 32, 810, y + 36, light(col, 0.4), 0.30)
            c.poly([(440, 556), (500, 640), (560, 556)], (230, 230, 236, 255))
            c.poly([(400, 556), (470, 556), (500, 640), (430, 640)], dark(col, 0.8) + (255,))
            c.poly([(600, 556), (530, 556), (500, 640), (570, 640)], dark(col, 0.8) + (255,))
            for y in range(670, 1100, 70):
                c.ellipse(500, y, 7, 7, fill=(240, 236, 226, 255))
        elif o in ('labcoat', 'suit', 'trench'):
            shirt = (236, 238, 244) if o != 'trench' else (60, 50, 44)
            c.poly([(430, 556), (570, 556), (540, 760), (460, 760)], shirt + (255,))
            if o == 'suit' or (o == 'labcoat' and rnd.random() < 0.5):
                tie = acc if o == 'suit' else (180, 40, 50)
                c.poly([(488, 590), (512, 590), (522, 610), (500, 625), (478, 610)], dark(tie, 0.8) + (255,))
                c.poly([(486, 622), (514, 622), (528, 760), (500, 790), (472, 760)], tie + (255,))
            lap = dark(col, 0.82) if o != 'labcoat' else (214, 218, 226)
            c.poly([(400, 556), (450, 556), (500, 800), (430, 690), (410, 640)], lap + (255,))
            c.poly([(600, 556), (550, 556), (500, 800), (570, 690), (590, 640)], lap + (255,))
            c.line([(450, 556), (500, 800)], dark(col, 0.6) + (255,), 2)
            c.line([(550, 556), (500, 800)], dark(col, 0.6) + (255,), 2)
            if o == 'trench':
                c.rect(200, 905, 800, 945, fill=dark(col, 0.75) + (255,))
                c.rect(475, 900, 525, 950, fill=(200, 170, 90, 255), r=4)
                for y in (820, 990):
                    for x in (440, 560):
                        c.ellipse(x, y, 9, 9, fill=dark(col, 0.5) + (255,))
            if o == 'labcoat':
                c.rect(600, 700, 690, 790, outline=(190, 196, 206, 255), w=3, r=4)
                c.rect(620, 670, 628, 720, fill=(40, 90, 200, 255), r=3)
            if o == 'suit':
                c.rect(600, 690, 680, 704, fill=(236, 238, 244, 255), r=3)
        elif o == 'astro':
            paint(c, 'rrect', (380, 650, 620, 820, 24), shade_stops((70, 76, 96), 0.15, 0.4))
            for i, bc in enumerate([(255, 70, 70), (255, 210, 60), (80, 220, 120), acc]):
                c.ellipse(420 + i * 54, 700, 14, 14, fill=bc + (255,))
            c.rect(410, 750, 590, 790, fill=(20, 26, 40, 255), r=8)
            for i in range(5):
                c.rect(420 + i * 34, 762, 440 + i * 34, 778, fill=acc + (255,), r=3)
            paint(c, 'ellipse', (500, 572, 140, 40), shade_stops((180, 186, 200), 0.3, 0.4))
            c.rect(205, 860, 795, 880, fill=(200, 205, 216, 255))
            c.poly(_star(300, 690, 22), acc + (255,))

    # ---------------------------------------------------------------- arms
    def _segment(self, length, width, color, forearm, hand, side):
        """A shaded arm segment hanging straight down from its joint. Returns (sprite, joint_x, joint_y) in pixels."""
        key = (length, width, forearm, hand, side)
        if key in self._arm_cache:
            return self._arm_cache[key]
        k = self.k
        r = width / 2
        Wd = max(width + 60, 170)
        top = r + 8
        Hd = top + length + (165 if forearm else r + 8)
        c = sets.Canvas(Wd, Hd, 2 * k)
        jx, jy = Wd / 2, top
        x0, x1 = jx - r, jx + r
        paint(c, 'rrect', (x0, jy - r, x1, jy + length + r, r), cyl_stops(color, self.accent), axis='x')
        c.tellipse(jx - r * 0.15, jy + length * 0.5, r * 0.22, length * 0.4, (255, 255, 255), 0.07, blur=8)
        if forearm:
            cuff_y = jy + length - 6
            if self.outfit in ('suit', 'labcoat'):
                paint(c, 'rrect', (x0 + 4, cuff_y - 18, x1 - 4, cuff_y + 14, 8), cyl_stops((236, 238, 244)), axis='x')
            elif self.outfit == 'astro':
                paint(c, 'rrect', (x0 - 2, cuff_y - 20, x1 + 2, cuff_y + 14, 10), cyl_stops((150, 156, 170), self.accent), axis='x')
            else:
                paint(c, 'rrect', (x0 + 2, cuff_y - 22, x1 - 2, cuff_y + 12, 10), cyl_stops(dark(color, 0.8), self.accent), axis='x')
                if self.outfit in ('varsity', 'sweater'):
                    c.rect(x0 + 2, cuff_y - 12, x1 - 2, cuff_y - 6, fill=(self.body_col if self.outfit == 'varsity' else self.second) + (255,))
            self._hand(c, jx, jy + length + 38, hand, side)
        else:
            c.line([(jx - r * 0.5, jy + length - 10), (jx + r * 0.4, jy + length - 2)], dark(color, 0.6) + (255,), 3)
        img = c.im.resize((max(1, round(Wd * k)), max(1, round(Hd * k))), Image.LANCZOS)
        if side == 'L':
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        out = (img, jx * k, jy * k)
        self._arm_cache[key] = out
        return out

    def _hand(self, c, x, y, kind, side):
        g = self.glove
        stops = [(0.0, light(g, 0.28)), (0.5, g), (1.0, dark(g, 0.6) if g != VOID else (2, 2, 4))]
        rimc = self.accent
        if kind == 'open':
            for i, a in enumerate((-38, -13, 12, 36)):
                ra = math.radians(a)
                fx, fy = x + math.sin(ra) * 50, y + math.cos(ra) * 50
                c.line([(x + math.sin(ra) * 18, y + math.cos(ra) * 18), (fx, fy)], g + (255,), 20)
            c.line([(x + 30, y - 6), (x + 62, y - 28)], g + (255,), 21)
            paint(c, 'ellipse', (x, y, 44, 41), stops)
        elif kind == 'point':
            paint(c, 'ellipse', (x, y, 46, 43), stops)
            c.line([(x - 6, y + 20), (x - 6, y + 92)], g + (255,), 22)
            c.ellipse(x - 6, y + 92, 11, 11, fill=g + (255,))
            c.line([(x + 30, y + 2), (x + 46, y + 18)], g + (255,), 18)
        elif kind == 'thumb':
            paint(c, 'ellipse', (x, y, 46, 43), stops)
            c.line([(x - 4, y + 24), (x - 6, y + 82)], g + (255,), 26)
            c.ellipse(x - 6, y + 82, 13, 13, fill=g + (255,))
        else:
            paint(c, 'ellipse', (x, y + 4, 48, 45), stops)
            for i in range(3):
                c.line([(x - 22 + i * 18, y + 30), (x - 18 + i * 18, y + 40)], dark(g, 0.5) + (255,) if g != VOID else (40, 44, 60, 255), 2)
        c.d.arc(c._b(x - 48, y - 42, x + 48, y + 49), -60, 60, fill=rimc + (255,), width=max(1, int(4 * c.ss)))

    def _paste_arm(self, frame, ox, oy, side, a1, a2, hand, shrug):
        k = self.k
        sx, sy, dr = SHOULDER[side]
        sy -= shrug * 22
        r1 = math.radians(a1)
        ex = sx + dr * math.sin(r1) * UPPER
        ey = sy + math.cos(r1) * UPPER
        width = 74
        up = self._segment(UPPER, width, self.sleeve, False, None, side)
        fo = self._segment(FORE, width - 6, self.sleeve, True, hand, side)
        for (img, jx, jy), px, py, ang in ((up, sx, sy, a1), (fo, ex, ey, a2)):
            th = dr * ang
            rot = img.rotate(th, resample=Image.BILINEAR, expand=True)
            vx, vy = jx - img.width / 2, jy - img.height / 2
            cr, sr = math.cos(math.radians(th)), math.sin(math.radians(th))
            rx = rot.width / 2 + vx * cr + vy * sr
            ry = rot.height / 2 - vx * sr + vy * cr
            frame.paste(rot, (int(ox + px * k - rx), int(oy + py * k - ry)), rot)

    def paste_body(self, frame, ox, oy, st):
        """Torso and the arms that are behind the desk/head. ox, oy: pixel position of the character box."""
        dy = st.get('dy', 0.0) * self.k
        dx = st.get('dx', 0.0) * self.k
        frame.paste(self.torso, (int(ox + dx), int(oy + dy)), self.torso)
        front = st.get('front', ())
        for side in ('L', 'R'):
            if side not in front:
                a1, a2 = st['arms'][side]
                self._paste_arm(frame, ox + dx, oy + dy, side, a1, a2, st['hands'][side], st.get('shrug', 0))

    def paste_front(self, frame, ox, oy, st):
        dy = st.get('dy', 0.0) * self.k
        dx = st.get('dx', 0.0) * self.k
        for side in st.get('front', ()):
            a1, a2 = st['arms'][side]
            self._paste_arm(frame, ox + dx, oy + dy, side, a1, a2, st['hands'][side], st.get('shrug', 0))

    # ---------------------------------------------------------------- head
    def _build_head(self):
        k = self.k * HEAD_SCALE
        hx0, hy0, hx1, hy1 = HEAD_WIN
        w, h = hx1 - hx0, hy1 - hy0
        c = sets.Canvas(w, h, 2 * k)
        self._oxy = (hx0, hy0)
        T = lambda x, y: (x - hx0, y - hy0)

        def E(cx, cy, rx, ry):
            x, y = T(cx, cy)
            return (x, y, rx, ry)

        col = self._main()
        acc = self.accent
        hood = self.outfit in HOOD_OUTFITS
        if self.hat == 'hood':
            paint(c, 'ellipse', E(500, 380, 242, 232), shade_stops(col, 0.15, 0.5))
            c.tellipse(*T(500, 400), 200, 185, (0, 0, 0), 0.6, blur=14)
        elif hood:
            paint(c, 'ellipse', E(500, 392, 234, 202), shade_stops(col, 0.12, 0.5))
            c.tellipse(*T(500, 400), 190, 170, (0, 0, 0), 0.5, blur=14)
        elif not hood:
            x0, y0 = T(452, 505)
            paint(c, 'rrect', (x0, y0, x0 + 96, y0 + 64, 26), [(0.0, (30, 32, 44)), (1.0, (10, 11, 16))])
        # head
        paint(c, 'ellipse', E(500, 385, 178, 160), [(0.0, (26, 30, 46)), (0.4, VOID), (1.0, (2, 2, 6))])
        c.tellipse(*T(445, 315), 95, 55, (90, 110, 170), 0.16, blur=22)
        hx, hy = T(500, 385)
        _glow_line(c, [(hx + math.cos(math.radians(a)) * 176, hy + math.sin(math.radians(a)) * 158) for a in range(-55, 70, 5)], acc, 12, 0.6)
        c.line([(hx + math.cos(math.radians(a)) * 176, hy + math.sin(math.radians(a)) * 158) for a in range(-55, 70, 5)], light(acc, 0.15) + (255,), 5)

        tall = self.hat in ('witch', 'wizard', 'top', 'cowboy', 'fedora', 'captain', 'santa', 'crown', 'bucket')
        if tall:
            self._headphones(c, T, band=True, cups=False)
            self._hat(c, T)
            self._headphones(c, T, band=False, cups=True)
        elif self.hat == 'hood':
            self._headphones(c, T, band=True, cups=False)
            self._hat(c, T)
            self._headphones(c, T, band=False, cups=True)
        else:
            self._hat(c, T)
            self._headphones(c, T, band=True, cups=True)
        if self.hat == 'helmet':
            self._helmet(c, T)
        return c.im.resize((round(w * k), round(h * k)), Image.LANCZOS)

    def _headphones(self, c, T, band, cups):
        acc = self.accent
        if band:
            x0, y0 = T(272, 52)
            x1, y1 = T(728, 480)
            c.d.arc(c._b(x0, y0, x1, y1), 180, 360, fill=(30, 32, 44, 255), width=int(34 * c.ss))
            c.d.arc(c._b(x0 + 6, y0 + 4, x1 - 6, y1 - 4), 195, 345, fill=(70, 74, 92, 255), width=int(5 * c.ss))
            x0, y0 = T(286, 66)
            x1, y1 = T(714, 466)
            c.d.arc(c._b(x0, y0, x1, y1), 200, 340, fill=acc + (255,), width=int(4 * c.ss))
        if cups:
            for cx in (290, 710):
                x, y = T(cx, 397)
                c.glow(x, y, 90, 120, acc, 0.35)
                paint(c, 'ellipse', (x, y, 52, 78), [(0.0, (70, 74, 92)), (0.5, (32, 34, 46)), (1.0, (14, 15, 22))])
                c.d.ellipse(c._b(x - 52, y - 78, x + 52, y + 78), outline=acc + (255,), width=int(9 * c.ss))
                c.tellipse(x - 14, y - 34, 18, 26, (255, 255, 255), 0.18, blur=4)

    def _hat(self, c, T):
        h = self.hat
        acc = self.accent
        rnd = self.rnd
        body = self.body_col
        hc = {'cap': (24, 26, 36), 'cap_back': dark(body, 0.8), 'beanie': rnd.choice([dark(body, 0.8), (200, 60, 50), (40, 60, 120), (230, 200, 70)]),
              'beanie_pom': rnd.choice([(200, 40, 50), (40, 110, 70), (230, 230, 236)]), 'bucket': rnd.choice([(200, 180, 130), (60, 90, 60), (40, 50, 90)]),
              'santa': (196, 30, 40), 'witch': rnd.choice([(30, 22, 40), (60, 30, 90)]), 'top': (22, 22, 28), 'wizard': rnd.choice([(40, 50, 140), (90, 40, 140)]),
              'cowboy': (140, 96, 54), 'fedora': rnd.choice([(70, 58, 46), (40, 40, 48), (130, 110, 80)]), 'captain': (240, 240, 244), 'crown': (240, 190, 60),
              'hood': self._main()}.get(h, (24, 26, 36))
        st = shade_stops(hc, 0.18, 0.5)

        def P(*pts):
            return [T(x, y) for x, y in pts]

        if h in ('cap', 'cap_back'):
            crown = [T(500 + math.cos(math.radians(a)) * 190, 280 + math.sin(math.radians(a)) * 160) for a in range(180, 361, 6)]
            paint(c, 'poly', crown, st)
            c.line([T(500, 125), T(500, 280)], dark(hc, 0.6) + (255,), 3)
            c.ellipse(*T(500, 122), 13, 10, fill=light(hc, 0.2) + (255,))
            if h == 'cap':
                paint(c, 'ellipse', (*T(500, 300), 212, 38), [(0.0, light(hc, 0.25)), (0.6, hc), (1.0, dark(hc, 0.5))])
                x0, y0 = T(288, 262)
                x1, y1 = T(712, 338)
                c.d.arc(c._b(x0, y0, x1, y1), 15, 165, fill=acc + (255,), width=int(5 * c.ss))
            else:
                paint(c, 'rrect', (*T(440, 250), *T(560, 290), 16), [(0.0, VOID), (1.0, VOID)])
                c.rect(*T(440, 266), *T(560, 274), fill=acc + (255,))
                paint(c, 'poly', P((300, 265), (700, 265), (690, 290), (310, 290)), st)
        elif h in ('beanie', 'beanie_pom'):
            dome = [T(500 + math.cos(math.radians(a)) * 194, 300 + math.sin(math.radians(a)) * 170) for a in range(180, 361, 6)]
            paint(c, 'poly', dome, st)
            for x in range(320, 690, 22):
                c.line([T(x, 150 + abs(x - 500) * 0.5), T(x, 290)], dark(hc, 0.82) + (255,), 2)
            paint(c, 'rrect', (*T(298, 270), *T(702, 336), 20), shade_stops(dark(hc, 0.9), 0.15, 0.4))
            for x in range(312, 690, 16):
                c.line([T(x, 276), T(x, 330)], dark(hc, 0.7) + (255,), 2)
            if h == 'beanie_pom':
                for _ in range(26):
                    a = rnd.uniform(0, 6.28)
                    r = rnd.uniform(0, 34)
                    c.ellipse(*T(500 + math.cos(a) * r, 120 + math.sin(a) * r), 16, 16, fill=light(hc, rnd.uniform(0.1, 0.5)) + (255,))
        elif h == 'bucket':
            paint(c, 'poly', P((352, 168), (648, 168), (684, 300), (316, 300)), st)
            paint(c, 'ellipse', (*T(500, 305), 250, 52), [(0.0, light(hc, 0.2)), (0.5, hc), (1.0, dark(hc, 0.55))])
            c.rect(*T(318, 270), *T(682, 292), fill=dark(hc, 0.7) + (255,))
            c.line([T(330, 320), T(670, 320)], dark(hc, 0.7) + (255,), 2)
        elif h == 'santa':
            body_pts = [T(310, 300)] + [T(x, y) for x, y in bez((310, 300), (360, 120), (560, 60), (780, 170), 18)] + \
                       [T(x, y) for x, y in bez((780, 170), (660, 150), (640, 220), (690, 300), 10)]
            paint(c, 'poly', body_pts, st)
            c.tpoly([T(560, 120), T(690, 160), T(650, 300), T(560, 300)], (0, 0, 0), 0.18, blur=10)
            for i in range(14):
                x = 300 + i * 30
                c.ellipse(*T(x, 305 + math.sin(i) * 4), 28, 26, fill=(246, 246, 250, 255))
            for _ in range(20):
                a = rnd.uniform(0, 6.28)
                r = rnd.uniform(0, 30)
                c.ellipse(*T(790 + math.cos(a) * r, 178 + math.sin(a) * r), 16, 16, fill=(250, 250, 252, 255))
        elif h == 'witch':
            paint(c, 'ellipse', (*T(500, 312), 290, 48), [(0.0, light(hc, 0.2)), (0.5, hc), (1.0, dark(hc, 0.5))])
            cone = [T(360, 300)] + [T(x, y) for x, y in bez((360, 300), (420, 120), (520, -60), (650, -150), 18)] + \
                   [T(x, y) for x, y in bez((650, -150), (580, -40), (610, 140), (640, 300), 14)]
            paint(c, 'poly', cone, st)
            c.rect(*T(365, 255), *T(635, 292), fill=acc + (255,))
            c.rect(*T(470, 250), *T(530, 297), outline=(240, 200, 80, 255), w=6, r=4)
        elif h == 'top':
            paint(c, 'ellipse', (*T(500, 305), 220, 36), [(0.0, light(hc, 0.25)), (0.5, hc), (1.0, dark(hc, 0.4))])
            paint(c, 'rrect', (*T(360, 20), *T(640, 300), 10), cyl_stops(hc), axis='x')
            paint(c, 'ellipse', (*T(500, 22), 140, 26), [(0.0, light(hc, 0.3)), (1.0, hc)])
            c.rect(*T(360, 236), *T(640, 278), fill=acc + (255,))
        elif h == 'wizard':
            cone = [T(330, 312)] + [T(x, y) for x, y in bez((330, 312), (420, 100), (480, -120), (530, -230), 18)] + \
                   [T(x, y) for x, y in bez((530, -230), (560, -100), (620, 120), (670, 312), 16)]
            paint(c, 'poly', cone, st)
            paint(c, 'ellipse', (*T(500, 316), 230, 34), [(0.0, light(hc, 0.2)), (1.0, dark(hc, 0.5))])
            for _ in range(7):
                x, y = rnd.uniform(400, 600), rnd.uniform(-80, 270)
                c.poly([T(px, py) for px, py in _star(x, y, rnd.uniform(12, 22))], (255, 220, 90, 255))
        elif h == 'cowboy':
            brim = [T(x, y) for x, y in bez((180, 260), (280, 360), (720, 360), (820, 260), 20)] + \
                   [T(x, y) for x, y in bez((820, 260), (700, 320), (300, 320), (180, 260), 20)]
            paint(c, 'poly', brim, st)
            paint(c, 'poly', P((360, 300), (370, 150), (450, 120), (500, 150), (550, 120), (630, 150), (640, 300)), st)
            c.rect(*T(362, 262), *T(638, 290), fill=dark(hc, 0.55) + (255,))
        elif h == 'fedora':
            paint(c, 'ellipse', (*T(500, 310), 240, 40), [(0.0, light(hc, 0.2)), (0.5, hc), (1.0, dark(hc, 0.5))])
            paint(c, 'poly', P((365, 300), (380, 170), (450, 140), (500, 165), (550, 140), (620, 170), (635, 300)), st)
            c.rect(*T(366, 256), *T(634, 290), fill=dark(hc, 0.45) + (255,))
            c.rect(*T(366, 256), *T(634, 262), fill=acc + (255,))
        elif h == 'captain':
            paint(c, 'poly', P((320, 300), (300, 200), (500, 150), (700, 200), (680, 300)), st)
            c.rect(*T(320, 262), *T(680, 300), fill=(24, 26, 36, 255))
            paint(c, 'ellipse', (*T(500, 310), 170, 26), [(0.0, (60, 60, 70)), (1.0, (10, 10, 14))])
            c.ellipse(*T(500, 225), 30, 26, fill=(230, 190, 70, 255))
            c.poly([T(px, py) for px, py in _star(500, 225, 18)], (24, 26, 36, 255))
        elif h == 'crown':
            pts = P((330, 300), (330, 180), (400, 240), (450, 150), (500, 220), (550, 150), (600, 240), (670, 180), (670, 300))
            paint(c, 'poly', pts, [(0.0, (255, 230, 120)), (0.5, (240, 190, 60)), (1.0, (170, 120, 30))])
            for x, gc in ((400, (220, 40, 60)), (500, (40, 120, 230)), (600, (40, 190, 100))):
                c.ellipse(*T(x, 272), 14, 14, fill=gc + (255,))
            for x in (330, 450, 550, 670):
                c.ellipse(*T(x, 160 if x in (450, 550) else 178), 10, 10, fill=(255, 240, 160, 255))
        elif h == 'hood':
            # the hood's back is painted behind the head in _build_head; this is the brow that frames the face
            outer = [T(500 + math.cos(math.radians(a)) * 242, 382 + math.sin(math.radians(a)) * 232) for a in range(195, 346, 5)]
            inner = [T(500 + math.cos(math.radians(a)) * 182, 392 + math.sin(math.radians(a)) * 150) for a in range(340, 199, -5)]
            paint(c, 'poly', outer + inner, shade_stops(hc, 0.2, 0.45))
            c.tpoly(inner + [T(x, y + 30) for x, y in reversed(inner)], (0, 0, 0), 0.45, blur=8)
            c.line(inner, self.accent + (255,), 4)

    def _helmet(self, c, T):
        acc = self.accent
        x, y = T(500, 380)
        c.tellipse(x, y, 290, 280, (170, 210, 255), 0.10)
        c.d.ellipse(c._b(x - 290, y - 280, x + 290, y + 280), outline=(220, 235, 255, 200), width=int(6 * c.ss))
        c.d.arc(c._b(x - 250, y - 240, x + 250, y + 240), 200, 250, fill=(255, 255, 255, 170), width=int(14 * c.ss))
        c.tellipse(x + 150, y - 150, 30, 20, (255, 255, 255), 0.5, blur=4)
        paint(c, 'rrect', (*T(300, 600), *T(700, 650), 24), shade_stops((190, 196, 210), 0.3, 0.4))
        c.rect(*T(310, 620), *T(690, 628), fill=acc + (255,))

    # ---------------------------------------------------------------- eyes and expressions
    def _rotated_head(self, tilt, pv):
        cache = self.__dict__.setdefault('_rot_cache', {})
        if tilt not in cache:
            if len(cache) >= 28:
                cache.pop(next(iter(cache)))
            cache[tilt] = self.head if tilt == 0 else self.head.rotate(tilt, center=pv, resample=Image.BILINEAR)
        return cache[tilt]

    def paste_head(self, frame, ox, oy, st, t):
        k = self.k * HEAD_SCALE
        hx0, hy0, hx1, hy1 = HEAD_WIN
        ox0, oy0 = self.head_off
        T0 = lambda x, y: ((x - hx0) * k - ox0, (y - hy0) * k - oy0)
        pv = T0(*PIVOT)
        tilt = round(st.get('tilt', 0.0) * 2) / 2          # half-degree steps, so rotated heads can be reused
        head = self._rotated_head(tilt, pv).copy()
        th = math.radians(tilt)
        ct, sn = math.cos(th), math.sin(th)

        def T(x, y):
            X, Y = T0(x, y)
            ddx, ddy = X - pv[0], Y - pv[1]
            return (pv[0] + ddx * ct + ddy * sn, pv[1] - ddx * sn + ddy * ct)
        draw_cups(head, T, k, self.accent, st.get('glow', 0.4))
        draw_face(head, T, k, st, self.accent, t, T0=T0, angle=tilt)
        bk = self.k
        px = ox + PIVOT[0] * bk - pv[0] + (st.get('dx', 0) + st.get('head_dx', 0)) * bk
        py = oy + PIVOT[1] * bk - pv[1] + (st.get('dy', 0) + st.get('head_dy', 0) - st.get('shrug', 0) * 6) * bk
        frame.paste(head, (int(px), int(py)), head)


def _comp_img(img, layer, x, y):
    """alpha_composite that tolerates the layer hanging over the edge."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.width, x + layer.width), min(img.height, y + layer.height)
    if x1 > x0 and y1 > y0:
        img.alpha_composite(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def draw_cups(img, T, k, acc, glow):
    d = ImageDraw.Draw(img)
    g = max(0.0, min(1.0, glow))
    col = mix(dark(acc, 0.55), light(acc, 0.35), g)
    for cx in (290, 710):
        x, y = T(cx, 397)
        r = (22 + 8 * g) * k
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        d.ellipse([x - r * 0.45, y - r * 0.6, x - r * 0.05, y - r * 0.2], fill=light(col, 0.5))


# eye looks: kind, openness, tilt, extras
EXPRESSIONS = {
    'normal': dict(kind='angular'),
    'happy': dict(kind='happy'),
    'excited': dict(kind='wide', open=1.05),
    'surprised': dict(kind='wide', open=1.2, small=True),
    'angry': dict(kind='angular', open=0.85, tilt=18),
    'mad': dict(kind='angular', open=0.8, tilt=22, extras=('vein',)),
    'think': dict(kind='angular', tilt=-8, look=(-6, -4), right_open=0.6),
    'tired': dict(kind='angular', open=0.45, tilt=-6),
    'sleepy': dict(kind='line', extras=('zzz',)),
    'focused': dict(kind='angular', open=0.7, tilt=6),
    'determined': dict(kind='angular', open=0.75, tilt=12),
    'sad': dict(kind='angular', open=0.85, tilt=-18),
    'cry': dict(kind='angular', open=0.8, tilt=-20, extras=('tears',)),
    'wink': dict(kind='wink'),
    'love': dict(kind='heart', extras=('blush', 'hearts')),
    'amazed': dict(kind='star', extras=('sparkles',)),
    'dizzy': dict(kind='spiral'),
    'shocked': dict(kind='ring', extras=('sweat',)),
    'suspicious': dict(kind='half', look=(8, 0)),
    'laugh': dict(kind='happy', extras=('blush',), bounce=True),
    'confused': dict(kind='confused', extras=('question',)),
    'cool': dict(kind='shades'),
}


def _eye_poly(cx, cy, side, open_, tilt, scale=1.0):
    base = [(-46, -30), (38, -6), (30, 30), (-36, 22)]
    ang = math.radians(tilt if side < 0 else -tilt)
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for x, y in base:
        y *= max(open_, 0.07)
        if side > 0:
            x = -x
        x, y = x * scale, y * scale
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


def _heart(cx, cy, s):
    pts = []
    for i in range(40):
        t = i / 40 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s, cy + y * s))
    return pts


def _star(cx, cy, r):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return pts


def draw_face(img, T, k, st, acc, t, T0=None, angle=0.0):
    """Eyes and expression extras, drawn onto the head sprite (in head units via T).
    When the head is already rotated by `angle`, T maps into the rotated head and T0 into the upright one: the eye layer is
    drawn upright with T0 and then rotated, which is much cheaper than rotating the whole head every frame."""
    T_draw = T0 or T
    name = st.get('emotion', 'normal')
    ex = EXPRESSIONS.get(name, EXPRESSIONS['normal'])
    open_mul = st.get('open', 1.0)
    lx, ly = st.get('look', (0, 0))
    elx, ely = ex.get('look', (0, 0))
    lx += elx
    ly += ely
    kind = ex['kind']
    glow_col = light(acc, 0.45)
    # supersampled eye layer
    SSF = 2
    bx0, by0 = T_draw(330, 300)
    bx1, by1 = T_draw(670, 480)
    w, h = int(bx1 - bx0), int(by1 - by0)
    layer = Image.new('RGBA', (w * SSF, h * SSF), (0, 0, 0, 0))
    mask = Image.new('L', (w * SSF, h * SSF), 0)
    md = ImageDraw.Draw(mask)
    ld = ImageDraw.Draw(layer)

    def P(x, y):
        X, Y = T_draw(x, y)
        return ((X - bx0) * SSF, (Y - by0) * SSF)

    s = k * SSF
    white = (250, 252, 255, 255)
    for side, cx in ((-1, 430), (1, 570)):
        x = cx + lx
        y = EYE_Y + ly
        o = max(0.06, ex.get('open', 1.0) * open_mul)
        if side > 0 and 'right_open' in ex:
            o = max(0.06, ex['right_open'] * open_mul)
        k_here = kind
        if kind == 'wink' and side > 0:
            k_here = 'happy'
        elif kind == 'wink':
            k_here = 'angular'
        if kind == 'confused':
            k_here = 'angular'
        tilt = ex.get('tilt', 0)
        if kind == 'confused':
            tilt = 14 if side < 0 else -14
        if k_here == 'angular' or k_here == 'half':
            if k_here == 'half':
                o = min(o, 0.45)
            pts = [P(*p) for p in _eye_poly(x, y, side, o, tilt)]
            md.polygon(pts, fill=255)
            ld.polygon(pts, fill=white)
            if k_here == 'half':
                a, b = P(x - 48, y - 6), P(x + 48, y - 6)
                ld.line([a, b], fill=glow_col + (255,), width=max(1, int(5 * s)))
        elif k_here == 'happy':
            box = [*P(x - 44, y - 36), *P(x + 44, y + 36)]
            md.arc(box, 200, 340, fill=255, width=max(1, int(16 * s)))
            ld.arc(box, 200, 340, fill=white, width=max(1, int(15 * s)))
        elif k_here == 'wide':
            rx, ry = 40, 50 * min(o, 1.3)
            box = [*P(x - rx, y - ry), *P(x + rx, y + ry)]
            md.ellipse(box, fill=255)
            ld.ellipse(box, fill=white)
            if ex.get('small'):
                pr = 9
                ld.ellipse([*P(x - pr, y - pr), *P(x + pr, y + pr)], fill=(20, 24, 40, 255))
        elif k_here == 'line':
            a, b = P(x - 40, y + 4), P(x + 40, y + 4)
            md.line([a, b], fill=255, width=max(1, int(12 * s)))
            ld.line([a, b], fill=white, width=max(1, int(10 * s)))
        elif k_here == 'heart':
            beat = 1 + 0.08 * math.sin(t * 8)
            pts = [P(*p) for p in _heart(x, y + 4, 2.6 * beat)]
            md.polygon(pts, fill=255)
            ld.polygon(pts, fill=(255, 90, 140, 255))
        elif k_here == 'star':
            pts = [P(*p) for p in _star(x, y, 46 * (1 + 0.06 * math.sin(t * 6 + side)))]
            md.polygon(pts, fill=255)
            ld.polygon(pts, fill=(255, 230, 90, 255))
        elif k_here == 'spiral':
            pts = []
            for i in range(60):
                a = i * 0.32 + t * 6 * side
                r = 3 + i * 0.7
                pts.append(P(x + math.cos(a) * r, y + math.sin(a) * r))
            md.line(pts, fill=255, width=max(1, int(8 * s)))
            ld.line(pts, fill=white, width=max(1, int(7 * s)))
        elif k_here == 'ring':
            box = [*P(x - 38, y - 44), *P(x + 38, y + 44)]
            md.ellipse(box, outline=255, width=max(1, int(12 * s)))
            ld.ellipse(box, outline=white, width=max(1, int(10 * s)))
            pr = 8
            ld.ellipse([*P(x - pr, y - pr), *P(x + pr, y + pr)], fill=white)
        elif k_here == 'shades':
            pass
    if kind == 'shades':
        lens = [P(368, 360), P(492, 360), P(486, 420), P(380, 420)]
        lens2 = [P(508, 360), P(632, 360), P(620, 420), P(514, 420)]
        for L in (lens, lens2):
            ld.polygon(L, fill=(14, 16, 26, 255), outline=glow_col + (255,), width=max(1, int(4 * s)))
            md.polygon(L, fill=120)
        ld.line([P(492, 372), P(508, 372)], fill=(40, 44, 60, 255), width=max(1, int(8 * s)))
        ld.line([P(380, 372), P(430, 368)], fill=(255, 255, 255, 140), width=max(1, int(5 * s)))
        ld.line([P(520, 372), P(570, 368)], fill=(255, 255, 255, 140), width=max(1, int(5 * s)))
    # glow is blurred at final size (4x fewer pixels than the supersampled layer)
    glow = mask.resize((w, h), Image.BILINEAR, reducing_gap=2.0).filter(ImageFilter.GaussianBlur(9 * k))
    gl = Image.new('RGBA', (w, h), glow_col + (255,))
    gl.putalpha(glow.point(lambda v: int(v * 0.9)))
    gl.alpha_composite(layer.resize((w, h), Image.BILINEAR, reducing_gap=2.0))
    if abs(angle) > 0.01:
        cx0, cy0 = (bx0 + bx1) / 2, (by0 + by1) / 2
        cx, cy = T(500, 390)
        gl = gl.rotate(angle, resample=Image.BILINEAR, expand=True)
        dx, dy = cx - gl.width / 2, cy - gl.height / 2
    else:
        dx, dy = bx0, by0
    _comp_img(img, gl, int(dx), int(dy))

    draw_extras(img, T, k, ex.get('extras', ()), acc, t)


def draw_extras(img, T, k, extras, acc, t):
    """Blush, tears, hearts, zzz and the other little expression effects, in head units via T."""
    if not extras:
        return
    d = ImageDraw.Draw(img)
    if 'blush' in extras:
        pad = int(30 * k) + 2
        m = Image.new('L', (int(110 * k) + 2 * pad, int(50 * k) + 2 * pad), 0)
        ImageDraw.Draw(m).ellipse([pad, pad, m.width - pad, m.height - pad], fill=130)
        m = m.filter(ImageFilter.GaussianBlur(10 * k))
        bl = Image.new('RGBA', m.size, (255, 90, 140, 255))
        bl.putalpha(m)
        for cx in (400, 600):
            X, Y = T(cx, 452)
            pos = (int(X - bl.width / 2), int(Y - bl.height / 2))
            if img.mode == 'RGBA':
                _comp_img(img, bl, *pos)
            else:
                img.paste(bl, pos, bl)
    if 'tears' in extras:
        for i, cx in enumerate((420, 580)):
            u = (t * 0.9 + i * 0.45) % 1.0
            X, Y = T(cx + (-6 if i == 0 else 6), 420 + u * 110)
            r = 9 * k
            d.ellipse([X - r, Y - r, X + r, Y + r * 1.4], fill=(120, 190, 255))
            d.polygon([(X - r * 0.8, Y - r * 0.2), (X + r * 0.8, Y - r * 0.2), (X, Y - r * 2.2)], fill=(120, 190, 255))
    if 'sweat' in extras:
        X, Y = T(650, 300 + (t * 20) % 20)
        r = 12 * k
        d.ellipse([X - r, Y - r, X + r, Y + r * 1.3], fill=(150, 210, 255))
        d.polygon([(X - r * 0.8, Y - r * 0.3), (X + r * 0.8, Y - r * 0.3), (X, Y - r * 2.4)], fill=(150, 210, 255))
    if 'vein' in extras:
        X, Y = T(640, 300)
        r = 22 * k * (1 + 0.15 * math.sin(t * 10))
        for a in (0, 90, 180, 270):
            ra = math.radians(a + 45)
            d.arc([X + math.cos(ra) * r - r, Y + math.sin(ra) * r - r, X + math.cos(ra) * r + r, Y + math.sin(ra) * r + r],
                  a + 45 + 90, a + 45 + 270, fill=(255, 60, 60), width=max(2, int(6 * k)))
    if 'zzz' in extras:
        f = sets.font(int(46 * k), 'black')
        for i in range(3):
            u = (t * 0.5 + i / 3) % 1.0
            X, Y = T(640 + u * 120, 300 - u * 160)
            d.text((X, Y), 'z', font=sets.font(int((30 + u * 30) * k), 'black'), fill=(220, 230, 255), anchor='mm')
    if 'hearts' in extras:
        for i in range(3):
            u = (t * 0.6 + i / 3) % 1.0
            X, Y = T(640 + math.sin(u * 6 + i) * 30, 330 - u * 200)
            pts = [(X + px * k, Y + py * k) for px, py in _heart(0, 0, 1.3 * (1 - u * 0.4))]
            d.polygon(pts, fill=(255, 90, 140))
    if 'sparkles' in extras:
        for i in range(4):
            u = (t * 1.2 + i / 4) % 1.0
            X, Y = T(360 + i * 95, 270 - math.sin(u * math.pi) * 30)
            r = (6 + 14 * math.sin(u * math.pi)) * k
            d.polygon([(X, Y - r), (X + r * 0.3, Y - r * 0.3), (X + r, Y), (X + r * 0.3, Y + r * 0.3), (X, Y + r),
                       (X - r * 0.3, Y + r * 0.3), (X - r, Y), (X - r * 0.3, Y - r * 0.3)], fill=(255, 236, 120))
    if 'question' in extras:
        X, Y = T(680, 250 + math.sin(t * 3) * 8)
        d.text((X, Y), '?', font=sets.font(int(90 * k), 'black'), fill=light(acc, 0.3), anchor='mm')


# ----------------------------------------------------------------------------------------- quick previews

def preview(style, size=360, bg=(14, 22, 48)):
    """A bust picture of the character in a style, for the interface."""
    k = size / 760.0
    rig = Rig(style, k)
    W = int(CW * k)
    H = int(820 * k)
    img = Image.new('RGBA', (W, H), bg + (255,))
    g = sets.Canvas(W, H, 1)
    g.glow(W / 2, H * 0.45, W * 0.5, H * 0.5, ACCENTS[style['accent']], 0.35)
    img.alpha_composite(g.im)
    st = dict(arms={'L': (12, 8), 'R': (36, 160)}, hands={'L': 'fist', 'R': 'open'}, emotion='happy', open=1.0, glow=0.8)
    oy = -int(40 * k)
    rig.paste_body(img, 0, oy, st)
    rig.paste_head(img, 0, oy, st, 0.0)
    return img.convert('RGB')
