import hashlib,json,io
from types import SimpleNamespace
import pytest
from sticker_engine.providers import native_installer as mod
class Response(io.BytesIO):
    headers={}
def fixture(monkeypatch,digest):
    data=b'fixture-exe';metadata={'assets':[{'name':'codex-x86_64-pc-windows-msvc.exe','browser_download_url':'https://github.com/openai/codex/releases/download/fixture/codex.exe','digest':digest,'size':len(data)}]}
    metadata['assets'] += [dict(metadata['assets'][0],name=n+'-x86_64-pc-windows-msvc.exe') for n in ['codex-code-mode-host','codex-command-runner','codex-windows-sandbox-setup']]
    monkeypatch.setattr(mod.platform,'machine',lambda:'AMD64')
    monkeypatch.setattr(mod.urllib.request,'urlopen',lambda req,timeout:Response(json.dumps(metadata).encode()) if req.full_url==mod.RELEASE_API else Response(data))
    run=SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess,'run',lambda *a,**kw:run)
    return data

def test_native_verified_binary_installs_without_node(tmp_path,monkeypatch):
    data=fixture(monkeypatch,'sha256:'+hashlib.sha256(b'fixture-exe').hexdigest())
    file=mod.install_native(tmp_path)
    assert __import__('pathlib').Path(file).read_bytes()==data

def test_bad_native_hash_never_replaces_existing_binary(tmp_path,monkeypatch):
    fixture(monkeypatch,'sha256:'+'0'*64)
    root=tmp_path/'tools/codex';root.mkdir(parents=True);(root/'codex.exe').write_bytes(b'previous')
    with pytest.raises(ValueError,match='校验失败'):mod.install_native(tmp_path)
    assert (root/'codex.exe').read_bytes()==b'previous';assert len(list(root.iterdir()))==1

def test_missing_digest_never_downloads_or_executes(tmp_path,monkeypatch):
    fixture(monkeypatch,'')
    with pytest.raises(ValueError,match='校验信息'):mod.install_native(tmp_path)
    assert not (tmp_path/'tools/codex/codex.exe').exists()


def test_truncated_download_resumes_at_verified_offset(tmp_path,monkeypatch):
    data=fixture(monkeypatch,'sha256:'+hashlib.sha256(b'fixture-exe').hexdigest())
    initial=mod.urllib.request.urlopen
    requests=[]
    class Partial(Response):status=200
    class Resumed(Response):status=206
    def download(req,timeout):
        if req.full_url==mod.RELEASE_API:return initial(req,timeout)
        requests.append(req)
        return Partial(data[:3]) if len(requests)==1 else Resumed(data[3:]) if req.headers.get('Range') else Partial(data)
    monkeypatch.setattr(mod.urllib.request,'urlopen',download)
    file=mod.install_native(tmp_path)
    assert __import__('pathlib').Path(file).read_bytes()==data
    assert requests[1].headers['Range']=='bytes=3-'


def test_missing_helper_rejects_before_install(tmp_path,monkeypatch):
    fixture(monkeypatch,'sha256:'+hashlib.sha256(b'fixture-exe').hexdigest())
    old=mod.urllib.request.urlopen
    def missing(req,timeout):
        response=old(req,timeout)
        if req.full_url==mod.RELEASE_API:
            metadata=json.load(response);metadata['assets']=metadata['assets'][:1]
            return Response(json.dumps(metadata).encode())
        return response
    monkeypatch.setattr(mod.urllib.request,'urlopen',missing)
    with pytest.raises(ValueError,match='完整运行组件'):mod.install_native(tmp_path)
    assert not (tmp_path/'tools/codex').exists()


def test_helper_failure_restores_entire_previous_install(tmp_path,monkeypatch):
    fixture(monkeypatch,'sha256:'+hashlib.sha256(b'fixture-exe').hexdigest())
    folder=tmp_path/'tools/codex';folder.mkdir(parents=True)
    (folder/'codex.exe').write_bytes(b'previous-main')
    (folder/'codex-code-mode-host.exe').write_bytes(b'previous-host')
    old=mod._install_component
    def fail(metadata,folder,name,target,progress,validate=True):
        if target=='codex-code-mode-host.exe':raise ValueError('fixture helper interrupted')
        return old(metadata,folder,name,target,progress,validate)
    monkeypatch.setattr(mod,'_install_component',fail)
    with pytest.raises(ValueError,match='interrupted'):mod.install_native(tmp_path)
    assert (folder/'codex.exe').read_bytes()==b'previous-main'
    assert (folder/'codex-code-mode-host.exe').read_bytes()==b'previous-host'
