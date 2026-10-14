from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.library.failed_drafts import cleanup
from sticker_engine.config.series import EpisodeMeta,save_meta


def test_quarantines_only_empty_shells_and_preserves_images_platform_and_named_drafts(tmp_path):
    rt=LibraryRuntime(tmp_path);rt.bind('a@example.com',True)
    for name,meta in [('shell',EpisodeMeta()),('named',EpisodeMeta(album_name='保留')),
                      ('platform',EpisodeMeta(platform_item_id='1')),('image',EpisodeMeta())]:
        p=rt.output_root/('episode_'+name);save_meta(p,meta)
        (p/'本次制作角色.md').write_text('角色卡',encoding='utf-8')
        if name=='image':(p/'grid.png').write_bytes(b'artwork')
        rt.capture(p)
    preview=cleanup(rt)
    assert preview['count']==1
    result=cleanup(rt,True)
    assert result['count']==1
    assert not (rt.output_root/'episode_shell').exists()
    for name in ('named','platform','image'):assert (rt.output_root/('episode_'+name)).exists()
    from pathlib import Path
    archived=Path(result['moved'][0]['archive_path'])
    assert (archived/'meta.json').is_file()
    assert rt.library.read_work(rt.account_id,result['moved'][0]['work_id'])['state']=='deleted'
    assert cleanup(rt)['count']==0
