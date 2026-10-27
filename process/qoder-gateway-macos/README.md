# Qoder 网关（苹果版）· qoder-gateway-macos

把 Qoder 套餐暴露成一个**本地 OpenAI 兼容 API**，macOS 专用，**拉下来就能用**：

```
base_url = http://127.0.0.1:32999/v1
api_key  = 你自己在 ~/.qoder-api/key.txt 里放的那个（没有会自动生成）
model    = DeepSeek-Flash / DeepSeek-V4-Pro / GLM-5.3 / Qwen3.8-Max / Kimi-K3.1-Pro / …
```

和 Windows 版（`qoder-gateway`）是**同一份 Go 源码**，只是交叉编译成 Mach-O、启动器换了
平台相关的部分（安装位置、签名检查、Python 探测）。两边用同一个端口、同一套
`~/.qoder-api/` 凭据约定，所以配置和客户端代码可以互通。

## 为什么是 process 插件

minicode 的三类插件里只有 `process` 对**前缀缓存完全隐形**——它不往 prompt 里塞任何文本：

| 类别 | 对 prompt 的影响 |
| --- | --- |
| `process`（本插件） | **不贡献任何 prompt 文本**，缓存零影响 |
| `tool` | 往核心工具之后追加 schema（核心前缀不动，但 tools 数组会变） |
| `appearance` | 只影响界面 |

宿主负责启动、健康检查、崩溃重启、开关与日志；`autostart: true` 时跟着 mini_code 一起起。

## 二进制怎么随插件发

宿主安装器有两条硬规则：**单文件 ≤ 8MB**、**下载扩展名白名单里没有可执行文件**（只收
`.json/.md/.py/.sh/.css/图片/字体/音频` 这类）。所以两个架构各打一个载荷：

```
                                  Mach-O          zlib(-9)+base64
GOOS=darwin GOARCH=arm64   →  6.46 MB  →  qoder-gw-macos-arm64.bin.json  3.53 MB  （带 ad-hoc 签名）
GOOS=darwin GOARCH=amd64   →  6.85 MB  →  qoder-gw-macos-amd64.bin.json  3.79 MB
```

两个都放进来（合计 7.3MB，宿主上限 24MB），这样 Apple Silicon 和 Intel Mac 装同一个插件都行。

`gateway.py` 首次运行时：

1. 看本机架构（`platform.machine()`；如果你用的是 Rosetta 下的 python，还查一次
   `sysctl.proc_translated`）挑对应载荷；
2. 解码 → 解压 → **校验 sha256 与长度**，再读 Mach-O 头核对**架构**，三个都对上才落盘；
3. 原子写到 `~/Library/Application Support/QoderAPI/QoderAPI`，`chmod 755`，顺手清掉
   `com.apple.quarantine`（从浏览器拖过来的文件会被 Gatekeeper 拦）；
4. 之后每次启动都比对 sha256：本机副本与清单一致就直接用，不一致就解出插件自带的那份
   （插件升级即二进制升级）。

重新生成载荷（改了网关代码之后）：

```bash
cd qoderapi-gw
python make_payload_macos.py               # 两个架构都构建并写进 plugin/qoder-gateway-macos/
python make_payload_macos.py --arch arm64  # 只重打 Apple Silicon 那份
```

生成器会自己核对：产物确实是 **darwin** Mach-O、`cputype` 与目标架构一致、**arm64 必须带
`LC_CODE_SIGNATURE`**（缺了就拒绝发布），体积在宿主上限内。

## Apple Silicon 上那件容易踩的事

arm64 的 Mach-O 必须带代码签名，否则内核直接 `killed: 9`（连一行输出都没有，看着像
"程序根本没跑"）。Go 交叉编译默认会打 **ad-hoc 签名**，所以插件发出去的那份是签过的。
启动器另外做了两道保险：

* 解出后读 Mach-O 头，确认 `LC_CODE_SIGNATURE` 在；
* 万一子进程异常退出、而二进制又没有签名，就 `codesign --force --sign - <path>` 补一个
  ad-hoc 签名再重启一次。

（ad-hoc 签名不是开发者签名，没有 notarization，所以 macOS 会对它做**本地**验证——
自己编译自己跑完全够用；它不能拿去公证分发。）

