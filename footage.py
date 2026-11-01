"""Royalty-free video footage: search, safe download, and preparing clips as frame sequences for the renderer.

Sources: Pexels Videos and Pixabay Videos (free keys, same as for pictures), Wikimedia Commons (CC0 / public domain /
CC BY only) and NASA (public domain), plus the user's own clips uploaded to assets/myclips.
Clips are muted; only the picture is used.
"""
import hashlib
import os
import re
import shutil
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import images as imgs
from speech import FFMPEG, NO_WINDOW

ROOT = os.path.dirname(os.path.abspath(__file__))
DL_CACHE = os.path.join(ROOT, 'assets', 'footage')
FRAME_CACHE = os.path.join(ROOT, 'assets', 'clipframes')
MY_CLIPS = os.path.join(ROOT, 'assets', 'myclips')
MAX_BYTES = 150 * 1024 * 1024
VIDEO_EXT = ('.mp4', '.mov', '.webm', '.mkv', '.m4v', '.avi')

SOURCES = [
    dict(id='mine', name='My clips', key=None, desc='Clips you uploaded (matched by file name)'),
    dict(id='pexels', name='Pexels Videos', key='pexels_key', desc='Modern HD stock footage (free key)'),
    dict(id='pixabay', name='Pixabay Videos', key='pixabay_key', desc='Stock footage (free key)'),
    dict(id='pixabay_anim', name='Pixabay animations', key='pixabay_key', desc='Animated and illustrated clips (free key)'),
    dict(id='wikimedia', name='Wikimedia Commons', key=None, desc='Historic and archive film, CC licences'),
    dict(id='nasa', name='NASA', key=None, desc='Space footage, public domain'),
]
NAMES = {s['id']: s['name'] for s in SOURCES}
DEFAULT_SOURCES = ['mine', 'pexels', 'pixabay', 'pixabay_anim', 'wikimedia', 'nasa']


def source_status():
    cfg = imgs.load_config()
    out = []
    for s in SOURCES:
        ready = bool(cfg.get(s['key'])) if s['key'] else (s['id'] != 'mine' or bool(list_my_clips()))
        out.append(dict(s, ready=ready))
    return out


def _cand(provider, raw, title, creator, lic, lic_url, attribution, source_url, thumb, url, w, h, duration):
    c = imgs._cand(provider, raw, title, creator, lic, lic_url, attribution, source_url, thumb, url, w, h)
    c['duration'] = float(duration or 0)
    c['kind'] = 'video'
    imgs.CAND[c['id']] = c
    return c


def _pick_file(files, portrait):
    """files: list of (url, w, h). Picks the smallest file that is still sharp enough."""
    want = 1080 if portrait else 1280
    files = [f for f in files if f[0] and f[1] and f[2]]
    if not files:
        return None
    good = [f for f in files if max(f[1], f[2]) >= want * 0.9 and max(f[1], f[2]) <= 2000]
    if good:
        return min(good, key=lambda f: f[1] * f[2])
    return max(files, key=lambda f: f[1] * f[2])


# ------------------------------------------------------------------ providers
def search_pexels(q, n, portrait):
    key = imgs.load_config().get('pexels_key')
    if not key:
        return []
    url = 'https://api.pexels.com/videos/search?' + urllib.parse.urlencode(
        dict(query=q, per_page=min(n * 2, 15), orientation='portrait' if portrait else 'landscape', size='medium'))
    out = []
    for v in imgs.get_json(url, {'Authorization': key}).get('videos', []):
        files = [(f.get('link'), f.get('width'), f.get('height')) for f in v.get('video_files', [])
                 if (f.get('file_type') or '').startswith('video/mp4')]
        f = _pick_file(files, portrait)
        if not f:
            continue
        user = (v.get('user') or {}).get('name')
        title = re.sub(r'[-_]+', ' ', (v.get('url') or '').rstrip('/').rsplit('/', 1)[-1])
        title = re.sub(r'\s*\d+$', '', title).strip() or q
        out.append(_cand('pexels', v['id'], title, user, 'Pexels License', 'https://www.pexels.com/license/', False,
                         v.get('url'), v.get('image'), f[0], f[1], f[2], v.get('duration')))
    return out


