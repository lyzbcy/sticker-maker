import json
from sticker_engine.publish.status import fetch_income
from sticker_engine.featured_remake import duplicate_sources
import pytest

class Page:
    def __init__(self, blank=False): self.blank=blank
    def goto(self,*a,**kw): pass
    def wait_for_function(self,*a,**kw): pass
    def evaluate(self,script,label):
        return '' if self.blank else {'累计赞赏(元)':'0','累计热度':'100','当前可提现(元)':'2.5'}[label]

def test_income_uses_profile_not_artwork_parent(tmp_path):
    data=fetch_income(Page(),output_root=tmp_path/'library/art',user_data=tmp_path/'profile')
    assert json.loads((tmp_path/'profile/income.json').read_text('utf-8'))==data
    assert not (tmp_path/'library/income.json').exists()
    assert data['summary']['total_tips']=='0'

def test_blank_income_preserves_previous(tmp_path):
    cache=tmp_path/'income.json'; cache.write_text('old','utf-8')
    assert 'error' in fetch_income(Page(True),output_root=tmp_path/'art')
    assert cache.read_text('utf-8')=='old'

def test_byte_duplicates_and_root_boundary(tmp_path):
    source=tmp_path/'a.png';source.write_bytes(b'original')
    duplicate=tmp_path/'b.png';duplicate.write_bytes(b'original')
    different=tmp_path/'c.png';different.write_bytes(b'new')
    result=duplicate_sources(source,[source,duplicate,duplicate,different],tmp_path)
    assert result['matches']==[str(duplicate)]
    assert result['platform_duplicate_status']=='unknown'
    with pytest.raises(ValueError): duplicate_sources(source,[],tmp_path/'other')
    assert source.read_bytes()==b'original'
