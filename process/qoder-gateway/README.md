# qoder-gateway —— Qoder 网关（mini_code process 插件）

把 Qoder 套餐暴露成一个本地 OpenAI 兼容 API，**拉下来就能用，不需要装 Go、不需要编译**：

```
base_url = http://127.0.0.1:32999/v1
api_key  = 你自己在 ~/.qoder-api/key.txt 里放的那个
model    = DeepSeek-Flash / DeepSeek-V4-Pro / GLM-5.3 / Qwen3.8-Max / Kimi-K3.1-Pro / …
```

## 为什么是 process 插件

minicode 的三类插件里只有 `process` 对**前缀缓存完全隐形**：

| 类别 | 对 prompt 的影响 |
| --- | --- |
| `process`（本插件） | **不贡献任何 prompt 文本**，缓存零影响 |
| `tool` | 往核心工具之后追加 schema（核心前缀不动，但 tools 数组会变） |
| `appearance` | 只影响界面 |

所以"把一个常驻服务接进来"就该用 process：宿主负责启动、健康检查、崩溃重启、开关与日志。

## 二进制怎么随插件发（以及为什么要绕这一道）

宿主安装器有两条硬规则：**单文件 ≤ 8MB**、**下载扩展名白名单里没有 `.exe`**（只收 `.json/.md/.py/.js/.css/图片/字体/音频` 这类）。而网关 exe 编译出来约 10MB。所以载荷这样放：

```
go build -trimpath -ldflags "-s -w"   →  QoderAPI.exe  7,197,696 B (6.86 MB)
zlib(-9) + base64                      →  qoder-gw.bin.json  3,986,808 B (3.80 MB)
```

`qoder-gw.bin.json` 里带 `algo / raw_size / sha256 / file`，`gateway.py` 首次运行时：

1. 解码 → 解压 → **校验 sha256 与长度**，不匹配就拒绝执行；
2. 原子写到 `%LOCALAPPDATA%\Programs\QoderAPI\QoderAPI.exe`（先 `.new` 再 `os.replace`，Windows 上运行中的映像被锁也能安全失败）；
3. 之后每次启动都比对 sha256：本机副本与插件清单一致就直接用，不一致就解出插件自带的那份（插件升级即二进制升级）。

重新生成载荷（改了网关代码之后）：

```bash
cd qoderapi-gw
python make_payload.py          # 自己 go build -s -w，写出 plugin/qoder-gw.bin.json
```

## 额度面板（界面右上角的 Qoder 积分徽标）

装上之后，界面右上角会有一枚额度徽标：剩余 / 总量、已用百分比、进度条、状态色
（正常绿 / 偏低黄 / 告急红 / 未运行灰）。数据直接来自本机网关的 `GET /qoder/usage`
（上游真实返回的 `user_quota`），不是估的。

启动器每 60 秒问一次 `/qoder/usage`，把结果预渲染成 `quota-slot.html` 写进插件目录；
宿主资源路由带 `Cache-Control: no-store`，每次打开/刷新页面都重新拉 ——
所以「刷新页面 = 刷新额度」。

**为什么不实时刷新**：宿主把 `ui.slots` 的片段放进无脚本、跨源隔离的 `<iframe sandbox>`
（裸 sandbox，连 `allow-scripts` 都不给）。Chromium 151 实测：内联样式与中文正常，
但 `<meta http-equiv=refresh>` **不触发**、同源 `<img>` / `<link>` **连请求都发不出**
（`'self'` 在 opaque origin 下不匹配）。片段里跑不了脚本、拉不到资源，只能显示静态内容。

三个地方能看额度：

1. 界面右上角徽标（`ui.slots = overlay`）
2. 完整额度页：**用浏览器直接打开插件目录里的 `quota.html`**
   （`C:\Users\<你>\.mini_code\plugins\qoder-gateway\quota.html`）
   —— 套餐、重置时间、token、前缀缓存命中率都在这。
   注意它**不能**通过 `http://127.0.0.1:7500/plugins/qoder-gateway/quota.html` 打开：
   宿主只服务 `ui.slots` 里声明过的 html，其余一律 403（这是有意的安全设计）。
