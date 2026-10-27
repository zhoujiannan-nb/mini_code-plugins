# web-search — 工具插件（第二类 / `kind: "tool"`）

给模型追加三个工具，全部包装本机的 [web_search](https://github.com/) 项目（Playwright 真实浏览器）：

| 工具 | 干什么 | 默认 |
|---|---|---|
| `web_search` | 搜一个关键词，返回 JSON（position/title/link/snippet/source…） | engine=bing，max=10 |
| `web_read` | 打开一个 URL，抽正文成 markdown（去掉导航/广告/侧栏） | max_chars=8000 |
| `web_search_multi` | 一批关键词（≤8）共用一次浏览器会话 | max=5/词 |

装：插件中心 → 插件市场 → `网页搜索 / 正文读取` → 安装。装完就在「已安装」里，
manifest 不写 `enabled`（**缺省即启用**）—— 注意 manifest 里写 `"enabled": false` 是
**在界面上点不亮的**（状态文件只往"关"的集合里加，从不覆盖 manifest）。

## 外部依赖（**插件不会自己装，装完必须先备齐**）

工具插件跑的是宿主不认识的外部程序，缺依赖不会让插件消失，只会让**每次调用都报错**。

1. **`web_search` 项目本体**（`web_search/cli.py` 那套）。默认路径 `D:\project_ai\web_search`。
2. **Python 包**，要装在**跑 mini_code 的那个 python** 里（桌面端从资源管理器启动时用的是
   `PATH` 上第一个 `python`，不一定等于你终端里的那个）：
   ```bat
   pip install playwright pydantic trafilatura
   ```
3. **Chromium 内核**（Playwright 自带的内核，不是系统 Chrome，约 150 MB，**必须单独下一条**）：
   ```bat
   playwright install chromium
   ```
4. 可选：`playwright-stealth` / `ddddocr` —— 这三个工具都没用到，不装也行。

自检（要 `"ok": true` 且 `problems` 为空）：

```bat
python <web_search 项目目录>\ws.py doctor --json
```

### 换机器 / 路径不一样

改本插件目录里的 `config.json`：

```json
{ "web_search_home": "D:\\project_ai\\web_search" }
```

或者设环境变量 `MINICODE_WEB_SEARCH_HOME`（优先级更高）。三处都没对上时，工具会返回一段
写清楚"去哪儿改"的错误，而不是一个 traceback。

## 文件

```
tool/web-search/
├── plugin.json     宿主读的清单：kind=tool + tools[]（这个文件是真源，不是派生的）
├── adapter.py      三个工具的实现：stdin 收 JSON 参数 → stdout 出结果
├── config.json     web_search 项目的位置（装完之后用户自己改）
└── README.md
```

## 契约（改 `adapter.py` 前先看这段）

- **参数走 stdin，不走命令行**：宿主把模型的参数对象序列化成 JSON 写进子进程的 stdin，
  `command` / `args` 在 manifest 里是静态的（`["adapter.py","search"]`）→ 没有引号/注入问题。
- **工作目录 = 插件目录**，所以 `args` 里的相对路径就是本目录。
- **结果打 stdout**；超过 **32KB** 宿主截断。中日韩一个字 3 字节，所以 `max_chars` 上限夹到
  12000（默认 8000），别学 `ws.py` 自己的 20000 默认值 —— 那会一头撞上截断线。
- **失败 = 非零退出 + 原因写 stderr**（`die()`）。stdout 保持干净，别把日志混进去。
- 宿主给子进程注入 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` / `LANG` / `LC_ALL`，
  不然 Windows 中文版控制台继承 GBK，一打中文就 `UnicodeEncodeError`。
- 工具名匹配 `^[a-z][a-z0-9_]{1,63}$`，且**不能与内置工具重名**（`read_file` / `write_file` /
  `edit_file` / `exec` / `search_files` / `list_dir` / `glob` / `copy_file` / `move_file` /
  `delete_file` / `readimg` / `skills` / `task`…，重名会被宿主忽略并记警告）。
- `timeout_seconds` 缺省 60、上限 600；超时是"返回一条工具结果"，不是崩溃。

## 本地先跑通（不经过 mini_code，参数照样走 stdin）

```bat
cd /d <插件目录>            REM 装完之后是 %USERPROFILE%\.mini_code\plugins\web-search
echo {"query":"sglang mtp","max":5} | python adapter.py search
echo {"url":"https://example.com"} | python adapter.py read
echo {"queries":["sglang mtp","vllm spec decode"],"max":3} | python adapter.py multi
```

## 仓库侧：改完要重跑索引

`plugin.json` 是这个插件的真源（不像 `boot-anim/*` 那样由 `theme.json` 派生），
但 `index.json` 里的 sha256 是 `tools/make_plugins.py` 扫出来的：

```bat
python tools/make_plugins.py        REM 重新生成 index.json（含 tool 桶）
python tools/make_index.py --check  REM 自查：sha256 对不上 = 用户装不上
```

⚠️ 宿主的**下载白名单**决定一个插件目录里能出现哪些扩展名
（`.css .svg .png .jpg .jpeg .webp .gif .woff .woff2 .ttf .otf .html .htm`
+ `.js .mjs .json .md .mp3 .ogg .wav .ico`，见 `web/plugins_catalogue.go`）。
本插件带的 `adapter.py` 需要那份白名单里有 `.py`，否则安装会被拒（`不允许的插件文件类型`）。
