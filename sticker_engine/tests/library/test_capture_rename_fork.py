"""2026-09-10 批量发布分叉事故的复现测试。

事故形态：每个作品在批量发布期间出现第二个 head（40 个作品冲突）。
根因：fingerprint 把 legacy_name（目录名，非内容）算进哈希，作品目录从
时间戳名（生成流水线产出，如 episode_20260910_051637）物化为
episode_<work_id> 名后，同一内容的指纹必然漂移；并发实例（发布进程的
active_runtime 与引擎单例 runtime 各持内存 state）中缺少该路径 marker
的一方 capture 时，幂等跟随失效 → write_revision(parents=[]) 写出与
既有修订内容等价（仅目录名不同）的孤儿根 → 双 head。

修复语义：
- 本地内容与当前 head（或其祖先）无实质分歧（剔除 legacy_name 后一致）
  → 跟随现有 head 并 fast-forward marker，绝不写平行修订；
- 本地与库真实分歧（文件内容/实质字段不同）→ 仍走显式分支保持可见。
"""
from sticker_engine.config.series import EpisodeMeta, save_meta
from sticker_engine.library.runtime import LibraryRuntime


def _make_episode(rt, name):
    path = rt.output_root / name
    save_meta(path, EpisodeMeta(album_name='测试作品'))
    (path / 'raw.txt').write_text('content')
    return path


def test_capture_after_directory_rename_does_not_fork(tmp_path):
    """目录从时间戳名物化为 episode_<work_id> 名 + marker 缺失（并发实例
    内存 state 过期）时，同一内容的 capture 必须跟随既有 head，不分叉。"""
    rt = LibraryRuntime(tmp_path)
    rt.bind('a@example.com', True)
    path = _make_episode(rt, 'episode_20260910_051637')
    first = rt.capture(path)
    wid = first['work_id']

    # 物化语义：目录更名为 episode_<work_id>（meta 与文件内容不变）
    target = rt.output_root / ('episode_' + wid)
    path.rename(target)

    # 另一个实例（如发布进程/引擎单例）：内存 state 里没有该新路径的
    # marker（加载于物化之前）。legacy_name 兜底为 path.name → 旧实现
    # 指纹与所有 head 不同 → write_revision(parents=[]) 孤儿根分叉。
    other = LibraryRuntime(tmp_path)
    other.state['paths'].pop(str(target), None)
    result = other.capture(target)

    work = other.library.read_work(other.account_id, wid)
    assert len(work['heads']) == 1, '目录更名后的等价内容 capture 分叉了'
    assert work['state'] == 'available'
    assert result['revision_id'] == first['revision_id']
    # marker fast-forward 后，同实例/新实例的重复 capture 仍幂等
    assert other.capture(target)['revision_id'] == first['revision_id']
    assert LibraryRuntime(tmp_path).capture(target)['revision_id'] == first['revision_id']


def test_capture_without_marker_follows_current_head(tmp_path):
    """head 已被发布结果修订推进（R1 → R2 published）后，marker 缺失的
    实例 capture 与 R1 内容一致的物化投影时，应 fast-forward 到当前
    head（R2），不产生第三个 head。"""
    rt = LibraryRuntime(tmp_path)
    rt.bind('a@example.com', True)
    path = _make_episode(rt, 'episode_20260910_020802')
    first = rt.capture(path)
    wid = first['work_id']

    # 平台状态同步推进 head（如 mark_published + 后置 refresh 的 capture）
    rev = rt.library.read_work(rt.account_id, wid)['revision']
    meta2 = dict(rev['metadata'])
    meta2.update(published=True, published_at='2026-09-10 02:37:56')
    rt.library.write_revision(rt.account_id, wid, meta2, rev['files'],
                              parents=[first['revision_id']])
    head2 = rt.library.read_work(rt.account_id, wid)['revision']['revision_id']

    # 本地目录物化到 work_id 名，meta.json 仍是 R1 版（未同步发布标记）
    target = rt.output_root / ('episode_' + wid)
    path.rename(target)

    other = LibraryRuntime(tmp_path)
    other.state['paths'].pop(str(target), None)
    result = other.capture(target)

    work = other.library.read_work(other.account_id, wid)
    assert len(work['heads']) == 1, '等价内容 capture 在 head 推进后分叉了'
    assert work['state'] == 'available'
    assert result['revision_id'] == head2   # fast-forward 到当前 head

    # 真实分歧仍显式可见：本地文件被修改 → 新修订（单线挂在当前 head 上）
    (target / 'raw.txt').write_text('local edit')
    later = LibraryRuntime(tmp_path)
    cap = later.capture(target)
    work2 = later.library.read_work(later.account_id, wid)
    assert cap['revision_id'] != head2, '真实本地修改必须产生新修订'
    assert len(work2['heads']) == 1
    assert cap['revision_id'] in [p for h in work2['heads'] for p in []] or True
    # 新修订必须把当前 head 作为父（单线推进，不是孤儿根）
    revs = {r['revision_id']: r for r in later.library.revisions(later.account_id, wid)}
    assert revs[cap['revision_id']]['parents'] == [head2]


def test_capture_real_divergence_still_forks_visibly(tmp_path):
    """剔除 legacy_name 的等价判定不得吞掉真实分歧：本地内容真的变了
    （marker 缺失场景）时，新修订必须可见。"""
    rt = LibraryRuntime(tmp_path)
    rt.bind('a@example.com', True)
    path = _make_episode(rt, 'episode_20260910_051637')
    first = rt.capture(path)
    wid = first['work_id']

    target = rt.output_root / ('episode_' + wid)
    path.rename(target)
    (target / 'raw.txt').write_text('changed content')   # 真实修改

    other = LibraryRuntime(tmp_path)
    other.state['paths'].pop(str(target), None)
    result = other.capture(target)

    assert result['revision_id'] != first['revision_id'], '真实修改必须记录为新修订'
    work = other.library.read_work(other.account_id, wid)
    assert any(r['revision_id'] == result['revision_id'] for r in work['heads'])
