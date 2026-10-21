> 现状：0.6.2已正式发布，双平台公开下载与更新清单校验完成
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-21

# 分发验收

## 0.6.2正式发布（2026-10-21）
本地正式包现集中保留于outputs/releases/0.6.2（含SHA256SUMS.txt、release-metadata.json），0.5.17回滚安装包保留一份于outputs/releases/0.5.17。发布后已清理重复构建/下载/解包产物与旧候选包；保留验收回执、源码回滚副本和原安装备份，历史回执中的构建路径不保证二进制仍存在。清理明细见verification/development-cleanup-20261021。

[Release](https://github.com/lyzbcy/sticker-maker/releases/tag/v0.6.2)对应源码d7c0b23。Windows主题安装器207169062字节（较上一公开版448486444字节减少53.81%），Mac ARM64包230049160字节（较508264026字节减少54.74%）。Windows正式封装中内嵌后端与已验收205 MB候选相同，3份主程序/asar/冻结引擎载荷SHA与候选打包目录一致；安装界面已渲染检查。本次没有替换用户现有正式安装。

双端公开文件均匿名完整下载，大小与SHA同本地最终文件、GitHub资产digest和官网version.json一致；实际更新器对0.5.15/0.5.17识别更新、对0.6.2不重复提示，Win/Mac选包和文件校验通过。官网页面与清单均为0.6.2。详细证据verification/public-release-0.6.2；Release附SHA256SUMS.txt与release-metadata.json。

发布默认使用本地Windows和SSH原生Mac构建，三个仓库Actions工作流均disabled_manually，并移除push/tag自动触发。官网的GitHub Pages配置为legacy、gh-pages分支根目录，静态文件含.nojekyll；GitHub平台自带Pages发布任务39561606954成功，计费毫秒0，没有运行双端构建Actions。后续发布上传已验收资产后，再将desktop/site整棵树提交到gh-pages，必要时调用POST /repos/lyzbcy/sticker-maker/pages/builds，并回读公网确认，不启用历史编译工作流。

Windows SHA256：`57cd5226993ee8a1b13072be2c98b07ccdb7d939a13cdbe423594b8c145cac01`；Mac SHA256：`4a1bd5f0ebab4c44f92432d1fd4eacb86257b4d6bf761932ac19817c17b011f2`。Mac使用ad-hoc签名，未Apple公证。

## 0.6.2本地瘦身候选（2026-10-21）
默认发行构建不重复打包Chromium，保留Playwright库/驱动与图像处理引擎，优先使用本机Edge/Chrome；缺少或需要备用浏览器时在问题与警告页安装可选组件。Windows候选205 MB，较0.6.1候选448 MB减少54.27%；Mac ARM64候选230 MB。双端共用源码，本轮Windows本机与Mac SSH原生构建、运行、签名及隔离安装验收完成，严格未使用Actions。没有替换正式安装或公开发布新版本。见[处理记录](desktop-usability-20261021.md)及verification/docx-tasks-20261021；下方正式0.5.15的包大小属于历史已发布版本。

## 0.5.15正式更新验收（2026-10-14）
本机最终候选已安装并核验PE/asar/IPC版本、3份payload SHA、fast_shelf/cli/hooks冻结语义、真实预约与状态持久化，699后端+98桌面回归通过。旧0.5.14完整安装备份保留；公开包与本机候选的SHA分别记录，不假称相同产物。
清洁CI已去掉升级目标0.5.1硬编码，保持真实旧版替换与作品sentinel验证；依赖锁校正为官方registry的实际版本、步骤失败立即停止。run38535103836双平台验收通过；Release38537670224、Pages38538966823成功。公网清单和页面0.5.15，实际更新器对旧0.5.1识别新版本、对当前0.5.15不重复提示，Win/Mac两份完整公开文件下载SHA与GitHub digest、清单三方匹配。最新全量692通过/6跳过、桌面98通过；四件交付和全部命令见verification/shelf-integration-20261014/VERIFICATION.txt。

粉丝路径见fan-guide.md：下载安装→安装生图组件→自己登录→选角色→做1组→本地ZIP→可选微信投稿。批量默认不投稿；不附赠账号/额度。

正式Windows安装包约444MB，Mac约499MB；从GitHubRelease获取（包括浏览器运行时，粉丝无需Python/Node）。安装器为主题WPF前端+静默NSIS后端。Source/UI/Frozen三层分开测试。旧版0.5.0迁移需先手动安装一次修复版。

历史0.5.1正式Release流水线38389217935成功；官网公共version.json已回读为0.5.1。QA38386084597与38387951697双平台全绿；最终Win/Mac文件完整下载SHA校验与35项启动器严格检查exit0已完成。QA候选和正式重建产物哈希分别记录，不混用。

普通粉丝仍需可用ChatGPT登录与相应生图额度及网络。首次提供简单中文说明，生成与微信投稿账号不捆绑。

公开客户端仅配置公开反馈转发接口；企微机器人密钥不放公开源码或安装包。未配置时反馈草稿保留并可复制诊断信息，不能误报已发送。
