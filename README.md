# mini_code 插件仓库

给 [mini_code](https://github.com/zhoujiannan-nb/mini_code) 用的公开插件仓库。

现在这里有三类插件：

- **外观插件**（`kind: appearance`，在 `boot-anim/`）——目前带的唯一能力是**开机动画**：
  一个 `plugin.json` 里写了 `boot` 块，宿主就把它当开机动画用。以后的外观主题（聊天底图、
  大字横幅、配色方案……）就再多加一个块，目录约定不变。
- **工具插件**（`kind: tool`，在 `tool/`）——往模型的工具列表**追加**工具，像网页搜索那样。
  真源是 `plugin.json` 里的 `tools[]`，参数走 **stdin**（不是命令行），实现在同目录的脚本里。
  见 [`tool/web-search/`](tool/web-search/)。
- **进程插件**（`kind: process`，在 `process/`）——宿主负责把它的本地服务拉起、探活、重启、
  关门，典型用途是给本机起一个 OpenAI 兼容的模型端点（见
  [`process/qoder-gateway/`](process/qoder-gateway/)）。**这一类不往 prompt 里塞任何文本**，
  所以对前缀缓存完全隐形；二进制随插件一起发（载荷形式），拉下来不用编译。

这三类的**目录写法不一样**，这是有意为之：`boot-anim/<id>/` 的真源是 `theme.json`
（`plugin.json` 由它派生，别手改）；`tool/<id>/` 与 `process/<id>/` 的真源就是 `plugin.json` 本身。

装、选、换、删**全在 mini_code 的「配置 → 插件中心」里**：左边的列表是本地已装的，右边是
仓库里的市场（进入页签自动拉一次）。装完之后点那一行的「**设为开机动画**」就生效，想先看看
就点「预览」。宿主直接读本仓库根目录的 [`index.json`](index.json)，不用手工拷文件。

`boot-anim/` 里每个主题目录同时留了 `theme.json`：它是**动画自己的书写格式**（人读着舒服、
`tools/make_index.py` 认它），`tools/make_plugins.py` 从它派生出宿主认的 `plugin.json`。
两个文件都进版本库，但这一类里**唯一的真源是 `theme.json`**。（`tool/` 那类没有 `theme.json`，
`plugin.json` 就是真源。）

## 现有主题

| 主题 | 时长 | 一句话 |
|---|---|---|
| [接入序列](boot-anim/mc-access/) `mc-access` | 17.8s | 复刻 dsh-startup-screen 的电影感序列：黑幕芯片标识 → 过曝洗白 → 五步接入（**真声女声播报** + 底噪 + 咔哒音效）→ 色散故障揭幕。品牌已是 Mini Code，终幕只念一声 `Welcome` |
| [机密接入](boot-anim/mc-secret/) `mc-secret` | 17.0s | 更硬的那一款：**默认中文女声**（`line-cn-1..5`）一屏一句报读，红色徽标、右下角人物立绘、结尾「降世」事件卡都按上游素材原样保留。`voice_lang=en` 换英文，`mascot=none` 收掉立绘，`event_window=1` 才在结尾弹事件卡（默认不弹） |

两个都是 `kind: appearance` 的插件，`plugin.json` 里带 `boot` 块（入口 / 预览图 / 时长上限）。

### 现有工具插件

| 插件 | 给模型追加什么 | 一句话 |
|---|---|---|
| [网页搜索 / 正文读取](tool/web-search/) `web-search` | `web_search` / `web_read` / `web_search_multi` | 真实（无头）浏览器搜 bing/baidu/google/duckduckgo/zhihu，正文抽成 markdown。**要本机自备 `web_search` 项目 + playwright + chromium**，缺依赖时工具会返回一段写清楚去哪儿装的错误 |

### 现有进程插件

| 插件 | 平台 | 给你什么 | 一句话 |
|---|---|---|---|
| [Qoder 网关](process/qoder-gateway/) `qoder-gateway` | Windows | `http://127.0.0.1:32999/v1`（OpenAI 兼容） | 把自己买的 Qoder 套餐变成本地 OpenAI 兼容 API：标准字段、原生 `tool_calls`、`reasoning_content`、真实 `cached_tokens` 前缀缓存命中。**二进制随插件发**（`qoder-gw.bin.json`：stripped exe → zlib → base64，3.8MB；宿主安装器不收 `.exe` 且单文件限 8MB），首次运行自动解到 `%LOCALAPPDATA%\Programs\QoderAPI\QoderAPI.exe` 并校验 sha256，**拉下来就能用、不用 Go 不用编译**。PAT 放 `~/.qoder-api/pat.txt`，客户端 key 放 `~/.qoder-api/key.txt`（没有就随机生成），凭据绝不进仓库 |
| [Qoder 网关（苹果版）](process/qoder-gateway-macos/) `qoder-gateway-macos` | macOS（arm64 + Intel） | 同上，同一个端口同一套凭据约定 | 同一份 Go 源码交叉编译成 Mach-O。**两个架构各一个载荷**（`qoder-gw-macos-arm64.bin.json` 3.53MB / `qoder-gw-macos-amd64.bin.json` 3.79MB），首次运行按本机 CPU 选对架构、解到 `~/Library/Application Support/QoderAPI/QoderAPI`、校验 sha256 + Mach-O 架构 + 代码签名、`chmod 755`。Apple Silicon 上 arm64 没有 `LC_CODE_SIGNATURE` 会被内核 `killed: 9`，所以发布的产物带 ad-hoc 签名，启动器还会在异常退出时 `codesign --force -s -` 补一次。入口是 `sh run.sh`（先找 Python 3.8+，缺了就叫你 `xcode-select --install`）；装完可以 `sh run.sh --selftest` 自查 |

进程插件的启停在**「配置 → 插件中心」**里（开始 / 停止 / 重启 / 看日志），装了 `autostart`
就跟着 mini_code 一起起来；反过来 mini_code 没跑，那个端口也不会有人听。两个 Qoder 网关
**同端口**，所以一台机器上只装其中之一（装错了也没关系：另一个会认出端口上是同一个网关，
转成看守而不是抢端口）。它们都**只监听 127.0.0.1**。

### 装、选、开

全在**「配置 → 插件中心」**，两条路：

- **市场页签**：进去会自动拉一次 `index.json`，找到想要的动画 → 右边详情 → **安装**；
- **已装页签**：装完就在这里。点一行选中，右边详情里 **设为开机动画**（这一下会同时把
  `boot_anim.enabled` 打开 —— 点了它显然是想看见它）；`预览` 直接播一遍，不用等下次启动。

**外观页**只留了一个状态摘要（“已启用 · 当前：接入序列 · 已装 2 个”）和一条
`去插件中心选 / 装动画 →` 的跳转；动画的**选择**不再是一张重复的表单。

嫌长就把「外观 → 开机动画 → 速度」调快（宿主的 `speed` 会一起压缩画面节奏），
不想听声音就勾「静默」——勾上后主题连音频文件都不会去下载。
`启用` 关掉、或者把动画插件在插件中心停用，效果一样：都不会播。

### 主题自己的开关（`theme.json` 的 `options`）

宿主的设置页只给 **启用 / 播放时机 / 速度 / 静默** 四个开关（身份名与片尾可交互两个控件
已经删了 —— 它们只对个别主题有意义，现在是主题自己在 `options` 里声明）。剩下的开关由主题
在 `theme.json` 里声明、以 query 传进 iframe。要改就改装到本地的那一份
`~/.mini_code/plugins/<id>/theme.json`（改完重启 mini_code）：

| 键 | 主题 | 默认 | 说明 |
|---|---|---|---|
| `voice_lang` | 机密接入 | `cn` | `cn` = 中文女声 `line-cn-1..5`，`en` = 英文 `line-1..5` |
| `mascot` | 机密接入 | `"0"` | 右下角人物立绘 `0`…`4`；`none` 整块不渲染（连图片请求都不发） |
| `event_window` | 机密接入 | `"0"` | `1` = 演完再弹一页「降世」事件卡，Enter/点击放行，8 s 无操作自己走 |
| `access_password` | 机密接入 | 空 | 访问密码；只在 `require_interaction=1` 时生效，拦在第 2 步「身份资料确认」 |
| `require_interaction` | 两个都有 | `0` | `1` = 前两步停下来等确认（最多等 12 s，不许把开机关死） |
| `brand1` / `brand2` / `brand3a` / `org_zh` / `org_en` / `welcome_box` / `footer` … | 两个都有 | 见各自 `theme.json` | 屏幕上那几行品牌字（迷你联盟 / MiniCode / 迎接最高智能降临 …），想换成自己项目的名字改这里 |

`theme.json` 顶上那几个（`entry` / `durationMs` / `maxMs` / `interactive` / `minViewport`）
`plugin.json` 的 `boot` 块里都有；宿主**先看 `plugin.json`，缺的字段才回落到 `theme.json`**，
所以老版本插件（只有 `theme.json`）照样能播。

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

看 [docs/theme-contract.md](docs/theme-contract.md)。四步：

1. `boot-anim/<你的 id>/` 里放 `theme.json` + `index.html`（+ `preview.svg`）；
2. `python tools/make_plugins.py` —— 校验 `theme.json`，派生 `plugin.json`，并重建 `index.json`；
3. `python tools/make_index.py --check` 自查一遍（sha256 对不对得上）；
4. 提 PR。

纯前端、无构建步骤、无依赖 —— 会写 HTML/CSS 就能写主题。

`theme.json` 是**唯一真源**，`plugin.json` 由它派生，别手改后者（下次生成会被覆盖）。

改完主题**一定要重跑 `make_plugins.py`**，否则 `index.json` 里的 sha256 与文件对不上，
用户点安装会报校验失败。

### 两个清单各管什么

| 文件 | 谁读 | 管什么 |
|---|---|---|
| `theme.json` | 仓库工具、宿主兜底 | 动画自己的完整清单：入口、时长、`options`（品牌文案 / 语音语种 / 立绘） |
| `plugin.json` | 宿主（`plugin` 包） | 声明"这是个插件" + `kind` + `boot` 块（入口 / 预览图 / 时长上限 / 标签），也就是插件中心那张卡上的字 |

宿主加载时**先看 `plugin.json`、缺的字段回落到 `theme.json`**，所以：

- 只放 `theme.json`（老式主题）= 还能播，但**在插件中心里不是一张卡**（没有 `plugin.json` 就不算插件）；
- 两个都放 = 插件中心里能装能选，主题自己的 `options` 照旧生效。

### `index.json` 里的桶

`kinds.appearance` 是插件中心读的那一份；`kinds.boot-anim` 是给只认这个桶的老宿主留的
**兼容别名**，两桶内容一样（别名桶少一个 `category` 字段）。已经踩过的坑：市场把各桶合并
成一张列表，同一段动画因此并排列了两张卡，点哪张装出来的都是同一个目录。宿主现在**按 id
去重**（桶名有序，`appearance` 排在前面先命中）；仓库这边也不该把同一个 id 挂到别的桶里
去"多露一次脸"。

`tool` / `process` / `skin` / `wallpaper` 这些桶是**其余各类**，条目由
`tools/make_plugins.py` 从各自的 `plugin.json` 扫出来（空的桶不写，省得市场里出现
"点进去什么都没有"的分组）。**别把同一个 id 也挂进 `boot-anim`** —— 那对别名只是给老宿主留的。

### 插件目录里能放哪些文件（宿主的下载白名单）

安装器逐个文件下下来之前会先验：路径必须在插件目录内、扩展名必须在白名单里、单文件 ≤8MB、
总数 ≤40 个、合计 ≤24MB。白名单（`web/plugins_catalogue.go` 的 `catalogueDownloadExtTypes`）：

```
.css .svg .png .jpg .jpeg .webp .gif .woff .woff2 .ttf .otf .html .htm
+  .js .mjs .json .md .py .sh .mp3 .ogg .wav .ico
```

不在表里的文件**装的时候会被直接拒**（`不允许的插件文件类型`）。所以
`tools/make_plugins.py` 在生成索引时就按同一张表查一遍，把失败提前到提交阶段，
而不是等用户点安装。插件目录还必须**扁平**（不许子目录）。

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

终幕那句「欢迎 X 访问」里的 X 取主题 `options.identity`（默认 `哈基米指挥官`）—— 宿主设置页
原先有个「身份名」输入框，现在删了（它只对这类主题有意义），要改就改插件目录里的
`theme.json`。

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
index.json                 机器读清单(tools/make_plugins.py 生成,别手改)
                             kinds.appearance = 插件中心读的那一份
                             kinds.boot-anim  = 老宿主的兼容别名(内容一样,少个 category)
                                ⚠ 同一个 id 会同时出现在两个桶里。新宿主按 id 去重,
                                  只列一张卡;别在别的桶里重挂同一个 id 来"多露一次脸"
                             kinds.tool / kinds.process = 另外两类(各自独立成桶,不会重复)
boot-anim/<id>/            外观插件(目前这一类只含开机动画)
  plugin.json                宿主认的清单:kind=appearance + boot 块(派生文件,别手改)
  theme.json                 动画自己的清单:入口/时长/options(真源)
  index.html / boot.js / boot.css / preview.svg / *.mp3 / *.webp …
tool/<id>/                 工具插件(第二类)：**plugin.json 就是真源**，没有 theme.json
  plugin.json                kind=tool + tools[]（name/description/parameters/command/args/timeout_seconds）
  adapter.py / config.json   工具的实现与它的配置（参数从 **stdin** 进来，不是命令行）
process/<id>/              进程插件(第三类)：**plugin.json 就是真源**，宿主托管一个本地子进程
  plugin.json                kind=process + process{command/args/autostart/restart/ready_timeout_seconds/health_check/expose}
  gateway.py                 启动器（也可换成任何能读 MINICODE_PLUGIN_DIR 的脚本）
  *.bin.json                 二进制载荷（宿主不收 .exe；常见做法 strip → zlib → base64，运行期校验 sha256 再解出）
preview/                   宿主模拟器(本地预览用)
docs/theme-contract.md     契约 v1
tools/make_plugins.py      校验 theme.json → 生成 plugin.json + index.json(**主要用这个**)
tools/make_index.py        只重建 index.json(绕过 plugin.json 的老路子;--check 自查用)
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
  授权，或者干脆别装这个主题（插件中心里停用/卸载它即可）。不想看到立绘也可以
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