def search_pixabay(q, n, portrait, video_type='film', provider='pixabay'):
    key = imgs.load_config().get('pixabay_key')
    if not key:
        return []
    url = 'https://pixabay.com/api/videos/?' + urllib.parse.urlencode(dict(key=key, q=q, per_page=max(3, min(n * 2, 20)),
                                                                            safesearch='true', video_type=video_type))
    out = []
    for h in imgs.get_json(url).get('hits', []):
        vids = h.get('videos') or {}
        files = [(vids[k].get('url'), vids[k].get('width'), vids[k].get('height')) for k in ('large', 'medium', 'small') if k in vids]
        f = _pick_file(files, portrait)
        if not f:
            continue
        thumb = (vids.get('tiny') or {}).get('thumbnail') or (vids.get('small') or {}).get('thumbnail') or ''
        out.append(_cand(provider, h['id'], h.get('tags'), h.get('user'), 'Pixabay Content License',
                         'https://pixabay.com/service/license-summary/', False, h.get('pageURL'), thumb, f[0], f[1], f[2],
                         h.get('duration')))
    return out


def search_pixabay_anim(q, n, portrait):
    return search_pixabay(q, n, portrait, video_type='animation', provider='pixabay_anim')


def search_wikimedia(q, n, portrait):
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(dict(
        action='query', generator='search', gsrsearch=q + ' filetype:video', gsrnamespace=6, gsrlimit=min(n * 3, 24),
        prop='videoinfo', viprop='url|size|mime|extmetadata|derivatives', viurlwidth=640,
        viextmetadatafilter='LicenseShortName|Artist|Restrictions|LicenseUrl', format='json'))
    pages = (imgs.get_json(url).get('query') or {}).get('pages', {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get('index', 0)):
        vi = (p.get('videoinfo') or [None])[0]
        if not vi:
            continue
        em = vi.get('extmetadata') or {}
        lic = imgs._strip((em.get('LicenseShortName') or {}).get('value'))
        if imgs._strip((em.get('Restrictions') or {}).get('value')):
            continue
        if re.match(r'^(CC0|Public domain|PD[- ])', lic, re.I):
            attribution = False
        elif re.match(r'^CC BY \d', lic):
            attribution = True
        else:
            continue
        files = []
        for d in vi.get('derivatives') or []:
            if 'video/' in (d.get('type') or '') and d.get('src'):
                files.append((d['src'], d.get('width') or 0, d.get('height') or 0))
        f = _pick_file(files, portrait) or ((vi.get('url'), vi.get('width'), vi.get('height')) if vi.get('size', 0) < MAX_BYTES else None)
        dur = vi.get('duration') or 0
        if not f or (dur and dur < 2):
            continue
        title = (p.get('title') or '').replace('File:', '').rsplit('.', 1)[0]
        out.append(_cand('wikimedia', p['pageid'], title, (em.get('Artist') or {}).get('value'), lic,
                         (em.get('LicenseUrl') or {}).get('value'), attribution, vi.get('descriptionurl'),
                         vi.get('thumburl') or '', f[0], f[1], f[2], dur))
    return out


def search_nasa(q, n, portrait):
    url = 'https://images-api.nasa.gov/search?' + urllib.parse.urlencode(dict(q=q, media_type='video', page_size=min(max(n * 2, 6), 20)))
    out = []
    for it in (imgs.get_json(url).get('collection') or {}).get('items', []):
        d = (it.get('data') or [{}])[0]
        links = it.get('links') or []
        if not d.get('nasa_id'):
            continue
        thumb = next((l.get('href', '') for l in links if l.get('render') == 'image'), '')
        out.append(_cand('nasa', d['nasa_id'], d.get('title'), d.get('center') or 'NASA', 'NASA (public domain)',
                         'https://www.nasa.gov/nasa-brand-center/images-and-media/', False,
                         f"https://images.nasa.gov/details/{d['nasa_id']}", thumb, 'nasa-asset:' + d['nasa_id'], 1280, 720, 0))
    return out


def list_my_clips():
    if not os.path.isdir(MY_CLIPS):
        return []
    return sorted(f for f in os.listdir(MY_CLIPS) if f.lower().endswith(VIDEO_EXT))


def search_mine(q, n, portrait):
    words = set(w for w in re.findall(r'[a-z]{3,}', q.lower()))
    out = []
    for f in list_my_clips():
        name_words = set(re.findall(r'[a-z]{3,}', os.path.splitext(f)[0].lower()))
        score = len(words & name_words)
        if score:
            c = _cand('mine', f, os.path.splitext(f)[0], 'you', 'Your own clip', '', False, '', '',
                      'file:' + f, 0, 0, 0)
            out.append((score, c))
    return [c for _, c in sorted(out, key=lambda x: -x[0])][:n]


PROVIDERS = dict(mine=search_mine, pexels=search_pexels, pixabay=search_pixabay, pixabay_anim=search_pixabay_anim, wikimedia=search_wikimedia, nasa=search_nasa)


def search(query, sources, portrait=False, per_source=3, limit=6, min_seconds=0):
    """Returns (candidates, errors). Your own clips come first, then longer clips that match the orientation."""
    sources = [s for s in sources if s in PROVIDERS]
    errors, results = {}, {}

    def one(sid):
        try:
            return sid, PROVIDERS[sid](query, per_source, portrait), None
        except Exception as e:
            return sid, [], str(e)[:120]

    with ThreadPoolExecutor(len(sources) or 1) as ex:
        for sid, res, err in ex.map(one, sources):
            results[sid] = res
            if err:
                errors[sid] = err
    merged = list(results.get('mine', []))
    others = [c for sid in sources if sid != 'mine' for c in results.get(sid, [])]

    def score(c):
        s = 0.0
        if c['duration'] and min_seconds and c['duration'] < min_seconds * 0.5:
            s -= 2
        if c['w'] and c['h'] and (c['h'] > c['w']) == portrait:
            s += 1
        return -s
    order = {sid: i for i, sid in enumerate(sources)}
    # interleave providers so one source doesn't take every slot
    ranked = sorted(others, key=lambda c: (score(c), [x['id'] for x in results.get(c['provider'], [])].index(c['id']),
                                           order.get(c['provider'], 9)))
    merged += ranked
    if not merged and len(query.split()) > 1:
        words = sorted(query.split(), key=len, reverse=True)
        return search(words[0], sources, portrait, per_source, limit, min_seconds)
    return merged[:limit], errors


# ------------------------------------------------------------------ download and prepare
def _resolve(c):
    url = c['url']
    if url.startswith('nasa-asset:'):
        nid = url.split(':', 1)[1]
        items = (imgs.get_json('https://images-api.nasa.gov/asset/' + urllib.parse.quote(nid)).get('collection') or {}).get('items', [])
        hrefs = [i.get('href', '') for i in items]
        for tag in ('~small.mp4', '~mobile.mp4', '~medium.mp4', '~preview.mp4'):
            for h in hrefs:
                if h.endswith(tag):
                    return h.replace('http://', 'https://')
        raise ValueError('No usable NASA video size')
    return url


def download(c):
    """Downloads a clip (once) into the cache and returns the local path."""
    if c['url'].startswith('file:'):
        name = os.path.basename(c['url'][5:])
        path = os.path.join(MY_CLIPS, name)
        if not os.path.isfile(path):
            raise ValueError('Your clip is missing: ' + name)
        return path
    os.makedirs(DL_CACHE, exist_ok=True)
    path = os.path.join(DL_CACHE, hashlib.sha1(c['id'].encode()).hexdigest()[:20] + '.video')
    if os.path.exists(path):
        return path
    tmp = path + '.part'
    with imgs._open(_resolve(c), timeout=60) as r:
        ctype = (r.headers.get('Content-Type') or '').lower()
        if not (ctype.startswith('video/') or ctype in ('application/octet-stream', 'binary/octet-stream', 'application/ogg')):
            raise ValueError('Link is not a video (' + ctype + ')')
        size = 0
        with open(tmp, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    f.close()
                    os.remove(tmp)
                    raise ValueError('Video is too large')
                f.write(chunk)
    os.replace(tmp, path)
    return path


def probe(path):
    """Duration in seconds and size of a video, read from ffmpeg's log."""
    r = subprocess.run([FFMPEG, '-hide_banner', '-i', path], capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
    m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', r.stderr)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    v = re.search(r'Video:.*?(\d{2,5})x(\d{2,5})', r.stderr)
    if not v:
        raise ValueError('Not a playable video')
    return dur, int(v.group(1)), int(v.group(2))


def prepare(c, seconds, W, H, fps, offset_frac=None, start_at=None):
    """Cuts `seconds` of the clip, scales and crops it to W x H and stores it as numbered JPEG frames.
    Returns dict(dir, frames). Short clips are looped by the renderer."""
    src = download(c)
    dur, sw, sh = probe(src)
    take = min(max(seconds, 1.0), 30.0)
    start = 0.0
    if start_at is not None:
        start = max(0.0, min(float(start_at), max(0.0, dur - 1.0)))
    elif dur > take + 1:
        # archive films often open with title cards, so long ones are cut from further in
        frac = offset_frac if offset_frac is not None else (0.25 if dur > 60 else 0.12 if c['provider'] == 'nasa' else 0.05)
        start = min(dur * frac, dur - take - 0.2)
    take = min(take, dur - start) if dur else take
    key = hashlib.sha1(f"{c['id']}|{start:.2f}|{take:.2f}|{W}x{H}|{fps}|{os.path.getsize(src)}".encode()).hexdigest()[:20]
    out = os.path.join(FRAME_CACHE, key)
    done = os.path.join(out, 'done')
    if not os.path.exists(done):
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out, exist_ok=True)
        vf = f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,crop={W}:{H},fps={fps},format=yuvj420p'
        r = subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-ss', f'{start:.2f}', '-i', src, '-t', f'{take:.2f}', '-an',
                            '-vf', vf, '-q:v', '4', os.path.join(out, '%05d.jpg')],
                           capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
        n = len([f for f in os.listdir(out) if f.endswith('.jpg')])
        if n < 2:
            shutil.rmtree(out, ignore_errors=True)
            raise ValueError('Could not read the video: ' + (r.stderr.strip()[-160:] or 'no frames'))
        with open(done, 'w') as f:
            f.write(str(n))
    with open(done) as f:
        n = int(f.read().strip() or 0)
    return dict(dir=out, frames=n)


def credit_line(c):
    if c['provider'] == 'mine':
        return None
    who = f" by {c['creator']}" if c.get('creator') else ''
    lic = f", {c['license']}" if c.get('license') else ''
    link = f" - {c['source_url']}" if c.get('source_url') else ''
    return f"Video \"{c['title']}\"{who}{lic} via {NAMES.get(c['provider'], c['provider'])}{link}"


def save_upload(name, stream, length):
    """Stores an uploaded clip in assets/myclips under a safe file name. Returns the name."""
    base, ext = os.path.splitext(os.path.basename(name))
    ext = ext.lower()
    if ext not in VIDEO_EXT:
        raise ValueError('Please upload a video file (mp4, mov, webm, mkv)')
    base = re.sub(r'[^A-Za-z0-9 _-]+', '', base).strip()[:60] or 'clip'
    os.makedirs(MY_CLIPS, exist_ok=True)
    final = base + ext
    i = 2
    while os.path.exists(os.path.join(MY_CLIPS, final)):
        final = f'{base} {i}{ext}'
        i += 1
    path = os.path.join(MY_CLIPS, final)
    left = length
    with open(path + '.part', 'wb') as f:
        while left > 0:
            chunk = stream.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    os.replace(path + '.part', path)
    try:
        probe(path)
    except Exception:
        os.remove(path)
        raise ValueError('That file is not a playable video')
    return final


def delete_my_clip(name):
    name = os.path.basename(name)
    if name in list_my_clips():
        os.remove(os.path.join(MY_CLIPS, name))
