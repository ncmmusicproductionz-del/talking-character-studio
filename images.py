"""Royalty-free image search, licence filtering and safe download for the studio.

Sources that work with no account: Openverse, Wikimedia Commons, NASA, Cleveland Museum of Art.
Sources that need a free key from the provider: Pexels, Pixabay, Unsplash.

Only images with licences that allow commercial use and edits are offered:
  strict   -> no credit needed (CC0, public domain, Pexels/Pixabay licence, NASA, Met Open Access)
  standard -> also CC BY (credit required; a credits.txt is written next to every video)
CC BY-SA, NC and ND images are never offered.
"""
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'assets', 'cache')
CONFIG_PATH = os.path.join(ROOT, 'config.json')
UA = 'TalkingCharacterStudio/1.0 (local video tool for creators)'
MAX_BYTES = 25 * 1024 * 1024
MIN_WIDTH = 900

SOURCES = [
    dict(id='openverse', name='Openverse', key=None, desc='Millions of CC0 / public domain / CC BY photos from many sites'),
    dict(id='wikimedia', name='Wikimedia Commons', key=None, desc='Historic, art and encyclopedia imagery'),
    dict(id='nasa', name='NASA', key=None, desc='Space and science, public domain'),
    dict(id='cleveland', name='Cleveland Museum of Art', key=None, desc='Open Access art and artefacts (CC0)'),
    dict(id='pexels', name='Pexels', key='pexels_key', desc='Modern stock photos (free key)'),
    dict(id='pixabay', name='Pixabay photos', key='pixabay_key', desc='Stock photos (free key)'),
    dict(id='pixabay_art', name='Pixabay illustrations', key='pixabay_key', desc='Illustrations and vector art from pixabay.com/illustrations (free key)'),
    dict(id='unsplash', name='Unsplash', key='unsplash_key', desc='High quality photos, credit required (free key)'),
]

_lock = threading.Lock()
CAND = {}            # candidate id -> candidate dict, so the page only ever sends ids back


# ------------------------------------------------------------------ config (API keys)
def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(updates):
    cfg = load_config()
    for k, v in updates.items():
        if k in ('pexels_key', 'pixabay_key', 'unsplash_key') and isinstance(v, str):
            v = v.strip()
            if v:
                cfg[k] = v
            elif v == '' and k in cfg and updates.get('clear_' + k):
                cfg.pop(k, None)
    for k in ('pexels_key', 'pixabay_key', 'unsplash_key'):
        if updates.get('clear_' + k):
            cfg.pop(k, None)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    return cfg


def source_status():
    cfg = load_config()
    out = []
    for s in SOURCES:
        out.append(dict(id=s['id'], name=s['name'], desc=s['desc'], needs_key=bool(s['key']),
                        key_set=bool(s['key'] and cfg.get(s['key']))))
    return out


# ------------------------------------------------------------------ networking
def _check_host(url):
    p = urllib.parse.urlparse(url)
    if p.scheme != 'https' or not p.hostname:
        raise ValueError('Only https image links are allowed')
    for info in socket.getaddrinfo(p.hostname, p.port or 443):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError('Blocked address')


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect())


def _open(url, headers=None, timeout=25):
    _check_host(url)
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    return _opener.open(req, timeout=timeout)


def get_json(url, headers=None, timeout=25):
    with _open(url, headers, timeout) as r:
        return json.loads(r.read(5_000_000).decode('utf-8', 'replace'))


def get_bytes(url, headers=None, timeout=40):
    with _open(url, headers, timeout) as r:
        ctype = (r.headers.get('Content-Type') or '').lower()
        if not ctype.startswith('image/') or 'svg' in ctype:
            raise ValueError('Link is not a normal image (' + ctype + ')')
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Image is too large')
        return data


# ------------------------------------------------------------------ helpers
def _cid(provider, raw):
    return provider + ':' + hashlib.sha1(f'{provider}|{raw}'.encode()).hexdigest()[:14]


def _strip(s):
    s = re.sub(r'<[^>]+>', '', s or '')
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def _cand(provider, raw, title, creator, lic, lic_url, attribution, source_url, thumb, url, w=0, h=0, extra=None):
    c = dict(id=_cid(provider, raw), provider=provider, title=_strip(title)[:120] or 'Untitled', creator=_strip(creator)[:80],
             license=lic, license_url=lic_url or '', attribution_required=bool(attribution), source_url=source_url or '',
             thumb=thumb, url=url, w=int(w or 0), h=int(h or 0))
    if extra:
        c.update(extra)
    return c


def _ok_license(c, strict):
    return not (strict and c['attribution_required'])


