import hashlib
from pathlib import Path
from sticker_engine.publish.sticker_metrics import page_metrics

def sample():
    items=[dict(md5=hashlib.md5(str(i).encode()).hexdigest(),meaning=f'图{i}',sends=100-i,data_time='10月24日',matched=True) for i in range(65)]
    return dict(albums=[dict(item_id='a',album_name='作品',period_kind='platform_daily',capture_date='2026-10-26',captured_at='2026-10-26T01:00:00',items=items)],cached_albums=1,scope_albums=1,cache_errors=[])

def test_default_twenty_next_page_search_and_zero():
    data=sample();data['albums'][0]['items'][-1]['sends']=0
    r=page_metrics(data,[],{})
    assert len(r['rows'])==20 and r['total']==65 and r['rows'][0]['meaning']=='图0'
    assert 'albums' not in r and r['summary']['sends']==sum(x['sends'] for x in data['albums'][0]['items'])
    r=page_metrics(data,[],dict(offset=20,limit=20))
    assert len(r['rows'])==20 and r['rows'][0]['meaning']=='图20'
    r=page_metrics(data,[],dict(query='图64',sort='asc'))
    assert r['total']==1 and r['rows'][0]['sends']==0

def test_image_exact_hash_visible_rows_only(tmp_path):
    final=tmp_path/'最终版';final.mkdir();p=final/'原图.png';p.write_bytes(b'original')
    data=sample();data['albums'][0]['items'][0]['md5']=hashlib.md5(b'original').hexdigest()
    work=dict(platform_item_id='a',path=str(tmp_path))
    r=page_metrics(data,[work],dict(limit=1))
    assert r['rows'][0]['image_path']==str(p)
    assert not page_metrics(data,[work],dict(offset=1,limit=1))['rows'][0]['image_path']
    assert p.read_bytes()==b'original'

def test_date_separation_clamp_and_no_guess(tmp_path):
    data=sample();other={**data['albums'][0], 'item_id':'b','capture_date':'2026-10-25'};data['albums'].append(other)
    r=page_metrics(data,[],dict(limit=99999))
    assert len(r['groups'])==2 and r['total']==65 and r['limit']==20
    assert all(not x['image_path'] for x in r['rows'])
    assert page_metrics(data,[],dict(observation='nonexistent'))['total']==0


def test_local_original_label_is_not_platform_hash_claim(tmp_path):
    final=tmp_path/'最终版';final.mkdir();p=final/'图0.png';p.write_bytes(b'local-original')
    data=sample();works=[dict(platform_item_id='a',path=str(tmp_path))]
    r=page_metrics(data,works,dict(limit=1))
    assert r['rows'][0]['image_path']==str(p) and r['rows'][0]['image_match']=='local_meaning'
    data['albums'][0]['items'][0]['matched']=False
    assert not page_metrics(data,works,dict(limit=1))['rows'][0]['image_path']
    data['albums'][0]['items'][0]['matched']=True
    p.rename(final/'图0-其他.png')
    assert not page_metrics(data,works,dict(limit=1))['rows'][0]['image_path']
