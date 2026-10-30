# 小鲸鱼直播套装 · AI 虚拟主播

一个能自己开播的 AI 虚拟主播：读弹幕、回话、念礼物、点歌、做动作。Windows 本地运行，接 OBS 推流到抖音直播伴侣。

> 新人先看 [`README-先看这个.md`](README-先看这个.md)，那是三步上手指南。
> 交给 AI 搭建看 [`给AI的搭建说明.md`](给AI的搭建说明.md)，里面有全部技术步骤和排查表。

## 组成

| 模块 | 文件 | 作用 |
| --- | --- | --- |
| 主播引擎 | `主播引擎.py` | 主循环：读弹幕 → 大模型生成回复 → TTS 出声 → 驱动形象 |
| 弹幕采集 | `弹幕采集.py`、`识屏.py` | 屏幕识别 / 直连两种取弹幕方式 |
| 弹幕转接 | `弹幕转接.py`、`标记服务.py` | 把弹幕投喂给引擎 |
| 抖音直连 | `抖音直连.py` | WebSocket 直连直播间，免读屏 |
| 形象渲染 | `形象.html`、`背景气泡.html` | OBS 浏览器源，PNG 睁眼/闭眼切换 |
| 字幕卡 | `字幕卡.py` | 生成当前台词字幕图 |
| 点歌收播 | `收播.py`、`点歌面板底.png` | 点歌队列与收播流程 |
| 启动脚本 | `开播.bat`、`控制面板.bat`、`重启监听器.bat` | 一键启停 |

## 快速开始

```bash
# 1. 装依赖
pip install requests websockets edge-tts pillow

# 2. 配置（从模板复制，填自己的 key）
copy config.example.json config.json

# 3. 开播
开播.bat
```

`config.json` 需要填两项：

- `api_key` — DeepSeek 的 key，[platform.deepseek.com](https://platform.deepseek.com) 注册
- `obs_password` — OBS → 工具 → WebSocket 服务器设置 里的密码

## 环境要求

- Windows 10 / 11
- Python 3.10+
- OBS Studio（免费）
- 抖音直播伴侣（PC 版）
- ffmpeg（本仓库未附带，自行下载 `ffmpeg.exe` 放根目录）

## 关于本地运行时目录

运行时会生成 `_登录配置/`、`_音乐缓存/`、`_弹幕监听/`、`_弹幕直连/`、`_tts/` 以及各类 `*日志.txt`。这些都是本地产物，已在 `.gitignore` 中排除，不会进仓库。

同理，`config.json`、`_cookie.txt` 含密钥与登录态，永不提交。

## 三条硬规矩

1. 发作品必须勾选「内容由 AI 生成」。
2. 开播时直播伴侣要放前台，读屏模式被遮挡就读不到弹幕。
3. 不能挂着不管，抖音会判「非实时直播」封禁。

## 免责

仅供个人学习与自用。直播内容合规、账号行为规范由使用者自负，请遵守平台规则与当地法律法规。