# ------------------------------------------------------------------ providers
def search_openverse(q, n, strict, orient):
    lic = 'cc0,pdm' if strict else 'cc0,pdm,by'
    url = 'https://api.openverse.org/v1/images/?' + urllib.parse.urlencode(
        dict(q=q, license=lic, page_size=min(max(n * 2, 6), 20), mature='false', size='large,medium'))
    out = []
    for r in get_json(url, timeout=15).get('results', []):
        l = (r.get('license') or '').lower()
        if l not in ('cc0', 'pdm', 'by'):
            continue
        name = {'cc0': 'CC0', 'pdm': 'Public Domain Mark', 'by': f"CC BY {r.get('license_version') or ''}".strip()}[l]
        out.append(_cand('openverse', r['id'], r.get('title'), r.get('creator'), name, r.get('license_url'), l == 'by',
                         r.get('foreign_landing_url'), r.get('thumbnail') or r.get('url'), r.get('url'),
                         r.get('width'), r.get('height')))
    return out


def search_wikimedia(q, n, strict, orient):
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(dict(
        action='query', generator='search', gsrsearch=q + ' filetype:bitmap', gsrnamespace=6, gsrlimit=min(n * 3, 30),
        prop='imageinfo', iiprop='url|extmetadata|size|mime', iiurlwidth=1600,
        iiextmetadatafilter='LicenseShortName|Artist|Restrictions|LicenseUrl|ObjectName', format='json'))
    pages = (get_json(url).get('query') or {}).get('pages', {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get('index', 0)):
        ii = (p.get('imageinfo') or [None])[0]
        if not ii or ii.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
            continue
        em = ii.get('extmetadata') or {}
        lic = _strip((em.get('LicenseShortName') or {}).get('value'))
        if _strip((em.get('Restrictions') or {}).get('value')):
            continue
        if re.match(r'^(CC0|Public domain|PD[- ])', lic, re.I):
            attribution = False
        elif re.match(r'^CC BY \d', lic):
            attribution = True
        else:
            continue
        if ii.get('width', 0) < MIN_WIDTH:
            continue
        title = (p.get('title') or '').replace('File:', '').rsplit('.', 1)[0]
        out.append(_cand('wikimedia', p['pageid'], title, (em.get('Artist') or {}).get('value'), lic,
                         (em.get('LicenseUrl') or {}).get('value'), attribution, ii.get('descriptionurl'),
                         ii.get('thumburl') or ii['url'], ii.get('thumburl') or ii['url'], ii.get('width'), ii.get('height')))
    return out


def search_nasa(q, n, strict, orient):
    url = 'https://images-api.nasa.gov/search?' + urllib.parse.urlencode(dict(q=q, media_type='image', page_size=min(max(n * 2, 6), 20)))
    out = []
    for it in (get_json(url).get('collection') or {}).get('items', []):
        d = (it.get('data') or [{}])[0]
        links = it.get('links') or []
        if not d.get('nasa_id') or not links:
            continue
        thumb = links[0].get('href', '')
        out.append(_cand('nasa', d['nasa_id'], d.get('title'), d.get('photographer') or d.get('center') or 'NASA',
                         'NASA (public domain)', 'https://www.nasa.gov/nasa-brand-center/images-and-media/', False,
                         f"https://images.nasa.gov/details/{d['nasa_id']}", thumb, 'nasa-asset:' + d['nasa_id']))
    return out


def search_cleveland(q, n, strict, orient):
    url = 'https://openaccess-api.clevelandart.org/api/artworks/?' + urllib.parse.urlencode(
        dict(q=q, has_image=1, cc0=1, limit=min(max(n * 2, 6), 20), fields='id,title,creators,images,url,share_license_status'))
    out = []
    for a in get_json(url).get('data', []):
        im = (a.get('images') or {}).get('web') or {}
        if not im.get('url') or a.get('share_license_status') != 'CC0':
            continue
        creator = ((a.get('creators') or [{}])[0].get('description') or 'Cleveland Museum of Art').split('(')[0].strip()
        out.append(_cand('cleveland', a['id'], a.get('title'), creator, 'CC0 (Cleveland Museum of Art)',
                         'https://creativecommons.org/publicdomain/zero/1.0/', False, a.get('url'), im['url'], im['url'],
                         im.get('width'), im.get('height')))
    return out


def search_pexels(q, n, strict, orient):
    key = load_config().get('pexels_key')
    if not key:
        return []
    url = 'https://api.pexels.com/v1/search?' + urllib.parse.urlencode(dict(query=q, per_page=min(n * 2, 20), orientation=orient))
    out = []
    for p in get_json(url, {'Authorization': key}).get('photos', []):
        src = p.get('src') or {}
        out.append(_cand('pexels', p['id'], p.get('alt') or q, p.get('photographer'), 'Pexels License',
                         'https://www.pexels.com/license/', False, p.get('url'), src.get('medium') or src.get('large'),
                         src.get('large2x') or src.get('large'), p.get('width'), p.get('height')))
    return out


def search_pixabay(q, n, strict, orient, image_type='photo', provider='pixabay'):
    key = load_config().get('pixabay_key')
    if not key:
        return []
    url = 'https://pixabay.com/api/?' + urllib.parse.urlencode(dict(
        key=key, q=q, image_type=image_type, per_page=max(3, min(n * 2, 20)), safesearch='true', min_width=1280,
        orientation='vertical' if orient == 'portrait' else 'horizontal'))
    out = []
    for h in get_json(url).get('hits', []):
        if image_type != 'photo' and h.get('type') == 'photo':
            continue
        out.append(_cand(provider, h['id'], h.get('tags'), h.get('user'), 'Pixabay Content License',
                         'https://pixabay.com/service/license-summary/', False, h.get('pageURL'),
                         h.get('webformatURL'), h.get('largeImageURL'), h.get('imageWidth'), h.get('imageHeight')))
    return out


def search_pixabay_art(q, n, strict, orient):
    """Illustrations and vector graphics (the pixabay.com/illustrations and /vectors sections), via the official API."""
    return search_pixabay(q, n, strict, orient, image_type='illustration', provider='pixabay_art') + \
        search_pixabay(q, max(1, n // 2), strict, orient, image_type='vector', provider='pixabay_art')


def search_unsplash(q, n, strict, orient):
    key = load_config().get('unsplash_key')
    if not key:
        return []
    url = 'https://api.unsplash.com/search/photos?' + urllib.parse.urlencode(
        dict(query=q, per_page=min(n * 2, 20), orientation='portrait' if orient == 'portrait' else 'landscape'))
    out = []
    for p in get_json(url, {'Authorization': 'Client-ID ' + key}).get('results', []):
        u = p.get('urls') or {}
        out.append(_cand('unsplash', p['id'], p.get('alt_description') or p.get('description') or q,
                         (p.get('user') or {}).get('name'), 'Unsplash License', 'https://unsplash.com/license', True,
                         (p.get('links') or {}).get('html'), u.get('small'), u.get('regular'), p.get('width'), p.get('height'),
                         extra=dict(ping=(p.get('links') or {}).get('download_location'))))
    return out


PROVIDERS = dict(pixabay_art=search_pixabay_art, openverse=search_openverse, wikimedia=search_wikimedia, nasa=search_nasa, cleveland=search_cleveland,
                 pexels=search_pexels, pixabay=search_pixabay, unsplash=search_unsplash)


def _search_once(query, sources, per_source=3, strict=False, orient='landscape', limit=8):
    """Searches the chosen sources in parallel; returns up to `limit` candidates, interleaved across sources."""
    query = (query or '').strip()
    if not query:
        return [], {}
    sources = [s for s in sources if s in PROVIDERS]
    errors, per = {}, {}

    def one(sid):
        try:
            res = [c for c in PROVIDERS[sid](query, per_source, strict, orient) if _ok_license(c, strict)]
            return sid, res[:per_source], None
        except Exception as e:
            return sid, [], str(e)[:160]

    with ThreadPoolExecutor(max(1, len(sources))) as ex:
        for sid, res, err in ex.map(one, sources):
            per[sid] = res
            if err:
                errors[sid] = err
    merged, i = [], 0
    while len(merged) < limit and any(i < len(v) for v in per.values()):
        for sid in sources:
            if i < len(per.get(sid, [])) and len(merged) < limit:
                merged.append(per[sid][i])
        i += 1
    with _lock:
        for c in merged:
            CAND[c['id']] = c
        if len(CAND) > 4000:
            for k in list(CAND)[:1500]:
                CAND.pop(k, None)
    return merged, errors


def search(query, sources, per_source=3, strict=False, orient='landscape', limit=8):
    """Like _search_once, but if too few pictures turn up it retries with shorter word combinations."""
    merged, errors = _search_once(query, sources, per_source, strict, orient, limit)
    words = query.split()
    if len(merged) < min(4, limit) and len(words) >= 2:
        tries = [' '.join(words[:2]), ' '.join(words[-2:])] + sorted(set(words), key=len, reverse=True)
        seen, tried = {c['id'] for c in merged}, {query.lower()}
        for t in tries:
            if len(merged) >= limit or t.lower() in tried:
                continue
            tried.add(t.lower())
            more, errs2 = _search_once(t, sources, per_source, strict, orient, limit)
            for c in more:
                if c['id'] not in seen and len(merged) < limit:
                    seen.add(c['id'])
                    merged.append(c)
            for k, v in errs2.items():
                errors.setdefault(k, v)
            if len(merged) >= 4:
                break
    return merged, errors


def public(c):
    keys = ('id', 'provider', 'title', 'creator', 'license', 'license_url', 'attribution_required', 'source_url', 'thumb', 'w', 'h')
    return {k: c[k] for k in keys}


# ------------------------------------------------------------------ download and prepare
def _resolve(c):
    url = c['url']
    if url.startswith('nasa-asset:'):
        nid = url.split(':', 1)[1]
        items = (get_json('https://images-api.nasa.gov/asset/' + urllib.parse.quote(nid)).get('collection') or {}).get('items', [])
        hrefs = [i.get('href', '') for i in items]
        for tag in ('~large.jpg', '~medium.jpg', '~orig.jpg', '~small.jpg'):
            for h in hrefs:
                if h.endswith(tag):
                    return h.replace('http://', 'https://')
        raise ValueError('No usable NASA image size')
    return url


def prepare(c):
    """Downloads (once), validates and re-encodes an image into the cache. Returns the local path."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(c['id'].encode()).hexdigest()[:20] + '.jpg')
    if os.path.exists(path):
        return path
    data = get_bytes(_resolve(c))
    img = Image.open(io.BytesIO(data))
    img.verify()
    img = Image.open(io.BytesIO(data)).convert('RGB')
    if img.width < 640:
        raise ValueError('Image is too small')
    img.thumbnail((2400, 2400))
    tmp = path + '.part'
    img.save(tmp, 'JPEG', quality=90)
    os.replace(tmp, path)
    if c.get('ping') and c['provider'] == 'unsplash':
        try:
            get_json(c['ping'], {'Authorization': 'Client-ID ' + load_config().get('unsplash_key', '')})
        except Exception:
            pass
    return path


def credit_line(c):
    who = f" by {c['creator']}" if c.get('creator') and c['creator'] != 'Untitled' else ''
    lic = f", {c['license']}" if c.get('license') else ''
    link = f" - {c['source_url']}" if c.get('source_url') else ''
    return f"\"{c['title']}\"{who}{lic} via {dict((s['id'], s['name']) for s in SOURCES).get(c['provider'], c['provider'])}{link}"


# ------------------------------------------------------------------ queries from the script
STOP = set('''about above after again against all also always among and another any are around because been before being below between both
but can come could did does doing down during each even every everyone everything few for from further get gets getting going had has
have having here how into its just keep know like made make many mostly much must need never next not now off once only other our out
over own people really said same says see she should since some something still such take than that the their them then there these
they thing things this those through today too took under until upon very want was way well were what when where which while who why
will with within without would yes yet you your here's there's it's that's isn't don't didn't wasn't weren't first real
january february march april june july august september october november december monday tuesday wednesday thursday
friday saturday sunday one two three four five six seven eight nine ten twenty thirty forty fifty hundred thousand
fourth fifth sixth seventh eighth ninth tenth day days year years time times staged stayed needed loved'''.split())


def keywords(text, n=3):
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text)
    scored = []
    for i, w in enumerate(words):
        lw = w.lower().strip("'-")
        if lw in STOP or len(lw) < 4 or any(p in STOP for p in lw.split('-')):
            continue
        scored.append((len(lw) + (3 if (w[0].isupper() and i > 0) else 0), -i, i, lw))
    top = sorted(scored, reverse=True)[:n]
    seen, out = set(), []
    for _, _, i, w in sorted(top, key=lambda t: t[2]):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return ' '.join(out)


def group_scenes(sentences, min_chars=70):
    """Groups consecutive sentences into scenes that share one picture. Same grouping is used for the review page and the render."""
    scenes, cur, size = [], [], 0
    for i, s in enumerate(sentences):
        starts_new = bool(cur) and (s.get('chapter') or s.get('image_query') or s.get('clip_query') or size >= min_chars
                                    or bool(s.get('no_image')) != bool(sentences[cur[-1]].get('no_image')))
        if starts_new:
            scenes.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(s['spoken'])
    if cur:
        scenes.append(cur)
    out = []
    for idx in scenes:
        text = ' '.join(sentences[i]['spoken'] for i in idx)
        explicit = next((sentences[i].get('image_query') for i in idx if sentences[i].get('image_query')), None)
        clip = next((sentences[i] for i in idx if sentences[i].get('clip_query')), None)
        skip = all(sentences[i].get('no_image') for i in idx)
        out.append(dict(idx=idx, text=text, query=(clip['clip_query'] if clip else None) or explicit or keywords(text), skip=skip,
                        clip_query=clip['clip_query'] if clip else None, clip_full=bool(clip and clip.get('clip_full')),
                        clip_at=clip.get('clip_at') if clip else None,
                        want='clip' if clip else ('image' if explicit else None)))
    return out