## 凭据一律不在仓库

| 东西 | 位置 | 说明 |
| --- | --- | --- |
| Qoder PAT | `~/.qoder-api/pat.txt` | 网关自己读；也可用 `QODER_PERSONAL_ACCESS_TOKEN` |
| 客户端 key | `~/.qoder-api/key.txt` | **没有就随机生成一个并写进去** |
| 日志 | — | 只打掩码 `key=****`，明文不落日志 |

`plugin.json`、`args`、命令行里都没有任何密钥。macOS 上这两个文件的权限建议
`chmod 600 ~/.qoder-api/*.txt`。

## 文件

```
process/qoder-gateway-macos/
  plugin.json                      清单（真源）：process.command = sh run.sh
  run.sh                           入口：找 Python 3.8+，找不到就说清楚怎么装
  gateway.py                      启动器：选架构 → 解载荷/校验 → 带起网关 → 跟随宿主退出
  qoder-gw-macos-arm64.bin.json   Apple Silicon 的二进制（zlib+base64，3.53MB）
  qoder-gw-macos-amd64.bin.json   Intel Mac 的二进制（3.79MB）
  qoder-gw.example.json           本机覆盖项样例（复制成 qoder-gw.json，别提交）
  README.md                       本文件
```

为什么入口是 `sh run.sh` 而不是 `command: python3`：macOS 上的 `python3` 来自
**Xcode 命令行工具**，没装过的机器上这个命令根本不存在，插件中心只会显示
`exec: python3: not found`。包装一层之后，缺 Python 时日志里直接给
`xcode-select --install`（或 `brew install python@3.12`），装完在插件中心点重启即可。

## 装好后

- 插件中心（配置 → 插件中心 → 已装）里能看到「Qoder 网关（苹果版）」，可启停/看日志；
- 装完想先自己验一遍（不占端口、不碰宿主）：

  ```bash
  cd ~/.mini_code/plugins/qoder-gateway-macos
  sh run.sh --selftest
  ```

  它会：认出 macOS 版本与架构 → 解出载荷 → 核对 sha256/架构/签名 → 跑一次
  `QoderAPI -version` → 打印下一步（放 PAT、启动、去哪儿看 key）。
- 接口：`GET /api/plugins/processes`、
  `POST /api/plugins/qoder-gateway-macos/process {"action":"start|stop|restart"}`、
  `GET /api/plugins/qoder-gateway-macos/logs`；
- **mini_code 不在跑时就没有 32999**，这是插件形态的固有边界。

## 想用自己编译的二进制（可选）

默认不用管——插件自带。要覆盖就在插件目录写 `qoder-gw.json`：

```json
{"bin": "/usr/local/bin/QoderAPI", "addr": "127.0.0.1:32999", "region": "global", "args": []}
```

或设环境变量 `QODER_GW_BIN` / `QODER_GW_ADDR` / `QODER_GW_REGION`。显式指定的路径原样使用，
不做 sha 校验（那是你自己的构建）。自己编（在 mac 上，或任意机器交叉编译）：

```bash
GOOS=darwin GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o QoderAPI .
# Apple Silicon 上如果跑不起来、报 killed: 9，就补一个 ad-hoc 签名：
codesign --force --sign - QoderAPI
```

## 两个防呆设计

- **端口已被占用且占用者就是 Qoder 网关** → 不重复绑定，转为"看守"；被看守的实例死了 →
  **立即自己接管**，不留空窗给宿主退避。
- **`-parent-pid`** → 宿主停插件时杀的是启动器，网关跟着退，不留占端口的孤儿。
- **非 macOS 直接说清楚**：本插件在别的平台上启动会以退出码 4 退出，并提示 Windows 该装
  `qoder-gateway`、Linux 自己 `go build`。

## 已知边界

* 只有 **arm64/amd64** 两份；Universal binary 也能做，只是体积翻倍没必要。
* ad-hoc 签名的二进制**换台机器/重新解出**后 macOS 会重新验证一遍，属正常。
* 没有 GUI、没有 launchd 常驻：生命周期归 mini_code 的插件中心管。
* 出问题先看 `sh run.sh --selftest` 与插件日志；`GET /health` 能立刻分辨"进程活着但上游不认"
  还是"没起来"。
