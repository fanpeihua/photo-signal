#!/usr/bin/env python3
"""Runnable regression check: dedup, recency, privacy and durable metric history."""
import json
from pathlib import Path
import tempfile
import radar


def check():
    config = radar.load_config()
    source = config['sources'][0]
    raw = dict(url='https://github.com/example/camera', title='Camera quality', metric=10, metric_name='stars', published_at='2999-01-01')
    with tempfile.TemporaryDirectory() as tmp:
        dbpath = Path(tmp) / 'test.sqlite'
        item = radar.normalize(raw, source, config)
        assert item['published_at'] is None, 'future dates must not become fresh content'
        item['first_seen'] = '2026-09-01T00:00:00+00:00'
        with radar.connect(dbpath) as db:
            radar.store_item(db, item)
            radar.store_item(db, radar.normalize({**raw, 'metric': 20}, source, config))
            private = radar.normalize({**raw, 'title': 'PRIVATE CAMERA SECRET'}, {**source, 'id': 'private-feed', 'private': True}, config)
            radar.store_item(db, private)
            db.execute('DELETE FROM metrics')
            db.executemany('INSERT INTO metrics VALUES (?,?,?)', [(item['id'], '2026-09-01', 10), (item['id'], '2026-09-02', 20)])
            db.execute('INSERT INTO runs(source_id,at,status,count,detail) VALUES (?,?,?,?,?)', (source['id'], '2026-09-01', 'ok', 1, ''))
            db.execute('INSERT INTO runs(source_id,at,status,count,detail) VALUES (?,?,?,?,?)', (source['id'], '2026-09-02', 'error', 0, 'network'))
        snap = radar.snapshot(dbpath)
        assert len(snap['items']) == 1 and snap['items'][0]['title'] == 'Camera quality'
        assert len(radar.snapshot(dbpath, local=True)['items']) == 2
        saved = snap['items'][0]
        assert saved['first_seen'] == item['first_seen'] and saved['initial_metric'] == 10
        assert saved['metric_delta'] == 10
        assert snap['sources'][0]['status'] == 'error' and snap['sources'][0]['last_success'] == '2026-09-01'
        radar.export_site(dbpath, Path(tmp) / 'site')
        path = Path(tmp) / 'site/snapshot.json'
        assert 'PRIVATE CAMERA SECRET' not in path.read_text()
        restored = Path(tmp) / 'restored.sqlite'
        radar.restore_snapshot(path, restored)
        after = radar.snapshot(restored)
        assert after['items'][0]['metric_history'] == saved['metric_history'], 'restoring must not fabricate observations'
        assert after['sources'][0]['status'] == 'error', 'old success must not mask new failure'
        assert after['items'][0]['first_seen'] == item['first_seen']
    topics, sentiment, _ = radar.classify('Paid portrait camera', '', config)
    assert 'AI 与计算摄影' not in topics and sentiment == '未判定'
    assert radar.classify('好用但是收费', '', config, 1)[1] == '负向'
    assert not radar.relevant('Flock surveillance cameras', '', 'hn', config)
    assert not radar.relevant('A social network for events', '', 'github', config)
    assert radar.relevant('Image denoising using FFT', '', 'github', config)
    assert radar.relevant('不好用', '', 'reviews', config)
    assert '画质与评测' in radar.classify('Image denoising using FFT', '', config)[0]
    assert radar.date_value('not a date') is None
    for bad in ['javascript:alert(1)', 'file:///etc/passwd', 'https://user:pass@example.com']:
        try:
            radar.safe_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('unsafe URL accepted')
    for bad in ['http://127.0.0.1/test', 'http://[::1]/test']:
        try:
            radar.public_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('private network accepted')
    assert radar.feed_rows(b'<rss><channel><item><title>Photo</title><link>https://example.com/post</link></item></channel></rss>')[0]['published_at'] is None
    try:
        radar.feed_rows(b'<html>login</html>')
    except ValueError:
        pass
    else:
        raise AssertionError('login page must not be reported as successful feed')
    print('PASS: dedup, dates, classification, safe links, private export, restore and metric history')


if __name__ == '__main__':
    check()
