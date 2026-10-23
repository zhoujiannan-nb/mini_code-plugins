# mini_code 插件仓库

给 [mini_code](https://github.com/zhoujiannan-nb/mini_code) 用的公开插件/素材仓库。
目前只有一类东西：**开机动画**（`boot-anim/`）。以后各种主题（聊天底图、大字横幅、
开场视频……）按同样的目录约定往这里加。

mini_code 的「配置 → 开机动画 → 在线获取」直接读本仓库根目录的
[`index.json`](index.json)，列表、下载、装到本地都在应用里完成，不用手工拷文件。

## 现有主题

| 主题 | 时长 | 一句话 |
|---|---|---|
| [接入序列](boot-anim/mc-access/) `mc-access` | 17.8s | 复刻 dsh-startup-screen 的电影感序列：黑幕芯片标识 → 过曝洗白 → 五步接入（**真声女声播报** + 底噪 + 咔哒音效）→ 色散故障揭幕。品牌已是 Mini Code，终幕只念一声 `Welcome` |

嫌长就把「配置 → 开机动画 → 速度」调快（宿主的 `speed` 会一起压缩画面节奏），
不想听声音就勾「静默」——勾上后主题连音频文件都不会去下载。

## 本地跑起来看

主题按**不可信第三方页面**跑（宿主用 `sandbox="allow-scripts"` 的 iframe 加载，并给
主题文件下发 `connect-src 'none'` 的 CSP），所以预览也得走 http：

```bash
cd mini_code-plugins
python -m http.server 8700
# 打开 http://127.0.0.1:8700/preview/  ← 宿主模拟器:选主题、调速度、看 postMessage 时序
```

`preview/index.html` 的加载规则与真宿主基本一致（sandbox、handoff 叠化、硬超时）。
**一个差别要注意**：模拟器没有那条 CSP，所以 `fetch()` 在模拟器里能通、在真宿主里必挂 ——
主题拿自己的素材请用 `<img>` / `<audio>` / `<link>` 这类标签，别用 `fetch` / `XHR`。

## 我想写一个主题

看 [docs/theme-contract.md](docs/theme-contract.md)。三步：

1. `boot-anim/<你的 id>/` 里放 `theme.json` + `index.html`（+ `preview.svg`）；
2. `python tools/make_index.py` 校验并重新生成 `index.json`；
3. 提 PR。

纯前端、无构建步骤、无依赖 —— 会写 HTML/CSS 就能写主题。
改完主题**一定要重跑 `make_index.py`**，否则 `index.json` 里的 sha256 与文件对不上，
用户点安装会报校验失败（`python tools/make_index.py --check` 可以在提 PR 前自查）。

## 语音 / 音效素材

**接入序列**里的 6 句播报（`line-1.mp3` … `line-6.mp3`）和两声"咔哒"
（`sfx-tick.mp3` / `sfx-ticks-run.mp3`，合计约 1.0 MB）是**真声素材**，不是 TTS：
它们来自 [dsh-startup-screen](https://github.com/LeeRolling/dsh-startup-screen)（MIT，
素材随该仓库分发）。移植时和音频有关的两件事：

- **文件名原样保留**。想换嗓子就删掉同名 mp3 换上自己的，主题按文件名读，不用改代码。
- **只留 `Welcome` 一个词**。上游 `line-6.mp3` 原句是 "Welcome to DeepSeek Harness"，
  按 20 ms 窗量出音节边界（`Wel` `come` 到 1.60s，之后停了 0.8s 才念后半句），
  所以下面的 `TRIMS` 把它在 1.70s 处收掉 —— 画面上写的是 `WELCOME TO / MINI CODE`，
  声音就只念 `Welcome`，顺带把别人家的品牌名从声音里去掉了。
- **每条素材"说到哪儿结束"是量出来的**：用 Web Audio 逐 40 ms 窗取 RMS（阈值 -38 dBFS），
  素材尾巴上挂着 0.1 ~ 2 秒不等的死空气，`boot.js` 里的 `TRIMS` 表把死空气削掉，
  不然每一步都要多等一两秒（整段从 23.4s 压到 17.8s）。

终幕那句「欢迎 X 访问」里的 X 取宿主「配置 → 开机动画 → **身份名**」，没填就用主题
默认值（哈基米指挥官）。

整套主题是脚本从上流仓库生成的，可复现，且**每一条改动都要能匹配上**（匹配不上直接
失败退出，不会生成半成品）：

```bash
git clone https://github.com/LeeRolling/dsh-startup-screen ../dsh
python tools/port_access.py --src ../dsh
```

声音到底放不放得出来，取决于自动播放策略，见
[docs/theme-contract.md](docs/theme-contract.md) 的「语音与音效」一节（桌面版已放宽）。

## 目录约定

```
index.json                 机器读清单(tools/make_index.py 生成,别手改)
boot-anim/<id>/            开机动画主题
preview/                   宿主模拟器(本地预览用)
docs/theme-contract.md     契约 v1
tools/make_index.py        校验 + 生成 index.json
tools/port_access.py       从上流仓库移植「接入序列」(带逐条补丁,可复现)
LICENSE-DSH                上游 dsh-startup-screen 的 MIT 原文(接入序列是它的衍生作品)
```

## 致谢与来源

- **接入序列** `mc-access` 是 [dsh-startup-screen](https://github.com/LeeRolling/dsh-startup-screen)
  的**移植 + 改写**（MIT，© LeeRolling）：分幕结构、画面节奏、播报与音效都来自那个项目；
  品牌文案与标识换成了 Mini Code（原标识是 DeepSeek 的鲸鱼，不能拿来当 mini_code 的牌子，
  所以换成一枚"六边形芯片 + `>` 镂空"的几何标识），并接上了 mini_code 的宿主协议
  （`ready` / `step` / `handoff` / `done`，跳过按钮归宿主），素材加载从
  `fetch + decodeAudioData` 改成 `<audio>`（宿主的 `connect-src 'none'` 会拦 fetch）。
  上游 MIT 原文见 [LICENSE-DSH](LICENSE-DSH)，逐条改动见 `tools/port_access.py`
  与 `boot.js` 里的 `mini_code 补丁` 注释。
- 主题里 **handoff 的时机**（在淡出**开始**那一帧就通知宿主叠化，否则交界处会闪一下）这个手法借鉴自 dsh-startup-screen 与
  [dsh-chat-wallpaper](https://github.com/LeeRolling/dsh-chat-wallpaper)（都是 MIT，© LeeRolling，给 DeepSeek Harness 写的插件）。
- **音频素材的版权**：那 6 句女声播报是上游从一段 DeepSeek 宣传视频里抠出来的，
  MIT 授权覆盖的是代码，**不覆盖这段音频**。自用无妨；要把本仓库再公开分发、
  或者商用，请先确认这段音频的授权，或用同名文件换成你自己有权限的素材。

## 许可

代码与画面实现：MIT — 见 [LICENSE](LICENSE)（接入序列的衍生作品部分另见
[LICENSE-DSH](LICENSE-DSH)）。音频素材的版权不属于本仓库的 MIT 授权，见上一节。
主题里请自己在 `theme.json` 的 `license` 字段署上作者。
