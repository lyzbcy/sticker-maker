---
name: lyzbcy-sticker-shelf
description: "自动上架微信表情开放平台「审核通过」的专辑。从最后一页往前逐页处理，预约今日上架，保证先通过审核的先上架。复用 publisher 登录态。"
---

中文名称：微信表情自动上架工具
能力简介：扫描作品列表里所有「审核通过」的单品专辑，自动点详情→上架→选今日→预约，批量完成今日上架。
使用场景：创作并通过审核的表情专辑，需要批量预约上架时使用。

# 微信表情自动上架工具 - Sticker Shelf

## AI 统一执行协议

<system-goal>
本 skill 的目标是稳定上架「审核通过」的专辑，预约今日上架。
把页面当成固定流程表单，按既定 7 步顺序执行，失败就停并报错，不要瞎猜。
</system-goal>

<shelf-hard-rules>
1. 只处理状态为「审核通过」的单品专辑；绝不碰「已上架 / 审核中 / 已下架」。
2. 只点单曲行的「详情」链接 `a[href="javascript:;"]`，绝不点形象详情 `a[href*="ip/detail"]`。
3. 复用 publisher 的登录态（.browser-data）和 .env 凭据，不扫码、不向用户索要密码。
4. 翻页必须从 min(5, 总页数) 往前到第 1 页，保证先审核通过的（低弹数）先上架。
5. 每页清空后必须刷新复查（自我审查），残留则补处理。
6. 预约就是「今日上架」，不要去选别的日期。
</shelf-hard-rules>

<shelf-7-step-flow>
对应需求 `.openclaw/自动将检测通过的发布.md` 的 7 步：

1. 打开首页 `https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index`，定位「审核通过」单曲行
2. 单击该行的「详情」（单曲详情链接 `a[href="javascript:;"`）
3. 等待几秒，详情页加载（同页跳转到 `stickerPage/setting?stikerid=...`）
4. 单击「上架」按钮（`div[data-v-e67065cd] button.weui-desktop-btn_primary`，文本"上架"）
5. 「预约上架」弹窗出现后，点日历「今日」（`a.weui-desktop-picker__current`；默认就已选中今日，显式点一次作保险）
6. 单击「预约」按钮（`div.weui-desktop-dialog__ft button.weui-desktop-btn_primary`，文本"预约"）
7. 确认预约成功（弹窗消失 / 出现成功文案），返回列表继续下一个
</shelf-7-step-flow>

<pagination-strategy>
翻页设计（需求的伪代码）：
- 总页数可能大于 5，但默认只处理最近 5 页（`--max-pages` 可调）
- 起始页 = min(5, 总页数)，从该页往前逐页处理到第 1 页
- 因为列表按更新时间倒序，靠后的页是更早通过的（低弹数），往前处理即可让先通过的先上架
- 自我审查：每页处理完后刷新该页，确认无「审核通过」残留再进上一页
</pagination-strategy>

<selectors-reference>
首页（inspect_home_result.json 已固化）：
- 列表行：`tbody.table_body > tr.table_tr`
- 状态：行内 `span.emotion_status.suc` 文本"审核通过"
- 单曲详情链接：`a[href="javascript:;"]`（区别于形象 `a[href*="ip/detail"]`）
- 总页数：`label.weui-desktop-pagination__num`（两个：当前页/总页数，取末位）
- 跳转：`.weui-desktop-pagination__input` 输入框 + 「跳转」按钮；兜底用「上一页」`a`

详情页（inspect_detail_result.json 已固化）：
- 上架按钮：`button.weui-desktop-btn_primary` 文本"上架"，外层 `div[data-v-e67065cd].weui-desktop-btn_wrp`
- 预约弹窗容器：`div.dialog_shelf`（点上架后 display:block）
- 今日单元格：`a.weui-desktop-picker__current`（弹窗打开即默认选中今日）
- 预约按钮：`div.weui-desktop-dialog__ft button.weui-desktop-btn_primary` 文本"预约"
- 成功标志：body 文案含「已预约/预约成功/上架成功」或弹窗消失
- 返回列表：`page.goBack()`（同页跳转）兜底 `goto(HOME_URL)`
</selectors-reference>

