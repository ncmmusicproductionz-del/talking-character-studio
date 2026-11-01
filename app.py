"""Talking Character Studio - a local web app.  Run it, then use the page that opens in your browser."""
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'output')
UPLOADS = os.path.join(ROOT, 'uploads')
WEB = os.path.join(ROOT, 'web')
VOICE_CACHE = os.path.join(ROOT, 'assets', 'voices')
PLAN_CACHE = os.path.join(ROOT, 'assets', 'plan')
PORT = int(os.environ.get('PORT') or os.environ.get('TC_PORT') or 8765)
JOBS = {}
LOCK = threading.Lock()
_voices_cache = {}
_avatar = {}


def get_voices():
    import speech
    if not _voices_cache:
        _voices_cache['edge'] = [dict(id=i, name=n) for i, n in speech.EDGE_VOICES]
        _voices_cache['edge_available'] = speech.edge_available()
        _voices_cache['windows'] = speech.windows_voices()
    return _voices_cache


def avatar_png():
    if 'png' not in _avatar:
        import io
        import character as ch
        img = ch.draw_head(dict(head_dy=0, glow=0.8, eye=ch.EMOTIONS['normal'], open_mul=1.0, look=0), 0.6)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        _avatar['png'] = buf.getvalue()
    return _avatar['png']


def clean_character(c):
    """Only known values get through to the renderer."""
    import rig
    c = c if isinstance(c, dict) else {}
    import puppet
    mode = c.get('mode') if c.get('mode') in ('classic', 'theme', 'random', 'custom', 'image') else 'classic'
    image_id = c.get('image_id') if mode == 'image' and puppet.exists(c.get('image_id')) else None
    if mode == 'image' and not image_id:
        mode = 'classic'
    try:
        seed = int(c.get('seed', 0)) % 100000
    except (TypeError, ValueError):
        seed = 0
    cu = c.get('custom') if isinstance(c.get('custom'), dict) else {}
    custom = dict(outfit=cu.get('outfit') if cu.get('outfit') in rig.OUTFITS else 'hoodie',
                  hat=cu.get('hat') if cu.get('hat') in rig.HATS else 'cap',
                  color=cu.get('color') if cu.get('color') in rig.COLORS else 'charcoal',
                  accent=cu.get('accent') if cu.get('accent') in rig.ACCENTS else 'blue')
    return dict(mode=mode, seed=seed, custom=custom, image_id=image_id)


def clean_footage(f):
    """Footage options from the page, or None when footage is off."""
    import footage
    if not isinstance(f, dict) or not f.get('on'):
        return None
    srcs = [x for x in (f.get('sources') or footage.DEFAULT_SOURCES) if x in footage.PROVIDERS]
    display = {'full': 'inside'}.get(f.get('display'), f.get('display'))
    display = display if display in ('screen', 'inside', 'bubble', 'mix') else 'screen'
    return dict(sources=srcs, display=display, all=f.get('scope', 'all') != 'tagged')


_char_png = {}


def character_png(c, theme):
    import io
    import rig
    key = json.dumps([c, theme], sort_keys=True)
    if key not in _char_png:
        if len(_char_png) > 120:
            _char_png.clear()
        buf = io.BytesIO()
        if c['mode'] == 'image':
            import puppet
            puppet.preview(c['image_id'], 300).save(buf, 'PNG')
        else:
            rig.preview(rig.make_style(c['mode'], theme, 1 + c['seed'], c['custom']), 300).save(buf, 'PNG')
        _char_png[key] = buf.getvalue()
    return _char_png[key]


def character_options():
    import motion
    import rig
    hx = lambda c: '#%02x%02x%02x' % c
    return dict(outfits=[dict(id=k, label=v) for k, v in rig.OUTFITS.items()],
                hats=[dict(id=k, label=v) for k, v in rig.HATS.items()],
                colors=[dict(id=k, hex=hx(v)) for k, v in rig.COLORS.items()],
                accents=[dict(id=k, hex=hx(v)) for k, v in rig.ACCENTS.items()],
                expressions=list(rig.EXPRESSIONS), poses=list(motion.POSES), actions=list(motion.ACTIONS))


