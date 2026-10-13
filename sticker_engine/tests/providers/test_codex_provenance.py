import os,time
from pathlib import Path
from unittest.mock import patch
from sticker_engine.providers.codex import CodexProvider
from .test_codex_observability import _FakeProc
SESSION='00000000-0000-0000-0000-000000000001'

def test_historical_image_never_turns_tool_failure_into_success(tmp_path):
 d=tmp_path/SESSION;d.mkdir();f=d/'old.png';f.write_bytes(b'old');os.utime(f,(1,1))
 p=CodexProvider(output_dir=tmp_path,timeout=5)
 proc=_FakeProc([(0,0)],stdout_text='{"thread_id":"'+SESSION+'"}',stderr_text='No sticker was created. Tool runtime executable missing.')
 with patch('sticker_engine.providers.codex.subprocess.Popen',return_value=proc):assert p.generate('fixture') is None
 assert '没有产出新图' in p.last_error

def test_concurrent_other_session_cannot_supply_result(tmp_path):
 own=tmp_path/SESSION;own.mkdir();other=tmp_path/'different';other.mkdir();(other/'fresh.png').write_bytes(b'other')
 p=CodexProvider(output_dir=tmp_path)
 assert p._image_for_request(0,'{"thread_id":"'+SESSION+'"}') is None

def test_fresh_own_session_is_selected(tmp_path):
 own=tmp_path/SESSION;own.mkdir();f=own/'fresh.png';f.write_bytes(b'own');started=time.time()-1
 p=CodexProvider(output_dir=tmp_path)
 assert p._image_for_request(started,'{"thread_id":"'+SESSION+'"}')==f

def test_no_session_proof_never_uses_global_latest(tmp_path):
 own=tmp_path/SESSION;own.mkdir();(own/'fresh.png').write_bytes(b'own')
 assert CodexProvider(output_dir=tmp_path)._image_for_request(0,'No image was created') is None
