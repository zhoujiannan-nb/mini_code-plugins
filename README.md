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
| [机密接入](boot-anim/mc-secret/) `mc-secret` | 17.0s | 更硬的那一款：**默认中文女声**（`line-cn-1..5`）一屏一句报读，红色徽标、右下角人物立绘、结尾「降世」事件卡都按上游素材原样保留。`voice_lang=en` 换英文，`mascot=none` 收掉立绘，`event_window=1` 才在结尾弹事件卡（默认不弹） |

嫌长就把「配置 → 开机动画 → 速度」调快（宿主的 `speed` 会一起压缩画面节奏），
不想听声音就勾「静默」——勾上后主题连音频文件都不会去下载。

### 主题自己的开关（`theme.json` 的 `options`）

宿主的设置页只给 **速度 / 身份名 / 静默 / 片尾可交互** 四个开关，剩下的开关由主题在
`theme.json` 里自己声明、以 query 传进 iframe。要改就改装到本地的那一份
`~/.mini_code/boot-anim/<id>/theme.json`（改完重启 mini_code）：

| 键 | 主题 | 默认 | 说明 |
|---|---|---|---|
| `voice_lang` | 机密接入 | `cn` | `cn` = 中文女声 `line-cn-1..5`，`en` = 英文 `line-1..5` |
| `mascot` | 机密接入 | `"0"` | 右下角人物立绘 `0`…`4`；`none` 整块不渲染（连图片请求都不发） |
| `event_window` | 机密接入 | `"0"` | `1` = 演完再弹一页「降世」事件卡，Enter/点击放行，8 s 无操作自己走 |
| `access_password` | 机密接入 | 空 | 访问密码；只在 `require_interaction=1` 时生效，拦在第 2 步「身份资料确认」 |
| `require_interaction` | 两个都有 | `0` | `1` = 前两步停下来等确认（最多等 12 s，不许把开机关死） |
| `brand1` / `brand2` / `brand3a` / `org_zh` / `org_en` / `welcome_box` / `footer` … | 两个都有 | 见各自 `theme.json` | 屏幕上那几行品牌字（迷你联盟 / MiniCode / 迎接最高智能降临 …），想换成自己项目的名字改这里 |

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

**机密接入**带的是另外 10 句播报（合计约 0.28 MB）＋同两声咔哒：默认读**中文女声**
`line-cn-1.mp3` … `line-cn-5.mp3`，`voice_lang=en` 时改读 `line-1.mp3` … `line-5.mp3`。
上游本来有 5 个音色（默认英文 + 中/日/俄/朝），这里只打包中英两套 —— 宿主设置页没有语种
下拉，多带三个语种只是多占 700 KB；要就在 `tools/port_secret.py` 的 `ASSETS` 里补上文件名
重新生成。中文那 5 句的 `TRIMS`（`'line-cn-1': [80, 1480]` 那几行）同样是逐 40 ms 窗量
RMS 得来的：素材头上有约 120 ms 静音、尾巴留着一小截空气，削掉以后整段约 17 s。
它的终幕 `line-6` / `line-cn-6` **不带**：原句是 "Welcome to DeepSeek Harness"（以及中文版），
把别人家的品牌名念进 Mini Code 不合适，所以终幕只有画面与合成钟。

终幕那句「欢迎 X 访问」里的 X 取宿主「配置 → 开机动画 → **身份名**」，没填就用主题
默认值（哈基米指挥官）。

两套主题都是脚本从上流仓库生成的，可复现，且**每一条改动都要能匹配上**（匹配不上直接
失败退出，不会生成半成品）：

```bash
git clone https://github.com/LeeRolling/dsh-startup-screen ../dsh
python tools/port_access.py --src ../dsh

git clone https://github.com/huzhengcai471-crypto/dsh-startup-secret ../dsh-secret
python tools/port_secret.py --src ../dsh-secret   # 上游 7 张内嵌图也会一起抽成扁平文件
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
tools/port_secret.py       从上流仓库移植「机密接入」(同样逐条补丁,顺带把内嵌图抽成扁平文件)
LICENSE-DSH                上游 dsh-startup-screen 的 MIT 原文(接入序列是它的衍生作品)
LICENSE-DSH-SECRET         上游 dsh-startup-secret 的 MIT 原文(机密接入是它的衍生作品)
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
- **机密接入** `mc-secret` 是 [dsh-startup-secret](https://github.com/huzhengcai471-crypto/dsh-startup-secret)
  v1.4.2 的移植（MIT，© 2026 该二创作者；它本身又是 dsh-startup-screen 的二次创作，
  上游 MIT 原文见 [LICENSE-DSH-SECRET](LICENSE-DSH-SECRET)）。和「接入序列」最不一样的地方是
  **画面素材一律照上游原样保留**：红色徽标 PNG、5 张人物立绘 webp、事件窗口插画，都是从上游
  内嵌的 7 个 data URI 里 base64 解码出来的同一批字节，只是改成了主题目录里的扁平文件（宿主
  CSP 允许 `img-src 'self'`，画面一个像素没重画）。改的只有：屏幕上的品牌文字（上游有三处写死
  了别家的名字）、宿主协议对接、`<audio>` 取素材、去掉浏览器合成音兜底、播报默认语种换成中文女声。
  **这些素材的授权要单独判断**：人物线稿画的是真实的人、徽标是政治标识、女声是别人的录音，
  MIT 授权覆盖的是代码而不是它们。自用/学习没问题；要把这个仓库再公开分发或商用，先确认这部分
  授权，或者干脆别装这个主题（设置页换回「接入序列」即可）。不想看到立绘也可以
  `mascot=none`，那样连图片请求都不会发。
- 主题里 **handoff 的时机**（在淡出**开始**那一帧就通知宿主叠化，否则交界处会闪一下）这个手法借鉴自 dsh-startup-screen 与
  [dsh-chat-wallpaper](https://github.com/LeeRolling/dsh-chat-wallpaper)（都是 MIT，© LeeRolling，给 DeepSeek Harness 写的插件）。
- **音频素材的版权**：那 6 句女声播报是上游从一段 DeepSeek 宣传视频里抠出来的，
  MIT 授权覆盖的是代码，**不覆盖这段音频**。自用无妨；要把本仓库再公开分发、
  或者商用，请先确认这段音频的授权，或用同名文件换成你自己有权限的素材。

## 许可

代码与画面实现：MIT — 见 [LICENSE](LICENSE)（接入序列的衍生作品部分另见
[LICENSE-DSH](LICENSE-DSH)，机密接入的衍生作品部分另见
[LICENSE-DSH-SECRET](LICENSE-DSH-SECRET)）。音频素材与图片素材（人物线稿、徽标、事件插画）
的版权都不属于本仓库的 MIT 授权，见上一节。
主题里请自己在 `theme.json` 的 `license` 字段署上作者。
