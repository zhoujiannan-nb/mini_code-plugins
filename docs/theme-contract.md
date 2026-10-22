# 主题契约 v1（boot-anim）

一个主题 = `boot-anim/<id>/` 目录里的三个东西：

```
boot-anim/mc-tech-archive/
├── theme.json      必需：清单（宿主只读它，不猜目录结构）
├── index.html      必需：入口，自包含（可以另放 .css/.js/图片，用相对路径）
└── preview.svg     建议：卡片缩略图（320×180，SVG 或 PNG）
```

宿主（mini_code）把它当成**不可信第三方页面**处理：

```html
<iframe sandbox="allow-scripts" src="/boot-anim/&lt;id&gt;/index.html?speed=1&name=..."></iframe>
```

- `sandbox="allow-scripts"` **没有** `allow-same-origin` → 主题拿不到宿主的 localStorage / DOM / cookie；
- `/boot-anim/*` 响应头带 `Content-Security-Policy: connect-src 'none'; default-src 'self' data: blob:` →
  主题**连不上任何接口**（包括宿主自己的 `/api/*`），也连不了外网；
- 想放音乐/字体请**放文件进主题目录**用相对路径引，不要 `fetch` 外部地址（CSP 会拦）。

## theme.json 字段

| 字段 | 必需 | 说明 |
|---|---|---|
| `id` | ✅ | 与目录名**必须一致**，小写字母数字和 `-` |
| `name` / `nameEn` | ✅ / | 显示名 |
| `version` | ✅ | `x.y.z`，宿主按它判断"有没有新版可下载" |
| `entry` | ✅ | 入口文件，**只能是目录内相对路径**（`..`、`/`、`\` 一律拒绝） |
| `preview` | | 缩略图相对路径 |
| `description` | | 一句话说明，列表里显示 |
| `durationMs` | ✅ | 正常播完大概多久（500–60000），设置页拿来显示 |
| `maxMs` | ✅ | **硬超时**：到点宿主无条件把画面收走，绝不让人被关在黑屏里 |
| `colors` | | `["dark"]` / `["dark","light"]`，只做了深色就别声明支持浅色 |
| `interactive` | | `true` 表示需要用户点击推进（宿主此时不计时打断） |
| `minViewport` | | 窗口宽度小于这个值就不播（手机/窄窗别挡路） |
| `tags` | | 列表里的标签 |
| `options` | | 默认参数，宿主以 **query string** 传进入口 |

宿主会拼这些 query（主题自行读取、自行兜默认值）：
`speed`（0.35–3）、`name`（用户身份名，可空）、`interactive`（0/1）、`accent`（主题色）。

## 与宿主的通讯（只有一个通道）

```js
parent.postMessage({ mc: "boot-anim", type: "...", id: "<主题 id>", ... }, "*");
```

| `type` | 什么时候发 | 宿主做什么 |
|---|---|---|
| `ready` | 脚本一开始 | 记录 `{durationMs, maxMs, steps}`，遮罩正式计入 |
| `step` | 进入第 n 段 | 显示进度点/日志（可选） |
| `handoff` | **淡出开始的那一瞬间** | 开始交叉叠化，把下面的界面露出来 |
| `done` | 演完/跳过 | 移除 iframe，解锁页面 |

**`handoff` 是这里唯一的坑，也是借鉴来的最重要一条**：如果你的收尾是淡出，一定要在
`opacity` 开始变小的**那一帧**发 `handoff`，不是等淡到 0 再发。等淡完再发，中间会有一帧
两层都不够实，用户看到的就是"闪一下"。收到 `handoff` 后仍然要发 `done`（宿主以 `done`
为准移除节点）。

主题**必须自己兜底**：任何异常都要在 `maxMs` 之内发一次 `done`
（本仓库两个示例都在末尾放了 `setTimeout(finish, maxMs)`）。宿主也有同名的硬超时，
但别指望它当你的计时器。

## 写主题的规则

1. **必须能自己结束**：`done` 一定要发；异常路径也要发。
2. **必须能被打断**：`Esc` / 点击跳过按钮 → 立刻 `done {by:"skip"}`。
3. **`prefers-reduced-motion`**：系统要求减少动效时快进（示例是速度 ×3，仍然走完）。
4. 别读写宿主的东西：拿不到，也不该拿。
5. 时长：2–10 秒是礼貌区间。超过 15 秒请做成 `interactive` 或给足跳过按钮。
6. 尺寸自适应：用 `vw/vh/%`，别假设 1920×1080；窗口可能只有 900×600。
7. 别放自动播放的音频：浏览器要求先有用户手势，硬放只会被 console 报错。
8. 深色优先：mini_code 默认深色；做浅色适配就把 `colors` 写全。

## 加一个主题

```bash
mkdir boot-anim/my-thing
# 放 theme.json / index.html / preview.svg
python tools/make_index.py      # 校验字段并重新生成 index.json
python -m http.server 8700      # 另开一个终端
# 打开 http://127.0.0.1:8700/preview/  实时看效果(和真宿主同规则)
```

`tools/make_index.py` 会挡住这些常见错：`id` 与目录名不一致、version 不是 `x.y.z`、
entry 不存在或越界、`maxMs < durationMs`、preview 缺失。**不要手改 `index.json`。**

## 宿主侧行为（供参考，改动请同步这里的文档）

- 默认装到 `~/.mini_code/boot-anim/<id>/`，目录可在「配置 → 开机动画」里改；
- 播放时机：页面首帧之前就用内联遮罩盖住（避免白闪），主题在遮罩里的 iframe 中跑；
- 播放策略：`每次会话`（sessionStorage 记一次）/ `总是` / `每天`（localStorage 记日期）/ `关闭`；
- 硬超时 `maxMs` 无条件收走画面；主题脚本报错、资源 404 也走同一条兜底；
- 只在 `window.innerWidth >= minViewport` 时播放。
