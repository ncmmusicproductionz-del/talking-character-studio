"""Draws the hooded, faceless presenter character (front view, waist-up).

Everything is drawn in "character units" on a 1000 x 1100 canvas and scaled by S.
The body (hood, torso, arms) and the head are separate layers so the head can nod and tilt.
"""
import math
from PIL import Image, ImageDraw

CW, CH = 1000, 1100
HX0, HY0, HW, HH = 180, 40, 640, 560      # head layer window, in units
PIVOT = (500, 540)                        # neck pivot the head tilts around

BLUE = (10, 140, 255)
BLUE_D = (8, 70, 150)
BLACK = (8, 9, 14)
CAP = (22, 24, 33)
CAP_L = (36, 39, 53)
HOODIE = (50, 52, 66)
HOODIE_D = (33, 35, 47)
BAND = (26, 28, 38)
WHITE = (250, 252, 255)
GLOW1 = (34, 56, 104)
GLOW2 = (96, 132, 196)

# arm angles in degrees (upper arm, forearm): 0 = hanging down, 90 = out sideways, 180 = straight up.
# Negative = swung inward across the body. The left arm is mirrored automatically.
POSES = {
    'rest':      {'L': (10, 6),   'R': (10, 6)},
    'explain':   {'L': (28, 105), 'R': (28, 105)},
    'open':      {'L': (40, 85),  'R': (40, 85)},
    'point':     {'L': (14, 8),   'R': (46, 125)},
    'think':     {'L': (14, 8),   'R': (-22, -140)},
    'celebrate': {'L': (52, 160), 'R': (52, 160)},
    'thumbs':    {'L': (14, 8),   'R': (30, 150)},
    'wave':      {'L': (14, 8),   'R': (36, 160)},
    'present':   {'L': (38, 90),  'R': (20, 8)},
}

# eye look per emotion: kind, openness, tilt (degrees), look offset
EMOTIONS = {
    'normal':    dict(kind='angular', open=1.0, tilt=0, look=0, soft=0),
    'happy':     dict(kind='happy', open=1.0, tilt=0, look=0, soft=0),
    'excited':   dict(kind='wide', open=1.0, tilt=0, look=0, soft=0),
    'surprised': dict(kind='wide', open=1.15, tilt=0, look=0, soft=0),
    'angry':     dict(kind='angular', open=0.9, tilt=16, look=0, soft=0),
    'think':     dict(kind='angular', open=1.0, tilt=-8, look=-6, soft=0, right_open=0.62),
    'tired':     dict(kind='angular', open=0.5, tilt=-6, look=0, soft=0),
    'focused':   dict(kind='angular', open=0.72, tilt=6, look=0, soft=0),
    'sad':       dict(kind='angular', open=0.85, tilt=-18, look=0, soft=0),
    'wink':      dict(kind='wink', open=1.0, tilt=0, look=0, soft=0),
}

SHOULDER = {'L': (305, 600, -1), 'R': (695, 600, 1)}
UPPER, FORE = 170, 150


def arm_points(side, a1, a2, ty=0.0):
    sx, sy, dr = SHOULDER[side]
    sy += ty
    r1, r2 = math.radians(a1), math.radians(a2)
    ex = sx + dr * math.sin(r1) * UPPER
    ey = sy + math.cos(r1) * UPPER
    hx = ex + dr * math.sin(r2) * FORE
    hy = ey + math.cos(r2) * FORE
    return (sx, sy), (ex, ey), (hx, hy)


