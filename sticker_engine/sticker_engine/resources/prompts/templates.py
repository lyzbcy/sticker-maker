"""三模式的 prompt 模板。

2026-08 重写：吸收 GitHub 优秀 sticker prompt 案例（awesome-gpt4o-images
Case 21/27/28 等）的共性技巧——
1. 每格动作/表情要"画面级具体"（tearful eyes and slightly trembling lips），
   而不是抽象词（happy）；
2. Chibi 美学显式规格：夸张大眼、柔和圆脸线、大头身比；
3. 贴纸质感：白描边（die-cut sticker look）、每格留白、肢体完整不断裂、
   无漂浮多余元素；
4. 负面约束显式化：无文字/水印/阴影。
"""

# ---- 统一风格块（三个模式共用，保证一套里风格严格一致） ----
_STYLE_BLOCK = (
    "STYLE (strictly identical across all panels):\n"
    "- Keep every panel CUTE and lovable (kawaii): soft pastel colors, gentle "
    "rounded shapes; never scary, grotesque, undead, ghostly, zombie-like, "
    "injured or dirty; exaggeration must always stay adorable\n"
    "- Chibi proportions: oversized head with a tiny stubby body, about "
    "two-heads-tall; round head wider than tall; no visible joints or bones\n"
    "- Face: huge sparkly eyes placed LOW on the head with a large forehead, "
    "rosy blush cheeks, exaggerated expressive big eyes, soft rounded lines\n"
    "- 3D clay style, soft matte clay material, soft studio lighting\n"
    "- Each sticker gets a uniform thin white outline (die-cut sticker look) "
    "and a clean margin around it inside its cell\n"
    "- Every character fully visible inside its own cell: no cropped "
    "limbs/tails/hair, nothing floating or detached, no extra stray elements\n"
    "- Characters must never touch or cross the grid divider lines: keep "
    "completely empty background gutters between neighboring cells; every "
    "body part (feet, hands, ears, props) stays FULLY inside its own panel "
    "— a panel whose content touches the gutter gets DISCARDED\n"
    "- No banner, ribbon, strip or decorative frame along the bottom or "
    "edges of any panel\n"
    "- Outfits stay modest in every pose (falling, lying, tumbling): never "
    "show underwear or immodest exposure\n"
    "- Exactly two arms and two legs per character — never draw extra "
    "or duplicated limbs\n"
    "- If the character sticks out its tongue, keep it TINY and cute — "
    "never a large or floppy tongue\n"
    "- Background: solid magenta (#ff00ff), completely flat — no shadows, "
    "no gradients, no scenery\n"
    "- Absolutely no text, letters, numbers or watermarks in any panel"
)

# 参考图库模式：base + N 张参考图，每张参考图对应一个 panel
# （良品率本就最高的模式：只加强贴纸质感与完整性的约束）
REF_LIBRARY_TEMPLATE = (
    "Generate a {grid}x{grid} sticker sheet ({n} panels, evenly spaced grid).\n"
    "Image 1 is the BASE character — the protagonist who must appear in EVERY "
    "panel with identical identity, outfit, hairstyle and colors.\n"
    "Images 2-{n_img} are REFERENCE stickers: borrow ONLY the pose/expression "
    "idea of each reference into the matching panel; never copy the reference "
    "characters themselves.\n"
    "One panel per reference, same order as given.\n"
    + _STYLE_BLOCK
)

# 故事模式：每行一个 4 格小故事（起承转合）
STORY_TEMPLATE = (
    "Generate a {grid}x{grid} sticker sheet ({n} panels, evenly spaced grid). "
    "Each ROW is one 4-panel mini-story with a clear setup-turn-resolution "
    "arc; panels inside a row read left to right.\n"
    "Image 1 is the BASE character — the protagonist of every panel, "
    "identical identity/outfit/hairstyle throughout.\n"
    "Stories and panels: {stories_description}\n"
    "For every panel make the emotion readable at chat-icon size: exaggerated "
    "facial expression plus one unmistakable body action.\n"
    + _STYLE_BLOCK
)

# 排列组合模式：情绪+动作+点缀 随机组合
# panels_description 由 keywords.json 的画面级描述拼成（不再是抽象单词）
KEYWORD_COMBO_TEMPLATE = (
    "Generate a {grid}x{grid} sticker sheet ({n} panels, evenly spaced grid).\n"
    "Image 1 is the BASE character — the protagonist of every panel, "
    "identical identity/outfit/hairstyle throughout.\n"
    "Panels (one scene per panel, follow this order):\n{panels_description}\n"
    "CHAT-USE FIRST: every panel must work as a STANDALONE chat sticker — "
    "one instantly readable emotion plus one unmistakable body action, "
    "understood in under a second with zero context; a panel that only makes "
    "sense next to its neighbors is a failure.\n"
    + _STYLE_BLOCK
)
