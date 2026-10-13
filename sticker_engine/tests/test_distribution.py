import zipfile
import pytest
from sticker_engine.distribution import export_episode

def test_export_has_artwork_but_not_credentials(tmp_path):
 root=tmp_path/'episodes';source=root/'sample';(source/'最终版').mkdir(parents=True)
 (source/'最终版'/'test.png').write_bytes(b'fixture');(source/'credentials.json').write_text('fixture-secret')
 result=export_episode(source,tmp_path/'out.zip',root)
 assert result['images']==1
 with zipfile.ZipFile(result['path']) as z:
  assert '最终版/test.png' in z.namelist();assert 'credentials.json' not in z.namelist();assert z.testzip() is None

def test_rejects_outside_library(tmp_path):
 other=tmp_path/'other';other.mkdir()
 with pytest.raises(ValueError):export_episode(other,tmp_path/'out.zip',tmp_path/'episodes')

def test_empty_export_does_not_replace_existing_file(tmp_path):
 root=tmp_path/'episodes';source=root/'sample';source.mkdir(parents=True);dest=tmp_path/'keep.zip';dest.write_bytes(b'keep')
 with pytest.raises(ValueError):export_episode(source,dest,root)
 assert dest.read_bytes()==b'keep'