def voice_preview(mode, voice):
    import speech
    os.makedirs(VOICE_CACHE, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', voice or 'default')
    ext = '.mp3' if mode == 'edge' else '.wav'
    path = os.path.join(VOICE_CACHE, f'{mode}_{safe}{ext}')
    if not os.path.exists(path):
        name = voice.split('-')[2].replace('Neural', '') if mode == 'edge' and voice.count('-') >= 2 else 'your narrator'
        text = f"Hi, I'm {name}. This is how I'll sound reading your script."
        speech.synthesize(text, mode, voice, 0, path)
    return path


class Cancelled(Exception):
    pass


def run_job(jid, req):
    from pipeline import make_video
    job = JOBS[jid]
    out_dir = os.path.join(OUT, jid)
    os.makedirs(out_dir, exist_ok=True)
    live = os.path.join(out_dir, 'live.jpg')
    job['started'] = time.time()

    def progress(msg, frac):
        if job.get('cancel'):
            raise Cancelled()
        job['message'] = msg
        if frac is not None:
            job['progress'] = round(frac, 3)

    try:
        audio_path = None
        if req.get('mode') == 'file':
            aid = re.sub(r'[^A-Za-z0-9_.-]', '', req.get('audio_id', ''))
            audio_path = os.path.join(UPLOADS, aid)
        music = None
        m = req.get('music') or {}
        if isinstance(m, dict) and m.get('id'):
            mid = re.sub(r'[^A-Za-z0-9_.-]', '', m['id'])
            music = dict(path=os.path.join(UPLOADS, mid), volume=float(m.get('volume', 0.22)))
        look = req.get('look') if isinstance(req.get('look'), dict) else {}
        look['character'] = clean_character(look.get('character'))
        seconds = float(req['seconds']) if req.get('seconds') else None
        clips = clean_footage(req.get('footage'))
        job['live'] = f'/files/{jid}/live.jpg'
        res = make_video(
            req['script'], out_dir, mode=req.get('mode', 'edge'), voice=req.get('voice', ''), speed=int(req.get('speed', 0)),
            audio_path=audio_path, fmt=req.get('format', 'vertical'), quality=req.get('quality', 'final'),
            fps=int(req.get('fps', 24)), captions=look.get('caption_style', 'bold') != 'off', seconds=seconds, progress=progress,
            images=req.get('images') if isinstance(req.get('images'), dict) else None, look=look, music=music, live_path=live,
            video_clips=clips)
        files = {k: f'/files/{jid}/{os.path.basename(res[k])}' for k in ('video', 'srt', 'audio')}
        for k in ('credits', 'poster'):
            if res.get(k):
                files[k] = f'/files/{jid}/{os.path.basename(res[k])}'
        job['files'] = files
        job['warnings'] = res.get('warnings', [])
        job['seconds'] = round(res['seconds'], 1)
        job['sets'] = res.get('sets', [])
        job['status'] = 'done'
        title = next((l.strip('# ').strip() for l in req['script'].splitlines() if l.strip().startswith('#')), None)
        if not title:
            title = next((l.strip() for l in req['script'].splitlines() if l.strip()), 'Untitled')
        title = re.sub(r'\[[^\]]*\]|\*', '', title).strip()[:80]
        with open(os.path.join(out_dir, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(id=jid, created=time.time(), title=title, files=files, preview=bool(seconds), seconds=job['seconds'],
                           format=req.get('format', 'vertical'), sets=job['sets'], voice=req.get('voice', '')), f)
        try:
            os.remove(live)
        except OSError:
            pass
    except Cancelled:
        job['status'] = 'cancelled'
        shutil.rmtree(out_dir, ignore_errors=True)
    except Exception as e:
        traceback.print_exc()
        job['status'] = 'error'
        job['error'] = str(e)


def history():
    items = []
    if os.path.isdir(OUT):
        for d in os.listdir(OUT):
            p = os.path.join(OUT, d, 'meta.json')
            if os.path.exists(p):
                try:
                    items.append(json.load(open(p, encoding='utf-8')))
                except Exception:
                    pass
    return sorted(items, key=lambda m: -m['created'])


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data, ctype, cache=False):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'max-age=3600' if cache else 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self._get()
        except (ConnectionError, OSError):
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                self._json(dict(error=str(e)), 500)
            except Exception:
                pass

    def _get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ('/', '/index.html'):
            return self._static('index.html')
        if u.path.startswith('/web/'):
            return self._static(u.path[5:])
        if u.path == '/api/voices':
            return self._json(get_voices())
        if u.path == '/api/themes':
            import sets
            return self._json([dict(id=t, label=sets.THEMES[t]['label'], accent='#%02x%02x%02x' % sets.THEMES[t]['accent'])
                               for t in sets.THEME_ORDER])
        if u.path == '/api/status':
            jid = q.get('id', [''])[0]
            job = dict(JOBS.get(jid, dict(status='unknown')))
            if job.get('started'):
                job['elapsed'] = round(time.time() - job['started'], 1)
            return self._json(job)
        if u.path == '/api/history':
            return self._json(history())
        if u.path == '/api/image_sources':
            import images
            return self._json(images.source_status())
        if u.path == '/api/footage_sources':
            import footage
            return self._json(footage.source_status())
        if u.path == '/api/myclips':
            import footage
            return self._json([dict(name=n, size=os.path.getsize(os.path.join(footage.MY_CLIPS, n))) for n in footage.list_my_clips()])
        if u.path == '/api/random_script':
            import scriptgen
            try:
                minutes = max(0.5, min(30.0, float(q.get('minutes', ['8'])[0])))
            except ValueError:
                minutes = 8.0
            script, info = scriptgen.generate(minutes, footage=q.get('footage', ['1'])[0] != '0')
            return self._json(dict(script=script, **info))
        if u.path == '/api/characters':
            import puppet
            return self._json(puppet.list_characters())
        if u.path == '/api/character_options':
            return self._json(character_options())
        if u.path == '/api/character.png':
            c = clean_character(dict(mode=q.get('mode', ['classic'])[0], seed=q.get('seed', ['0'])[0], image_id=q.get('image_id', [''])[0],
                                     custom={k_: q.get(k_, [''])[0] for k_ in ('outfit', 'hat', 'color', 'accent')}))
            theme = q.get('theme', ['studio'])[0]
            import sets
            return self._bytes(character_png(c, theme if theme in sets.THEMES else 'studio'), 'image/png', cache=True)
        if u.path == '/api/avatar.png':
            return self._bytes(avatar_png(), 'image/png', cache=True)
        if u.path == '/api/voice_preview':
            mode = q.get('mode', ['edge'])[0]
            voice = q.get('voice', [''])[0]
            if mode not in ('edge', 'windows'):
                return self._json(dict(error='bad mode'), 400)
            path = voice_preview(mode, voice)
            with open(path, 'rb') as f:
                return self._bytes(f.read(), 'audio/mpeg' if path.endswith('.mp3') else 'audio/wav', cache=True)
        if u.path.startswith('/plan/'):
            name = u.path[6:]
            if not re.fullmatch(r'[a-f0-9]{16}\.jpg', name):
                return self.send_error(404)
            p = os.path.join(PLAN_CACHE, name)
            if not os.path.exists(p):
                return self.send_error(404)
            with open(p, 'rb') as f:
                return self._bytes(f.read(), 'image/jpeg', cache=True)
        if u.path.startswith('/files/'):
            return self._file(u.path)
        self.send_error(404)

    def _static(self, rel):
        rel = rel.replace('\\', '/')
        if '..' in rel or not re.fullmatch(r'[A-Za-z0-9_./-]+', rel):
            return self.send_error(404)
        p = os.path.join(WEB, rel)
        if not os.path.isfile(p):
            return self.send_error(404)
        with open(p, 'rb') as f:
            data = f.read()
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript',):
            ctype += '; charset=utf-8'
        self._bytes(data, ctype)

    def _file(self, path):
        parts = path.split('/')
        if len(parts) != 4 or not re.fullmatch(r'[A-Za-z0-9_-]+', parts[2]) or not re.fullmatch(r'[A-Za-z0-9_.-]+', parts[3]):
            return self.send_error(404)
        fp = os.path.join(OUT, parts[2], parts[3])
        if not os.path.isfile(fp):
            return self.send_error(404)
        size = os.path.getsize(fp)
        start, end, code = 0, size - 1, 200
        rng = self.headers.get('Range')
        if rng:
            m = re.match(r'bytes=(\d*)-(\d*)', rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
                code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header('Content-Type', mimetypes.guess_type(fp)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        if code == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if parts[3].endswith(('.srt', '.mp3', '.wav', '.txt')) or self.path.endswith('?dl=1'):
            self.send_header('Content-Disposition', f'attachment; filename="{parts[3]}"')
        self.end_headers()
        with open(fp, 'rb') as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):
        try:
            self._post()
        except (ConnectionError, OSError):
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                self._json(dict(error=f'Server error: {e}'), 500)
            except Exception:
                pass

    def _read_json(self, n):
        return json.loads(self.rfile.read(n) or b'{}')

    def _post(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        n = int(self.headers.get('Content-Length', 0))
        if u.path == '/api/upload_clip':
            import footage
            if n > 1024 * 1024 * 1024:
                return self._json(dict(error='Clip is too large (1 GB max)'), 413)
            try:
                name = footage.save_upload(q.get('name', ['clip.mp4'])[0], self.rfile, n)
            except ValueError as e:
                return self._json(dict(error=str(e)), 400)
            return self._json(dict(name=name))
        if u.path == '/api/character_upload':
            import puppet
            if n > 60 * 1024 * 1024:
                return self._json(dict(error='Pictures are too large (60 MB max in total)'), 413)
            req = self._read_json(n)
            import base64
            files = {}
            for slot in puppet.SLOTS:
                v = req.get(slot)
                if isinstance(v, str) and v.startswith('data:image/'):
                    files[slot] = base64.b64decode(v.split(',', 1)[1])
            try:
                cid = puppet.save_character(str(req.get('name', '')), files)
            except Exception as e:
                return self._json(dict(error=f'Could not use that picture: {e}'), 400)
            _char_png.clear()
            return self._json(dict(id=cid))
        if u.path == '/api/character_delete':
            import puppet
            req = self._read_json(n)
            puppet.delete_character(str(req.get('id', '')))
            return self._json(dict(ok=True))
        if u.path == '/api/delete_clip':
            import footage
            req = self._read_json(n)
            footage.delete_my_clip(str(req.get('name', '')))
            return self._json(dict(ok=True))
        if u.path == '/api/upload':
            if n > 400 * 1024 * 1024:
                return self._json(dict(error='File too large'), 413)
            name = q.get('name', ['audio.mp3'])[0]
            ext = os.path.splitext(name)[1].lower()
            if ext not in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.mp4'):
                return self._json(dict(error='Please upload an audio file (mp3, wav, m4a, ogg, flac)'), 400)
            os.makedirs(UPLOADS, exist_ok=True)
            aid = uuid.uuid4().hex[:12] + ext
            with open(os.path.join(UPLOADS, aid), 'wb') as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            return self._json(dict(id=aid, name=name))
        if u.path == '/api/generate':
            req = self._read_json(n)
            if not isinstance(req.get('script'), str) or not req['script'].strip():
                return self._json(dict(error='Write or paste a script first.'), 400)
            with LOCK:
                if any(j.get('status') == 'running' for j in JOBS.values()):
                    return self._json(dict(error='Another video is still rendering. Wait for it to finish.'), 409)
                jid = uuid.uuid4().hex[:10]
                JOBS[jid] = dict(status='running', progress=0.0, message='Starting', preview=bool(req.get('seconds')))
            threading.Thread(target=run_job, args=(jid, req), daemon=True).start()
            return self._json(dict(id=jid))
        if u.path == '/api/cancel':
            req = self._read_json(n)
            job = JOBS.get(str(req.get('id', '')))
            if job and job.get('status') == 'running':
                job['cancel'] = True
                job['message'] = 'Stopping...'
            return self._json(dict(ok=True))
        if u.path == '/api/plan':
            from pipeline import plan_preview
            req = self._read_json(n)
            if not isinstance(req.get('script'), str) or not req['script'].strip():
                return self._json(dict(scenes=[]))
            fmt = 'vertical' if req.get('format') == 'vertical' else 'landscape'
            ov = req.get('overrides') if isinstance(req.get('overrides'), dict) else {}
            stage = req.get('stage_mode') if req.get('stage_mode') in ('mix', 'room', 'open') else 'mix'
            scenes = plan_preview(req['script'], fmt, str(req.get('set_mode', 'auto')), ov, clean_character(req.get('character')), stage)
            return self._json(dict(scenes=scenes))
        if u.path == '/api/delete':
            req = self._read_json(n)
            jid = str(req.get('id', ''))
            if not re.fullmatch(r'[A-Za-z0-9_-]+', jid):
                return self._json(dict(error='bad id'), 400)
            if JOBS.get(jid, {}).get('status') == 'running':
                return self._json(dict(error='That video is still rendering.'), 409)
            shutil.rmtree(os.path.join(OUT, jid), ignore_errors=True)
            return self._json(dict(ok=True))
        if u.path == '/api/open_folder':
            os.makedirs(OUT, exist_ok=True)
            try:
                os.startfile(OUT)
            except Exception as e:
                return self._json(dict(error=str(e)), 500)
            return self._json(dict(ok=True))
        if u.path in ('/api/config', '/api/plan_images', '/api/search_images'):
            import images
            req = self._read_json(n)
            if u.path == '/api/config':
                images.save_config({k: v for k, v in req.items() if isinstance(v, (str, bool))})
                return self._json(images.source_status())
            sources = [s for s in (req.get('sources') or []) if s in images.PROVIDERS]
            if not sources:
                return self._json(dict(error='Turn on at least one picture source.'), 400)
            strict = req.get('license') == 'strict'
            orient = 'portrait' if req.get('format') == 'vertical' else 'landscape'
            if u.path == '/api/search_images':
                res, errs = images.search(str(req.get('query', '')), sources, per_source=3, strict=strict, orient=orient, limit=12)
                return self._json(dict(candidates=[images.public(c) for c in res], errors=errs))
            if not isinstance(req.get('script'), str) or not req['script'].strip():
                return self._json(dict(error='Write or paste a script first.'), 400)
            from concurrent.futures import ThreadPoolExecutor
            from scriptparse import parse_script
            scenes = images.group_scenes(parse_script(req['script']))

            def plan(sc):
                if sc['skip'] or not sc['query']:
                    return dict(candidates=[], errors={})
                res, errs = images.search(sc['query'], sources, per_source=2, strict=strict, orient=orient, limit=8)
                return dict(candidates=[images.public(c) for c in res], errors=errs)

            with ThreadPoolExecutor(3) as ex:
                found = list(ex.map(plan, scenes))
            rows = [dict(index=i, text=sc['text'][:160], query=sc['query'], skip=sc['skip'], **f) for i, (sc, f) in enumerate(zip(scenes, found))]
            return self._json(dict(rows=rows))
        self.send_error(404)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(UPLOADS, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    url = f'http://127.0.0.1:{PORT}/'
    print(f'Talking Character Studio is running at {url}\nLeave this window open while you use it. Press Ctrl+C to stop.')
    if not os.environ.get('TC_NOBROWSER') and '--no-browser' not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
