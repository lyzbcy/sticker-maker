import sys
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent))
from feedback_relay import Relay,chunks

ID='00000000-0000-0000-0000-000000000001'
def payload(content='表情包一键制作 0.5.1\n验收样本',id=ID):
    return {'request_id':id,'msgtype':'text','text':{'content':content}}

def test_delivered_receipt_is_idempotent_and_has_no_raw_content(tmp_path):
    sender=Mock(return_value={'errcode':0});r=Relay(tmp_path/'db',sender)
    assert r.submit(payload(),'client')[1]['errcode']==0
    assert r.submit(payload(),'client')[1]['errcode']==0
    assert sender.call_count==1
    assert '验收样本'.encode() not in (tmp_path/'db').read_bytes()

def test_timeout_receipt_never_resends_unknown_delivery(tmp_path):
    sender=Mock(side_effect=TimeoutError());r=Relay(tmp_path/'db',sender)
    assert r.submit(payload(),'client')[1]['state']=='unknown'
    assert r.submit(payload(),'client')[1]['state']=='unknown'
    assert sender.call_count==1

def test_partial_delivery_is_not_success_or_repeated(tmp_path):
    sender=Mock(side_effect=[{'errcode':0},{'errcode':1}]);r=Relay(tmp_path/'db',sender)
    p=payload('表情包一键制作 0.5.1\n'+'中'*1000)
    assert r.submit(p,'client')[1]['state']=='partial'
    assert r.submit(p,'client')[1]['errcode']!=0
    assert sender.call_count==2

def test_multibyte_parts_preserve_all_text_and_byte_boundaries():
    text='🍮中文'*1000;parts=chunks(text)
    assert ''.join(parts)==text
    assert all(len(x.encode())<=1700 for x in parts)

def test_server_redacts_and_never_accepts_arbitrary_upstream(tmp_path):
    sender=Mock(return_value={'errcode':0});r=Relay(tmp_path/'db',sender)
    assert r.submit(payload('表情包一键制作 0.5.1\npassword=fixture user@example.test'),'client')[0]==200
    text=sender.call_args.args[0]['text']['content'];assert 'fixture' not in text;assert 'user@' not in text
    assert r.submit({'url':'https://untrusted.test'},'client')[0]==400

def test_same_id_changed_content_rejected_and_ip_throttled(tmp_path):
    sender=Mock(return_value={'errcode':0});r=Relay(tmp_path/'db',sender)
    r.submit(payload(),'client')
    assert r.submit(payload('表情包一键制作 changed'),'client')[0]==409
    assert r.submit(payload(id='00000000-0000-0000-0000-000000000002'),'client')[0]==429

def test_real_http_health_validation_and_delivery_with_mock_upstream(tmp_path):
    import threading,json,urllib.request,urllib.error
    from feedback_relay import BoundedServer,handler
    sender=Mock(return_value={'errcode':0});relay=Relay(tmp_path/'db',sender)
    server=BoundedServer(('127.0.0.1',0),handler(relay))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        assert json.load(opener.open(base+'/health'))['status']=='ready'
        request=urllib.request.Request(base+'/feedback',data=json.dumps(payload()).encode(),headers={'Content-Type':'application/json'})
        assert json.load(opener.open(request))['errcode']==0
        assert sender.call_count==1
        bad=urllib.request.Request(base+'/feedback',data=b'{}')
        try:opener.open(bad);assert False,'invalid body accepted'
        except urllib.error.HTTPError as error:assert error.code==400
        assert sender.call_count==1
    finally:server.shutdown();server.server_close();thread.join()