def build_body_base(S):
    """Static part of the body: hood back, torso, drawstrings."""
    im = Image.new('RGBA', (int(CW * S), int(CH * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def pts(*p):
        return [(x * S, y * S) for x, y in p]

    d.ellipse([250 * S, 280 * S, 750 * S, 660 * S], fill=HOODIE_D)
    d.polygon(pts((262, 575), (738, 575), (812, 1100), (188, 1100)), fill=HOODIE)
    for cx in (292, 708):
        d.ellipse([(cx - 74) * S, (600 - 74) * S, (cx + 74) * S, (600 + 74) * S], fill=HOODIE)
    d.line(pts((226, 600), (188, 1100)), fill=BLUE_D, width=int(6 * S))
    d.line(pts((774, 600), (812, 1100)), fill=BLUE, width=int(6 * S))
    d.arc([218 * S, 526 * S, 366 * S, 674 * S], 180, 270, fill=BLUE_D, width=int(6 * S))
    d.arc([634 * S, 526 * S, 782 * S, 674 * S], 270, 360, fill=BLUE, width=int(6 * S))
    for x0, x1 in ((470, 462), (530, 538)):
        d.line(pts((x0, 575), (x1, 700)), fill=(205, 210, 222), width=int(6 * S))
        d.ellipse([(x1 - 8) * S, 692 * S, (x1 + 8) * S, 716 * S], fill=(205, 210, 222))
    return im


def draw_arms(im, S, arms, thumb=False, ty=0.0):
    d = ImageDraw.Draw(im)
    segs = []
    for side in ('L', 'R'):
        a1, a2 = arms[side]
        p0, p1, p2 = arm_points(side, a1, a2, ty)
        segs.append((side, p0, p1, p2))
    for width, col in ((84, HOODIE_D), (72, HOODIE)):
        for side, p0, p1, p2 in segs:
            for a, b in ((p0, p1), (p1, p2)):
                d.line([a[0] * S, a[1] * S, b[0] * S, b[1] * S], fill=col, width=int(width * S))
            for p in (p0, p1, p2):
                r = width / 2
                d.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)
    for side, p0, p1, p2 in segs:
        hx, hy = p2
        d.ellipse([(hx - 44) * S, (hy - 44) * S, (hx + 44) * S, (hy + 44) * S], fill=BLACK, outline=BLUE_D, width=int(4 * S))
        if thumb and side == 'R':
            d.rounded_rectangle([(hx - 15) * S, (hy - 84) * S, (hx + 15) * S, (hy - 26) * S], radius=int(15 * S), fill=BLACK, outline=BLUE_D, width=int(4 * S))


def _eye_poly(cx, cy, side, open_, tilt, scale=1.0):
    base = [(-46, -30), (38, -6), (30, 30), (-36, 22)]
    out = []
    ang = math.radians(tilt if side < 0 else -tilt)
    ca, sa = math.cos(ang), math.sin(ang)
    for x, y in base:
        y *= max(open_, 0.07)
        if side > 0:
            x = -x
        x, y = x * scale, y * scale
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


def draw_head(p, S):
    """p: dict(head_dy, glow, eye=(emotion dict), open_mul, look)."""
    im = Image.new('RGBA', (int(HW * S), int(HH * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dy = p.get('head_dy', 0.0)

    def X(x):
        return (x - HX0) * S

    def Y(y):
        return (y + dy - HY0) * S

    def box(x0, y0, x1, y1):
        return [X(x0), Y(y0), X(x1), Y(y1)]

    # hood rim and face void
    d.ellipse(box(268, 190, 732, 590), fill=HOODIE)
    d.ellipse(box(322, 225, 678, 545), fill=BLACK)
    d.arc(box(322, 225, 678, 545), 300, 60, fill=BLUE, width=int(7 * S))

    # cap crown, brim and button
    d.chord(box(310, 120, 690, 440), 180, 360, fill=CAP)
    d.ellipse(box(488, 112, 512, 132), fill=CAP_L)
    d.ellipse(box(288, 262, 712, 338), fill=CAP_L)
    d.arc(box(288, 262, 712, 338), 10, 170, fill=BLUE_D, width=int(5 * S))

    # headphone band and ear cups
    d.arc(box(272, 52, 728, 480), 180, 360, fill=BAND, width=int(32 * S))
    d.arc(box(284, 64, 716, 468), 195, 345, fill=BLUE, width=int(5 * S))
    glow = max(0.0, min(1.0, p.get('glow', 0.3)))
    ring = (int(10 + 60 * glow), int(120 + 80 * glow), 255)
    for cx in (290, 710):
        d.ellipse(box(cx - 50, 322, cx + 50, 472), fill=(24, 26, 36), outline=BLUE, width=int(9 * S))
        r = 24 + 6 * glow
        d.ellipse(box(cx - r, 397 - r, cx + r, 397 + r), fill=ring)

    # eyes
    e = p['eye']
    kind = e['kind']
    open_ = max(0.05, e['open'] * p.get('open_mul', 1.0))
    look = e.get('look', 0) + p.get('look', 0)
    for side, cx in ((-1, 430), (1, 570)):
        cy = 388
        cxx = cx + look
        o = open_
        if side > 0 and 'right_open' in e:
            o = max(0.05, e['right_open'] * p.get('open_mul', 1.0))
        if kind == 'happy' or (kind == 'wink' and side > 0):
            d.arc(box(cxx - 44, cy - 36, cxx + 44, cy + 36), 200, 340, fill=WHITE, width=int(15 * S))
            continue
        if kind == 'wide':
            rx, ry = 40, 50 * o
            for k, col in ((1.38, GLOW1), (1.18, GLOW2), (1.0, WHITE)):
                d.ellipse(box(cxx - rx * k, cy - ry * k, cxx + rx * k, cy + ry * k), fill=col)
            continue
        for k, col in ((1.36, GLOW1), (1.17, GLOW2), (1.0, WHITE)):
            poly = _eye_poly(cxx, cy, side, o, e['tilt'], k)
            d.polygon([(X(x), Y(y)) for x, y in poly], fill=col)
    return im