## 🔴🔴🔴 铁律（不可违反，违反即为 BUG）

1. **绝对只上架「审核通过」**：状态判断必须精确，已上架/审核中/已下架一律跳过
2. **绝对不要扫码登录**：登录走 publisher 共享登录态或 .env 账号密码
3. **绝对不要让用户手动操作**：所有点击由脚本完成，用户只等结果
4. **预约就是今日**：打开日历默认已选中今日，不要去选历史/未来日期
5. **失败保现场**：找不到元素就截图 + 记录 + 报错，不要刷新清掉线索
6. **不要重复上架**：详情页若无「上架」按钮（状态已变）则 SKIP，不要硬找

---

## 使用指南

### 0. 前置条件
- 已配置 publisher 的 `.env`（`WECHAT_STICKER_ACCOUNT` + `WECHAT_STICKER_PASSWORD_ENCODED`）
- publisher 的 `.browser-data` 有有效登录态（或 .env 凭据可自动登录）
- Edge 在 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`

### 1. 探测（首次或页面改版时）
详情页只读探测，固化选择器：
```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-shelf\scripts"
npm run inspect-detail    # 或 node inspect_detail.js
# 结果写入 inspect_detail_result.json，人工核对后据此调整 shelf.js
```
首页探测同理：`npm run inspect`。

### 2. 试运行（dry-run，只点详情不点上架）
```bash
node shelf.js --dry-run --max-pages 5
```
dry-run 模式会走到详情页确认「上架」按钮存在就返回，**不会真上架**，用来验证列表/翻页/详情定位是否正常。

### 3. 小范围真实上架（推荐先跑）
```bash
node shelf.js --limit 1        # 只预约上架 1 个，验证全链路
node shelf.js --limit 3        # 先上 3 个观察
```
`--limit` 控制本次预约上架的总数（成功/失败都计数），适合先小范围验证再放量。已实测 `--limit 1` 可完整走通"点详情→上架→选今日→预约→平台状态变更"。

### 4. 全量真实上架
```bash
node shelf.js                  # 默认最多翻 5 页
node shelf.js --max-pages 3    # 自定义页数
```
运行后会：从第 min(5,总页数) 页往前，逐页把「审核通过」预约今日上架，每页结束刷新复查。
参数可组合：`--limit N`（限制本次处理 N 个）、`--max-pages N`（最大翻页数）、`--dry-run`。
结果写入 `_shelf_result.json`：
```json
{ "summary": {"ok":N,"fail":N,"skip":N,"unknown":N},
  "results": [{"page":6,"name":"周三涵做表情48","status":"OK","reason":""}, ...] }
```
状态：`OK`(预约成功) / `FAIL`(失败) / `SKIP`(无上架按钮，可能已上架) / `UNKNOWN`(未确认)。

### 4. 失败处理
- 看 `_shelf_result.json` 里 FAIL/UNKNOWN 的项
- 看 `screenshot_*.png`（无弹窗/未确认时自动截图）
- 修复后重跑（脚本幂等：已预约/已上架的会 SKIP）

## 已知现实（known-gap）
- 详情页 DOM 依赖 `inspect_detail.js` 探测结果；微信改版后弹窗/按钮选择器可能失效，需重跑探测
- 「今日」依赖日历默认选中；若平台改为默认不选，`clickToday()` 会兜底点 `a.weui-desktop-picker__current`
- 预约成功判定用「文案 + 弹窗消失」双信号，偶发动画延迟可能判 UNKNOWN（需人工核对截图）
- 一次运行建议控制在合理弹数内（每弹约 15-25 秒），大量积压可分次跑
