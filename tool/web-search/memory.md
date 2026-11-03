# web-search 用法约束（插件加载后追加到系统提示）

- 只要答案依赖**当下事实**（版本、发布日期、价格、新闻、API 文档），就用 `web_search`，
  别凭记忆答；模型记忆里版本号往往已经过期。
- **默认什么都不用传**：引擎链（360 → 必应 → 搜狗 → 百度 → DuckDuckGo）会自动回退，
  一次 0.3–1.5s。不要写死 `engine`，除非你确实只要某个引擎。
- 返回里 `degraded=true`、或 `relevance` < 0.5、或有 `warning`：**这批结果不可信**
  （多半是反爬引流页 / 索引抽风）。必须换关键词或换 `chain`/`engine` 重搜一次再下结论，
  禁止直接引用这批标题作答。
- 结论要落在**打开过的链接**上：挑一条最相关的用 `web_read` 读完再回答，snippet 不够。
- 中文内容优先 360/搜狗（`chain=so360,sogou`）；英文可用 `engine=google`（会走浏览器，慢几秒）。
  只想看某个站点用 `domain=`，别在 query 里手写 `site:`。
- 有一串固定关键词要查时用 `web_search_multi`，一个进程查完，比连调 N 次 `web_search` 省。
- `web_read` 输出末尾那行 `<!-- url | title | N chars | backend | ms -->` 是元信息，
  看见 `WARNING` 或字数只有几十字就是页面被挡 / 需要登录，换一条结果或换来源，别当成空页交差。
- 正文默认截 8000 字（宿主只留 32KB）。提示 `truncated` 时才调大 `max_chars`，别一次拉到 12000。
- 连搜失败或怀疑环境问题时，让人在插件目录跑 `python adapter.py doctor`，
  调用记录在 `~/.mini_code/logs/web-search.jsonl`。
