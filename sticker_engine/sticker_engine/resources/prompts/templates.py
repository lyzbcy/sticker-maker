"""三模式的 prompt 模板（移植自现有 reference/prompt-templates.md）。"""

# 参考图库模式：base + N 张参考图，每张参考图对应一个 panel
REF_LIBRARY_TEMPLATE = (
    "Generate a {grid}x{grid} sticker grid ({n} panels). "
    "Image 1 is the BASE character (主角，必须出现在每个 panel，保持身份一致). "
    "Images 2-{n_img} are REFERENCE stickers (仅借用姿势/表情，不要用参考图里的角色). "
    "Each panel maps to one reference. 3D clay style, soft cute. "
    "Background: keep reference backgrounds. No text in image."
)

# 故事模式：每行一个 4 格小故事
STORY_TEMPLATE = (
    "Generate a {grid}x{grid} sticker grid. Each ROW is one 4-panel mini-story (起承转合). "
    "BASE character (image 1) is the protagonist in all panels. "
    "Stories and panels: {stories_description}. "
    "3D clay style, soft cute, chat-friendly. Magenta (#ff00ff) solid background. "
    "No shadows on background. No text in image."
)

# 排列组合模式：关键词随机组合
KEYWORD_COMBO_TEMPLATE = (
    "Generate a {grid}x{grid} sticker grid ({n} panels). "
    "BASE character (image 1) in all panels. "
    "Each panel: random emotion + action from lists. Panels: {panels_description}. "
    "3D clay style, soft cute. Magenta (#ff00ff) solid background, no shadows. No text."
)
