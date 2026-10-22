# mini_code 插件仓库

给 [mini_code](https://github.com/zhoujiannan-nb/mini_code) 用的公开插件/素材仓库。
目前只有一类东西：**开机动画**（`boot-anim/`）。以后各种主题（聊天底图、大字横幅、
开场视频……）按同样的目录约定往这里加。

mini_code 的「配置 → 开机动画 → 在线获取」直接读本仓库根目录的
[`index.json`](index.json)，列表、下载、装到本地都在应用里完成，不用手工拷文件。

## 现有主题

| 主题 | 时长 | 一句话 |
|---|---|---|
| [技术档案](boot-anim/mc-tech-archive/) `mc-tech-archive` | 9.4s | 睁眼开场 + 语音「你好,我是 Mini Code」+ 品牌字距展开 → 环形准星 → 过曝洗白(带音效)→ 三步文字序列 → 色散故障揭幕 |
| [极简终端](boot-anim/mc-minimal/) `mc-minimal` | 2.6s | 四行终端打字 + 扫描线 + `ready.`，嫌长就用这个（无声） |

## 本地跑起来看

主题按**不可信第三方页面**跑（宿主用 `sandbox="allow-scripts"` 的 iframe 加载，并给
`/boot-anim/*` 下发 `connect-src 'none'` 的 CSP），所以预览也得走 http：

```bash
cd mini_code-plugins
python -m http.server 8700
# 打开 http://127.0.0.1:8700/preview/  ← 宿主模拟器:选主题、调速度、看 postMessage 时序
```

`preview/index.html` 的加载规则与真宿主完全一致（sandbox、handoff 叠化、硬超时），
写主题时拿它当唯一验收环境就够。

## 我想写一个主题

看 [docs/theme-contract.md](docs/theme-contract.md)。三步：

1. `boot-anim/<你的 id>/` 里放 `theme.json` + `index.html`（+ `preview.svg`）；
2. `python tools/make_index.py` 校验并重新生成 `index.json`；
3. 提 PR。

纯前端、无构建步骤、无依赖 —— 会写 HTML/CSS 就能写主题。

## 语音/音效素材

`boot-anim/mc-tech-archive/` 里那两句台词（`voice-hello.wav` / `voice-welcome.wav`）和
音效 `sfx-flash.wav` 是用 `tools/gen_audio.py` 离线合成的（Windows 自带中文 TTS
Microsoft Huihui + 纯 python 合成的正弦/噪声音效），不联网、可复现：

```bash
python tools/gen_audio.py            # 重新生成到主题目录
python tools/gen_audio.py --voice "" # 用系统默认音色
```

换台词改脚本里的 `LINES`；主题按文件名读取，换素材不用改代码。
声音能不能放出来见 [docs/theme-contract.md](docs/theme-contract.md) 的「语音与音效」一节
（自动播放策略是真正的门槛，桌面版已经放宽）。

## 目录约定

```
index.json                 机器读清单(tools/make_index.py 生成,别手改)
boot-anim/<id>/            开机动画主题
preview/                   宿主模拟器(本地预览用)
docs/theme-contract.md     契约 v1
tools/make_index.py        校验 + 生成 index.json
```

## 致谢

开机动画的分幕结构、"中文主字 + 英文等宽副标题逐字打出"、以及 **handoff 时机**
（在淡出**开始**那一帧就通知宿主叠化，否则交界处会闪一下）这几处手法，借鉴自：

- [dsh-startup-screen](https://github.com/LeeRolling/dsh-startup-screen) — MIT, (c) LeeRolling
- [dsh-chat-wallpaper](https://github.com/LeeRolling/dsh-chat-wallpaper) — MIT, (c) LeeRolling

那两个是给 DeepSeek Harness 写的插件。本仓库**没有复制它们的代码**，只借了手法，
并把标识换成了 mini_code。

## 许可

MIT — 见 [LICENSE](LICENSE)。主题里请自己在 `theme.json` 的 `license` 字段署上作者。
