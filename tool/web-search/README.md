# web-search —— 网页搜索 / 正文读取（v2）

给 mini_code 的模型追加三个工具：`web_search`、`web_read`、`web_search_multi`。

**v2 最大的变化是默认不开浏览器了。** v1 每次搜索都要冷启动一次 Chromium，并且"只要有结果
就算成功"，在这台机器上实测 10 次查询只有 4 次能用（另外 6 次返回 58同城 / 腾讯体育 / B站直播
这类反爬引流页），中位 3.5s，最坏一次撞在 90s 超时上。v2 走纯 HTTP 引擎链 + 相关性闸门：

| 指标（10 条查询，走宿主同款调用） | v1 | v2 |
| --- | --- | --- |
| 可用率（有结果且没被闸门判废） | 4/10 | **10/10** |
| 中位耗时 | 3530ms | **1166ms** |
| 最差耗时 | 90114ms（超时） | 1490ms |
| 连续 12 次同查询 | 搜狗第 6 次后被限流 | 12/12 不衰减 |

浏览器并没有被扔掉：HTTP 链全挂时它才懒启动（cn.bing → google），`read` 也只有碰上
JS 渲染页 / 403 才开浏览器，知乎这类登录墙从 v1 的 75–90s 挂死变成 ~6s 明确报错。

## 装完就能用的东西

- **引擎链 + 相关性闸门**：`so360 → cn.bing → sogou → baidu → ddg`，某个引擎被限流或者
  返回一堆不沾边的东西（结果里含查询词的比例低于 `gate`）就自动换下一个。
- **跳转链还原**：360 的 `/link?m=`、搜狗的 `/web/link?url=`、google 的 `/goto?url=CAES…`
  （token 是加密的，只能跟着 302 走）都会还原成真链，`web_read` 才打得开。
- **代理自动探测**：环境变量 → Windows 系统代理（注册表）→ 常见本地端口
  （7897/7890/10809/1080）。在墙内直连不出海的环境里，这一步决定 google 通不通。
- **UA 轮换 + 引流页黑名单 + 引擎自己的小工具过滤**（实测英文查询会混进一条 `fanyi.so.com`）。
- **观测日志**：每次调用往 `~/.mini_code/logs/web-search.jsonl` 追加一行
  （cmd/query/ok/engine/rel/degraded/耗时/试过哪些引擎），超过 512KB 自动轮转。排查
  "上周还好的搜索怎么突然不行了" 就靠它。
- **`degraded` 显式标记**：只要相关性没过闸门、或被引流页顶掉、或一条都没有，返回里就是
  `degraded: true` + `warning` + `hint`，模型不会再把垃圾当答案抄走。
- **memory.md**：插件目录里的这份用法约束会随插件注入系统提示（plugin.json 里的
  `"memory": "memory.md"`）。v1 也有这个文件，但没在 manifest 里声明，所以从来没生效过。

## 依赖

纯 HTTP 路径只用标准库，装了就能跑。以下是**可选**加速带：

| 装了什么 | 换来什么 |
| --- | --- |
| `pip install trafilatura` | 正文抽取质量明显更好（`read` 首选后端），没装退化成正则剥标签 |
| `pip install playwright && playwright install chromium` | HTTP 链全挂时的浏览器兜底；`read` 的 JS 页兜底 |
| 外部 [web_search](../../README.md) 项目 | 只是给浏览器兜底多一套现成的 SERP 选择器；**v2 不依赖它**，删掉 config.json 里的 `web_search_home` 也照跑 |

## config.json（全部可省）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `chain` | `so360,bing-cn,sogou,baidu,ddg` | HTTP 引擎链，按顺序试 |
| `browser_chain` | `bing,google` | 浏览器兜底顺序（`bing` 给直链，`google` 多一次 HTTP 还原） |
| `gate` | `0.5` | 相关性闸门：结果里含查询词的最低比例，低于它就换引擎 |
| `mode` | `auto` | `auto` 链+兜底 / `fast` 只用 HTTP / `browser` 直接上浏览器 |
| `proxy` | `auto` | `auto` 自动探测 / `off` 强制直连 / 写死 `http://127.0.0.1:7890` |
| `deadline_s` | `25` | 整条链的时间预算 |
| `max_results` | `10` | 默认返回条数 |
| `searxng_url` | `` | 自建 SearXNG 端点（填了就走它的 JSON API 并插到链首，`&format=json`） |
| `log` | `true` | 是否写观测日志 |
| `web_search_home` | — | 可选，见上表 |

环境变量 `MINICODE_WEB_SEARCH_CHAIN/GATE/MODE/PROXY/SEARXNG_URL/...` 可以临时压过配置。
单次调用的参数（`chain`/`gate`/`mode`/`proxy`/`deadline_s`/`domain`/`engine`）优先级最高，
具体写在 `plugin.json` 的 parameters 里，模型看得见。

## 排障

```cmd
cd %HOME%\.mini_code\plugins\web-search
python -X utf8 adapter.py doctor          :: 环境、代理、逐个引擎（加 {"browser":true} 连浏览器一起测）
python -X utf8 bench.py                   :: 10 条查询的回归：可用率 / P50 / P95
python -X utf8 bench.py --durability 12   :: 同一条查询连打 12 次，看谁先被限流
python -X utf8 fastpath.py search "..." --json   :: 跳过 adapter 直接压引擎层
```

已知情况，不算 bug：

- **搜索引擎按 IP 限流**。这台的出口是数据中心 IP（实测被百度/搜狗标记），所以链里任何一个
  引擎都可能某天变成 0 条 —— 表现是 `degraded: true` + `warning` 里写清哪个引擎交白卷，
  换 `chain` 或用 `--gap_ms` 放慢即可。so360 是这台机器上最抗造的通道。
- **`engine=google` 一定会开浏览器**（google 的纯 HTTP 端点在这台机器上拿不到结果），
  慢 2–3s；链接要靠一次 HTTP 还原，偶尔还原失败会留原链。
- **搜狗给的是 `/web/link?url=` 跳转链**，本插件会尽量还原；还原失败时那条链仍然能用
  `web_read` 打开（浏览器会跟着 JS 跳），但直接 copy 出来不好看。
- **知乎正文要登录**（`read` 会给你 45 字 + WARNING），**zhihu 作为搜索引擎已下线**
  （无头浏览器 12 次全 0 条）；想看知乎用 `domain=zhihu.com`。
- **`read` 对 404/410 直接失败**（不再白等 4 秒开浏览器），错误里会带上读到的那几个字。

## 文件

| 文件 | 作用 |
| --- | --- |
| `plugin.json` | manifest（真源就在这个目录，`tools/make_plugins.py` 不会改它，但会重算 `index.json` 的 sha256） |
| `adapter.py` | 宿主的 stdin/stdout 契约 + 参数解析 + 输出整形 + 观测日志，子命令 `search/read/multi/doctor` |
| `fastpath.py` | 引擎层：HTTP 引擎、闸门、跳转链还原、浏览器兜底、正文抽取。可独立跑 |
| `memory.md` | 注入系统提示的用法约束（改这里要记得 `degraded` 语义要对上） |
| `bench.py` | 回归基准，改完引擎层跑一下 |
| `config.json` | 默认配置，全部可省 |
