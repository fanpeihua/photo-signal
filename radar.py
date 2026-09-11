#!/usr/bin/env python3
"""Free photo intelligence collector, durable history and localhost API; stdlib only."""
import argparse
import concurrent.futures
import email.utils
import fcntl
import hashlib
import html
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
DB = ROOT / 'data' / 'radar.sqlite'
MAX_BODY = 3_000_000


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def date_value(value):
    """Keep unknown dates unknown; reject future timestamps instead of inventing recency."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        try:
            d = email.utils.parsedate_to_datetime(str(value))
        except (ValueError, TypeError):
            return None
    d = d.replace(tzinfo=d.tzinfo or timezone.utc).astimezone(timezone.utc)
    return d.isoformat(timespec='seconds') if d <= datetime.now(timezone.utc) + timedelta(minutes=10) else None


def clean(value, limit=220):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()[:limit]


def safe_url(value):
    """Validate stored links. External pages are never fetched by the import API."""
    p = urllib.parse.urlsplit(str(value))
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('需要有效的 http/https 链接，不接受账号密码')
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def public_url(url):
    """Reject local/private destinations including redirects for user-configured feeds."""
    u = safe_url(url)
    p = urllib.parse.urlsplit(u)
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('来源必须是公网地址')
    return u


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, public_url(newurl))


def fetch(url):
    url = public_url(url)
    headers = {'User-Agent': 'PhotoSignal/1.0 (+https://github.com/fanpeihua/photo-signal)', 'Accept': '*/*'}
    if urllib.parse.urlsplit(url).hostname == 'api.github.com' and os.getenv('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    opener = urllib.request.build_opener(PublicRedirect())
    with opener.open(urllib.request.Request(url, headers=headers), timeout=20) as response:
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError('来源响应超过 3 MB')
        return data


def connect(path=DB):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY, url TEXT, title TEXT, summary TEXT, platform TEXT,
        source_id TEXT, brand TEXT, kind TEXT, published_at TEXT, first_seen TEXT,
        last_seen TEXT, topics TEXT, sentiment TEXT, sentiment_basis TEXT,
        metric REAL, metric_name TEXT, initial_metric REAL, private INTEGER DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, source_id TEXT, at TEXT, status TEXT, count INTEGER, detail TEXT
      );
      CREATE TABLE IF NOT EXISTS metrics (
        item_id TEXT, day TEXT, value REAL, PRIMARY KEY(item_id, day)
      );
    ''')
    return db


def load_config(local=False):
    config = json.loads(CONFIG.read_text())
    extra = ROOT / 'data/local-sources.json'
    if local and extra.exists():
        for s in json.loads(extra.read_text()):
            if s.get('kind') not in ('rss', 'atom'):
                raise ValueError('自定义来源支持 RSS 或 Atom')
            config['sources'].append({**s, 'private': True})
    return config


def contains(text, word):
    """ASCII word boundaries prevent 'AI' matching 'paid' or 'portrait' accidentally."""
    word = word.casefold()
    return bool(re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', text)) if word.isascii() else word in text


def classify(title, summary, config, rating=None):
    text = (title + ' ' + summary).casefold()
    topics = [t for t, words in config['topics'].items() if any(contains(text, w) for w in words)]
    sentiment, basis = '未判定', '标题或短摘录不足以判断情绪'
    if rating is not None:
        sentiment = '负向' if rating <= 2 else '正向' if rating >= 4 else '中性'
        basis = f'商店评分 {rating}/5；只是这条评论的信号'
    return topics or ['行业动态'], sentiment, basis


def relevant(title, summary, kind, config):
    """Known app reviews stay intact; broad search results must match photography context."""
    if kind in ('reviews', 'release'):
        return True
    text = (title + ' ' + summary).casefold()
    if any(contains(text, word) for word in config.get('exclude_keywords', [])):
        return False
    words = config['keywords'] + ['photos', 'images', 'cameras', 'photographer', 'photographers', 'imaging', 'denoising', 'raw', 'lightroom', 'darktable', 'composition', 'portrait', 'lens', 'lenses', 'exposure', 'fujifilm', 'canon', 'nikon']
    return any(contains(text, word) for word in words)


def normalize(raw, source, config):
    url = safe_url(raw['url'])
    title = clean(raw.get('title'), 220)
    if not title:
        raise ValueError('缺少标题')
    summary = clean(raw.get('summary'), 180)
    topics, sentiment, basis = classify(title, summary, config, raw.get('rating'))
    ident = ('private:' if source.get('private') else '') + str(raw.get('identity') or url)
    return dict(id=hashlib.sha256(str(ident).encode()).hexdigest()[:24], url=url, title=title,
                summary=summary, platform=source['platform'], source_id=source['id'],
                brand=source.get('brand', ''), kind=source['kind'], published_at=date_value(raw.get('published_at')),
                first_seen=now(), last_seen=now(), topics=json.dumps(topics, ensure_ascii=False),
                sentiment=sentiment, sentiment_basis=basis, metric=raw.get('metric'),
                metric_name=raw.get('metric_name', ''), initial_metric=raw.get('metric'), private=int(source.get('private', False)))


def feed_rows(data, atom=False):
    root = ET.fromstring(data)
    if root.tag == '{http://www.w3.org/2005/Atom}feed':
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        return [dict(title=e.findtext('a:title', '', ns), url=next((x.attrib.get('href', '') for x in e.findall('a:link', ns) if x.attrib.get('rel', 'alternate') == 'alternate'), ''), published_at=e.findtext('a:published', None, ns) or e.findtext('a:updated', None, ns)) for e in root.findall('a:entry', ns)][:60]
    if root.tag != 'rss':
        raise ValueError('来源未返回 RSS/Atom')
    return [dict(title=e.findtext('title'), url=e.findtext('link'), published_at=e.findtext('pubDate')) for e in root.findall('./channel/item')][:60]


def collect_source(s):
    kind = s['kind']
    if kind in ('rss', 'atom'):
        return feed_rows(fetch(s['url']), kind == 'atom')
    if kind == 'github':
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        q = s['query'] + f' pushed:>={cutoff} stars:>=5 archived:false'
        u = 'https://api.github.com/search/repositories?' + urllib.parse.urlencode(dict(q=q, sort='updated', order='desc', per_page=25))
        d = json.loads(fetch(u))
        return [dict(title=r['full_name'], summary=r.get('description'), url=r['html_url'], published_at=r['pushed_at'], metric=r['stargazers_count'], metric_name='stars') for r in d['items']]
    if kind == 'hn':
        cutoff = int(time.time() - 30 * 86400)
        u = 'https://hn.algolia.com/api/v1/search_by_date?' + urllib.parse.urlencode(dict(query=s['query'], tags='story', hitsPerPage=30, numericFilters=f'created_at_i>{cutoff}'))
        return [dict(title=r['title'], url=r.get('url') or 'https://news.ycombinator.com/item?id=' + r['objectID'], identity='hn:' + r['objectID'], published_at=r['created_at'], metric=r.get('points', 0), metric_name='points') for r in json.loads(fetch(u))['hits']]
    if kind == 'reviews':
        u = f"https://itunes.apple.com/{s['country']}/rss/customerreviews/page=1/id={s['app_id']}/sortby=mostrecent/json"
        entries = json.loads(fetch(u)).get('feed', {}).get('entry', [])
        if isinstance(entries, dict):
            entries = [entries]
        return [dict(title=e['title']['label'], summary=e['content']['label'], url=f"https://apps.apple.com/{s['country']}/app/id{s['app_id']}?see-all=reviews", identity=f"review:{s['app_id']}:{e['id']['label']}", published_at=e.get('updated', {}).get('label'), rating=int(e['im:rating']['label']), metric=int(e['im:rating']['label']), metric_name='rating') for e in entries if 'im:rating' in e]
    if kind == 'release':
        u = f"https://itunes.apple.com/lookup?id={s['app_id']}&country={s['country']}"
        return [dict(title=f"{s['brand']} · {r['version']}", summary=r.get('releaseNotes', ''), url=r['trackViewUrl'], identity=f"release:{s['app_id']}:{r['version']}", published_at=r.get('currentVersionReleaseDate')) for r in json.loads(fetch(u)).get('results', [])]
    raise ValueError('未知采集类型')


def store_item(db, item):
    fields = list(item)
    updates = [f'{k}=excluded.{k}' for k in fields if k not in ('id', 'first_seen', 'initial_metric', 'private')]
    # Private identifiers live in a separate namespace and cannot overwrite public data.
    db.execute(f"INSERT INTO items ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)}) ON CONFLICT(id) DO UPDATE SET {','.join(updates)}", list(item.values()))
    if item['metric'] is not None:
        db.execute('INSERT INTO metrics VALUES (?,?,?) ON CONFLICT(item_id,day) DO UPDATE SET value=excluded.value', (item['id'], now()[:10], item['metric']))


def collect(db_path=DB, local=False):
    config = load_config(local)
    lock = Path(db_path).with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'running', 'message': '已有采集任务运行'}
        source_list = [s for s in config['sources'] if s['kind'] != 'connection']
        with connect(db_path) as db, concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(collect_source, s): s for s in source_list}
            summary = []
            for job in concurrent.futures.as_completed(jobs):
                s = jobs[job]
                count, rejected, status, detail = 0, 0, 'ok', ''
                try:
                    rows = job.result()
                    for r in rows:
                        try:
                            if not relevant(clean(r.get('title')), clean(r.get('summary')), s['kind'], config):
                                rejected += 1
                                continue
                            item = normalize(r, s, config)
                        except (ValueError, KeyError, TypeError):
                            rejected += 1
                            continue
                        store_item(db, item)
                        count += 1
                    if not count:
                        status, detail = 'empty', '请求成功，但没有有效条目；不代表没有讨论'
                    if rejected:
                        detail += f' 过滤 {rejected} 条无关或不合法记录'
                except Exception as exc:
                    status = 'error'
                    # Exception URLs can contain feed credentials: expose only type/status.
                    detail = f'采集失败：{type(exc).__name__}' + (f' HTTP {exc.code}' if isinstance(exc, urllib.error.HTTPError) else '')
                db.execute('INSERT INTO runs(source_id,at,status,count,detail) VALUES(?,?,?,?,?)', (s['id'], now(), status, count, detail))
                db.commit()
                result = dict(source=s['id'], status=status, count=count, detail=detail)
                summary.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            # Retain a bounded 180-day observation history; failed feeds keep prior data.
            cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
            db.execute('DELETE FROM items WHERE last_seen < ? AND private=0', (cutoff,))
            db.execute('DELETE FROM metrics WHERE day < ? OR item_id NOT IN (SELECT id FROM items)', (cutoff[:10],))
            db.execute('DELETE FROM runs WHERE at < ?', (cutoff,))
        return {'status': 'done', 'sources': summary}


def snapshot(db_path=DB, local=False):
    config = load_config(local)
    with connect(db_path) as db:
        clause = '' if local else 'WHERE private=0'
        items = [dict(r) for r in db.execute(f'SELECT * FROM items {clause} ORDER BY COALESCE(published_at,first_seen) DESC LIMIT 6000')]
        sources = []
        for s in config['sources']:
            last = db.execute('SELECT * FROM runs WHERE source_id=? ORDER BY at DESC,id DESC LIMIT 1', (s['id'],)).fetchone()
            success = db.execute("SELECT at FROM runs WHERE source_id=? AND status='ok' ORDER BY at DESC,id DESC LIMIT 1", (s['id'],)).fetchone()
            sources.append(dict(id=s['id'], name=s['name'], platform=s['platform'], kind=s['kind'], note=s.get('note', ''), search_url=s.get('search_url', ''), status=last['status'] if last else 'pending', checked_at=last['at'] if last else None, count=last['count'] if last else 0, detail=last['detail'] if last else '', last_success=success['at'] if success else None))
        items = [i for i in items if relevant(i['title'], i['summary'], i['kind'], config)]
        for i in items:
            i['topics'], i['sentiment'], i['sentiment_basis'] = classify(i['title'], i['summary'], config, i['metric'] if i['kind'] == 'reviews' else None)
            ms = db.execute('SELECT day,value FROM metrics WHERE item_id=? ORDER BY day', (i['id'],)).fetchall()
            i['metric_history'] = [dict(m) for m in ms]
            i['metric_delta'] = ms[-1]['value'] - ms[0]['value'] if len(ms) >= 2 else None
    return dict(generated_at=now(), mode='local' if local else 'public', keywords=config['keywords'], topics=list(config['topics']), items=items, sources=sources)


def export_site(db_path=DB, output=None):
    output = Path(output or ROOT / 'dist')
    output.mkdir(parents=True, exist_ok=True)
    for p in (ROOT / 'web').iterdir():
        if p.is_file():
            shutil.copy2(p, output / p.name)
    payload = json.dumps(snapshot(db_path), ensure_ascii=False)
    tmp = output / 'snapshot.tmp'
    tmp.write_text(payload)
    tmp.replace(output / 'snapshot.json')
    (output / '.nojekyll').touch()


def restore_snapshot(path, db_path=DB):
    """Rehydrate public history in fresh Actions runners; never import local records."""
    saved = json.loads(Path(path).read_text())
    with connect(db_path) as db:
        columns = [r['name'] for r in db.execute('PRAGMA table_info(items)')]
        for item in saved['items']:
            if item.get('private'):
                continue
            row = {k: item[k] for k in columns}
            row['topics'] = json.dumps(row['topics'], ensure_ascii=False)
            db.execute(f"INSERT OR IGNORE INTO items ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))
            for m in item.get('metric_history', []):
                db.execute('INSERT OR REPLACE INTO metrics VALUES(?,?,?)', (item['id'], m['day'], m['value']))
        for s in saved['sources']:
            if s.get('checked_at'):
                db.execute('INSERT INTO runs(source_id,at,status,count,detail) VALUES(?,?,?,?,?)', (s['id'], s['checked_at'], s['status'], s['count'], s.get('detail', '')))
            if s.get('last_success') and s['status'] != 'ok':
                db.execute('INSERT INTO runs(source_id,at,status,count,detail) VALUES(?,?,?,?,?)', (s['id'], s['last_success'], 'ok', 0, '历史成功记录'))


class Handler(SimpleHTTPRequestHandler):
    """Loopback only; POST requires matching Origin and custom header against CSRF."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'web'), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def reply(self, code, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return self.reply(403, {'error': 'localhost only'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/snapshot.json':
            return self.reply(200, snapshot(local=True))
        if path == '/api/baseline':
            p = ROOT / 'data/local-baseline.json'
            return self.reply(200, json.loads(p.read_text()) if p.exists() else {})
        return super().do_GET()

    def do_POST(self):
        expected = f'http://{self.headers.get("Host")}'
        allowed = (f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}')
        if expected not in allowed or self.headers.get('Origin') != expected or self.headers.get('X-Photo-Signal') != '1':
            return self.reply(403, {'error': '只接受本机网站操作'})
        if self.path == '/api/collect':
            if not self.server.collect_lock.acquire(blocking=False):
                return self.reply(409, {'error': '采集正在运行'})
            def run():
                try:
                    collect(local=True)
                finally:
                    self.server.collect_lock.release()
            threading.Thread(target=run, daemon=True).start()
            return self.reply(202, {'status': 'running'})
        if self.path == '/api/status':
            return self.reply(200, {'running': self.server.collect_lock.locked()})
        return self.reply(404, {'error': '未知接口'})


def serve(port=8840, interval=7200):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.collect_lock = threading.Lock()
    def periodic():
        while True:
            if server.collect_lock.acquire(blocking=False):
                try:
                    collect(local=True)
                except Exception as e:
                    print(type(e).__name__, flush=True)
                finally:
                    server.collect_lock.release()
            time.sleep(max(300, interval))
    threading.Thread(target=periodic, daemon=True).start()
    print(f'Photo Signal: http://127.0.0.1:{port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['collect', 'export', 'serve', 'restore'])
    parser.add_argument('--snapshot', default=str(ROOT / 'data/public-snapshot.json'))
    parser.add_argument('--local', action='store_true')
    parser.add_argument('--port', type=int, default=8840)
    parser.add_argument('--interval', type=int, default=7200)
    args = parser.parse_args()
    if args.command == 'collect':
        collect(local=args.local)
    elif args.command == 'export':
        export_site()
    elif args.command == 'restore':
        restore_snapshot(args.snapshot)
    else:
        serve(args.port, args.interval)
