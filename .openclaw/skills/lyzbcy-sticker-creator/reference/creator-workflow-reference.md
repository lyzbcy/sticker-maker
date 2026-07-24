# Creator Workflow Reference

## 作用

这份 reference 只放结构化流程说明：
- 统一文件夹结构
- `本次制作角色.md` 协议
- 生成策略
- 当前推荐工作流

主入口仍然以 `SKILL.md` 为准。

## 统一文件夹结构

详见总规范：
`E:\星星布丁\微信表情包\.openclaw\skills\README.md`

```text
周三涵做表情N/
├── 本次制作角色.md
├── 参考图/
├── 原图/
├── 原图_透明ChromaKey/
├── 最终版/
├── 横幅/
├── 封面/
├── 图标/
├── 帧图/
└── *.gif
```

## 本次制作角色.md 协议

用途：
- creator 写入
- publisher 读取
- 用于决定“角色/内容”选择

模板：

```markdown
# 本次制作角色

## 基本信息
- 弹次：周三涵做表情N
- 类型：静态表情/动态表情
- 模式：single/duo/quad/auto
- 生成日期：YYYY-MM-DD

## 角色列表
- 星星布丁
- 捞鱼

## 含捞鱼：是/否

## 发布指引（供 lyzbcy-sticker-publisher 读取）
- 含捞鱼：是 → 选择「人物合辑(包含以上多个)」
```

发布规则：
- 含捞鱼：是 -> `人物合辑(包含以上多个)`
- 含捞鱼：否 -> `女人`

## 生成策略

### 模式

| 模式 | 参数 | 角色 |
|------|------|------|
| 单人 | `--mode single` | 单个角色 |
| 双人 | `--mode duo` | 星星布丁 + 捞鱼 |
| 四人 | `--mode quad` | 星星布丁 + 捞鱼 + 周三涵 + 周五涵 |
| 自动 | `--mode auto` | 按配置概率选择 |

### 参考图策略

- 单人/四人模式：排除 `【双人】`
- 双人模式：优先使用 `【双人】`
- 库存不足时：回退 AI 模板模式

## 当前推荐工作流

1. `prep_episode.py`
2. `validate.py --stage pre_generate`
3. Codex 生图
4. `crop_grid.py`
5. Chroma-key 或单图抠图
6. 视觉复核含义词
7. 写入 `最终版/`
8. `make_assets.py`
9. `validate.py --stage pre_publish`
10. `publish.js`

## 当前不建议当主流程的内容

- 旧版 ChatGPT 网页自动化
- 云服务器自动部署
- 把历史样例当模板直接复用