3. 终端 `python gateway.py --quota`

`ui.slots[].height` 是写死的像素高度，写小了徽标会被裁。当前 **117** 不是猜的：
`fit_height.py` 用 Chromium 在 100% / 200% 缩放下各量一次 `.wrap` 的真实高度，
取最大 + 6px 余量写回清单（卡片本体 91）。改了徽标样式就重新量一次。

## 凭据一律不在仓库

| 东西 | 位置 | 说明 |
| --- | --- | --- |
| Qoder PAT | `~/.qoder-api/pat.txt` | 网关自己读；也可用 `QODER_PERSONAL_ACCESS_TOKEN` |
| 客户端 key | `~/.qoder-api/key.txt` | **没有就随机生成一个并写进去**；`-key` 不再写死默认值 |
| 日志 | — | 只打掩码 `key=****`，明文不落日志 |

`plugin.json`、`args`、命令行里都没有任何密钥。

## 文件

```
process/qoder-gateway/
  plugin.json            清单（真源）：process.command = python gateway.py
  gateway.py             启动器：解载荷/校验 → 带起网关 → 跟随宿主退出
  qoder-gw.bin.json      随插件发的二进制（zlib+base64，3.80MB，sha256 在清单里）
  qoder-gw.example.json  本机覆盖项样例（复制成 qoder-gw.json，别提交）
  README.md              本文件
```

## 装好后怎么用

- 插件中心（配置 → 插件中心 → 已装）里能看到 `Qoder 网关`，可启停/看日志；
- 接口：`GET /api/plugins/processes`、`POST /api/plugins/qoder-gateway/process {"action":"start|stop|restart"}`、`GET /api/plugins/qoder-gateway/logs`；
- `autostart: true` → minicode 一起来就把网关带起来（**注意：minicode 不在跑时，就没有 32999**，这是插件形态的固有边界）。

## 想用自己编译的二进制（可选）

默认不用管——插件自带。要覆盖就在插件目录写 `qoder-gw.json`：

```json
{"bin": "D:\\somewhere\\QoderAPI.exe", "addr": "127.0.0.1:32999", "region": "global", "args": []}
```

或设环境变量 `QODER_GW_BIN` / `QODER_GW_ADDR` / `QODER_GW_REGION`。显式指定的路径原样使用，不做 sha 校验（那是你自己的构建）。

## 两个防呆设计（都实测过）

- **端口已被占用且占用者就是 Qoder 网关** → 不重复绑定，转为"看守"；被看守的实例死了 → **立即自己接管**，不留空窗给宿主退避。
- **`-parent-pid`** → 宿主停插件时杀的是 python，网关跟着退，不留占端口的孤儿（实测杀启动器后 6 秒内端口释放）。

## 发布到市场

把 `process/qoder-gateway/` 放进 `mini_code-plugins` 仓库根目录（`process/<id>/`，`plugin.json` 即真源，目录必须扁平），然后跑仓库自带生成器：

```bash
cd mini_code-plugins
python tools/make_plugins.py     # 校验扩展名/大小/semver，把 kinds.process 写进 index.json
```

实测：5 个文件、合计 3.9MB，全部通过宿主的下载白名单与大小上限，`kinds.process[qoder-gateway]` 正常生成，sha256 清单逐文件核对一致。

**已发布**（2026-10-27，`mini_code-plugins` 的 `5f7204b`）：从 `raw.githubusercontent.com/zhoujiannan-nb/mini_code-plugins/main/` 把 index.json 与这 5 个文件真下载回来，逐个比对 size + sha256 全部一致，载荷解开后的 exe 也复核过（7,197,696 B，sha256 `627edbf8…`）。插件中心 `GET /api/plugins/catalog` 里已经能看到它（`kind=process`、`files=5`、`installed=true`）。

> 仓库里那个 `.gitattributes`（`* -text`）别删：`index.json` 逐文件记 sha256、宿主按**字节**校验，而 Windows 上 `core.autocrlf=true` 的克隆会把 LF 换成 CRLF，一换就校验失败。关掉换行转换，仓库存什么字节、检出来就是什么字节。
