from types import SimpleNamespace
import pytest
from sticker_engine.publish.shelf_preflight import sync_warnings_for_shelf


def sample():
    return {'source': 'api', 'platform_total': 4, 'matched': 4, 'updated': 4,
            'list_complete': False, 'complete': False, 'unknown_statuses': [],
            'reason_failures': [], 'fresh_shelfable': ['approved'],
            'persistence_failures': [{'name': 'unrelated-live', 'message': 'missing parent'}]}


def load(_):
    return SimpleNamespace(album_name='approved', platform_item_id='sid', platform_status='审核通过')


def test_complete_api_list_can_shelf_despite_unrelated_local_save_failure():
    warnings = sync_warnings_for_shelf(sample(), load)
    assert len(warnings) == 1 and warnings[0]['name'] == 'unrelated-live'


@pytest.mark.parametrize('change', [
    {'updated': 3}, {'matched': 3}, {'source': 'dom'}, {'cancelled': True},
    {'error': 'login failed'}, {'unknown_statuses': [99]}, {'reason_failures': ['timeout']},
    {'persistence_failures': [{'name': 'approved', 'message': 'changed revision'}]},
    {'persistence_failures': []}, {'persistence_failures': [{}]},
    {'fresh_shelfable': None}, {'platform_total': 0},
])
def test_partial_or_affected_candidate_remains_blocked(change):
    result = dict(sample(), **change)
    assert sync_warnings_for_shelf(result, load) is None


def test_unreadable_candidate_stays_blocked():
    def missing(_):
        raise OSError('missing local metadata')
    assert sync_warnings_for_shelf(sample(), missing) is None
