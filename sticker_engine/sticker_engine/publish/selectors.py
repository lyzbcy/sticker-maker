"""微信表情开放平台选择器常量（集中管理，平台改版只改这里）。

策略（spec 决策）：优先 text/role 选择器（比 weui class 稳），class 作回退。
选择器命名对应 publisher 的 24 步 / shelf 的 7 步。
"""

# 平台地址
HOME_URL = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index"

# === 登录 ===
LOGIN_ACCOUNT_TAB_TEXT = "账号密码登录"      # 切换到账号密码登录 tab
LOGIN_BUTTON_TEXT = "登录"                    # 登录按钮
LOGIN_ACCOUNT_INPUT = 'input[type="text"]'    # 账号输入框（登录页）
LOGIN_PASSWORD_INPUT = 'input[type="password"]'

# === 提交作品入口 ===
SUBMIT_WORK_BUTTON_TEXT = "提交作品"
ALBUM_TYPE_TEXT = "表情专辑"

# === 表情类型 ===
STATIC_RADIO = 'i.weui-desktop-icon-radio'   # 静态（点击选静态）

# === 上传表情图 ===
STICKER_UPLOAD_LABEL = 'label[style*="cursor: pointer"]'   # 触发文件选择

# === 含义词输入 ===
MEANING_INPUT = 'input.weui-desktop-form__input[placeholder="输入含义词"]'

# === 专辑信息 ===
ALBUM_NAME_INPUT = 'input.weui-desktop-form__input[placeholder*="表情专辑名称"]'
INTRO_TEXTAREA = 'textarea.weui-desktop-form__textarea[placeholder*="特点和故事"]'
COPYRIGHT_INPUT = 'input.weui-desktop-form__input[placeholder*="版权信息"]'

# === 横幅/封面/图标上传区 ===
UPLOADER_INIT = 'div.uploader__init span.weui-desktop-icon__add'
ICON_UPLOAD_ICON = 'span.weui-desktop-icon__add'

# === 类型细分 / 风格 / 主题 / 地区 ===
CATEGORY_RADIO_VALUE = "1"                    # 卡通表情/其他
ROLE_DROPDOWN_DT = 'dt.weui-desktop-form__dropdowncascade__dt'
ROLE_FIRST_LEVEL = "人物角色"
ROLE_WITH_LAOYU_TITLE = "人物合辑(包含以上多个)"
ROLE_WITHOUT_LAOYU_TITLE = "女人"
STYLE_CHECKBOX_SOFT = 'input[type="checkbox"][value="软萌可爱"]'
STYLE_CHECKBOX_DAILY = 'input[type="checkbox"][value="日常"]'
THEME_RADIO_VALUE = "万能通用"
REGION_RADIO_VALUE = "DEF"                    # 全球

# === 赞赏 ===
ACCEPT_TIPS_CHECKBOX = 'input[type="checkbox"]'   # 接受赞赏（具体位置靠文本定位）
TIPS_TEXT_INPUT = 'input.weui-desktop-form__input[placeholder*="最少填写"]'
PRICE_FREE_RADIO_VALUE = "true"               # 免费

# === 裁剪框确定（经验13：uploadFile 后要点确定）===
CROP_CONFIRM_TEXT = "确定"

# === 提交 ===
SUBMIT_BUTTON_TEXT = "提交"

# === 上架（shelf）===
SHELF_STATUS_PASS = "审核通过"
SHELF_DETAIL_LINK = 'a[href="javascript:;"]'   # 单曲详情（区别于形象 ip/detail）
SHELF_BUTTON_TEXT = "上架"
SHELF_TODAY_CELL = 'a.weui-desktop-picker__current'
SHELF_CONFIRM_TEXT = "预约"
SHELF_PAGINATION_TOTAL = 'label.weui-desktop-pagination__num'
SHELF_PAGINATION_INPUT = '.weui-desktop-pagination__input'

# === 分页 ===
PAGINATION_PREV = 'a.weui-desktop-pagination__prev, a:has-text("上一页")'


def upload_success_thumbnail_check():
    """赞赏图上传成功判定：uploader 区域 img 数量增加（经验12）。"""
    return '[class*="uploader"] img'
