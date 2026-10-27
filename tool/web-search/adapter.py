#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mini_code 工具插件「web-search」的适配器（第二类 / kind=tool）。

宿主的调用契约（见 mini_code/plugin/tool.go、docs/plugins.md 第三节）：

  * 模型给出的参数对象以 **JSON 写到本脚本的 stdin**，不是命令行参数；
    plugin.json 里的 command/args 是静态的（不进命令行 → 没有引号/注入问题）。
  * 工作目录 = 插件目录。
  * stdout 就是返回给模型的结果；超过 32KB 宿主会截断。
  * 失败时非零退出，并把原因写到 stderr。
  * 宿主会给子进程注入 PYTHONUTF8=1 / PYTHONIOENCODING=utf-8。

子命令由 plugin.json 的 args 指定：

    python adapter.py search   < params.json
    python adapter.py read     < params.json
    python adapter.py multi    < params.json

真正干活的是 D:\\project_ai\\web_search（Playwright 浏览器驱动）。
它的位置可以在下面三个地方任一处覆盖（优先级从高到低）：

    1. 环境变量 MINICODE_WEB_SEARCH_HOME
    2. 本目录下的 config.json  {"web_search_home": "D:\\\\project_ai\\\\web_search"}
    3. 代码里的 FALLBACK_HOME
"""

import json
import os
import re
import sys

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_HOME = "MINICODE_WEB_SEARCH_HOME"
CONFIG_FILE = "config.json"
FALLBACK_HOME = r"D:\project_ai\web_search"

ENGINES = ("bing", "baidu", "google", "duckduckgo", "zhihu")

# 宿主只收 32KB（超出截断）。中日韩字符 UTF-8 里一个字 3 字节，
# 所以正文默认 8000 字（约 24KB）就差不多到顶了，别把它调到 20000。
MAX_CHARS_DEFAULT = 8000
MAX_CHARS_LIMIT = 12000
MAX_RESULTS = 20          # --max 上限
MAX_PAGES = 3             # --pages 上限（每页都要真开一次浏览器）
MAX_QUERIES = 8           # multi 一次最多几个关键词
TIMEOUT_MS_RANGE = (3000, 60000)


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def _utf8_stdio():
    """保证 stdout/stderr 是 UTF-8：Windows 控制台默认跟着 GBK 代码页走，
    打印中文就会 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(message, code=2):
    """失败：原因写 stderr，非零退出（stdout 保持干净）。"""
    sys.stderr.write(str(message).rstrip() + "\n")
    sys.stderr.flush()
    raise SystemExit(code)


def read_params():
    """参数从 stdin 进来。用 buffer 显式按 UTF-8 解，不跟控制台代码页走。"""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception:
        raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        params = json.loads(raw)
    except ValueError as exc:
        die("参数不是合法 JSON：%s（应该形如 {\"query\": \"sglang mtp\"}）" % exc)
    if not isinstance(params, dict):
        die("参数必须是一个 JSON 对象，收到 %s" % type(params).__name__)
    return params


def text(params, key, required=False, maxlen=4000):
    val = params.get(key)
    if val is None:
        if required:
            die("缺少必填参数 %r" % key)
        return None
    if not isinstance(val, str):
        val = str(val)
    val = val.strip()
    if not val:
        if required:
            die("参数 %r 不能为空" % key)
        return None
    return val[:maxlen]


def number(params, key, default, low, high):
    val = params.get(key)
    if val is None or val == "":
        return default
    try:
        num = int(val)
    except (TypeError, ValueError):
        die("参数 %r 必须是整数，收到 %r" % (key, val))
    return max(low, min(high, num))


def boolean(params, key, default=False):
    val = params.get(key)
    if val is None:
        return default
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(val)


def engine_of(params):
    eng = text(params, "engine")
    if not eng:
        return None                      # 交给 ws.py 用它自己的默认值
    eng = eng.lower()
    if eng not in ENGINES:
        die("engine 只认 %s，收到 %r" % ("/".join(ENGINES), eng))
    return eng


def web_search_home():
    """找到 web_search 包的父目录。三处覆盖，见文件头。"""
    home = os.environ.get(ENV_HOME)
    if not home:
        cfg = os.path.join(HERE, CONFIG_FILE)
        if os.path.isfile(cfg):
            try:
                with open(cfg, encoding="utf-8") as fh:
                    home = (json.load(fh) or {}).get("web_search_home")
            except Exception as exc:
                sys.stderr.write("config.json 读失败（忽略）：%s\n" % exc)
    home = home or FALLBACK_HOME
    home = os.path.abspath(os.path.expanduser(str(home)))
    if not os.path.isfile(os.path.join(home, "web_search", "cli.py")):
        die(
            "找不到 web_search（在 %s 下没有 web_search/cli.py）。\n"
            "装它需要三步：\n"
            "  1. 把项目放到某个目录（默认 D:\\project_ai\\web_search）\n"
            "  2. pip install playwright pydantic trafilatura && playwright install chromium\n"
            "  3. 改本插件目录里的 config.json 的 web_search_home，"
            "或设环境变量 %s" % (home, ENV_HOME)
        )
    return home


def load_cli(home):
    """直接 import，省掉再开一个 python 解释器的开销。"""
    if home not in sys.path:
        sys.path.insert(0, home)
    try:
        from web_search.cli import main  # noqa: WPS433
    except ImportError as exc:
        die(
            "导入 web_search 失败：%s\n"
            "多半是缺依赖。在跑 mini_code 的那个 python 里执行：\n"
            "  pip install playwright pydantic trafilatura\n"
            "  playwright install chromium" % exc
        )
    return main


# --------------------------------------------------------------------------
# 参数 → ws.py 的 argv
# --------------------------------------------------------------------------

def _common_flags(params):
    flags = []
    if boolean(params, "headless", True) is False:
        flags.append("--no-headless")     # 默认就是无头，只有明确要窗口时才加
    timeout_ms = params.get("timeout_ms")
    if timeout_ms not in (None, ""):
        flags += ["--timeout", str(number(params, "timeout_ms", 15000, *TIMEOUT_MS_RANGE))]
    return flags


def argv_search(params):
    query = text(params, "query", required=True)
    argv = ["search", query, "--json"]
    # 不写 --engine 时 ws.py 自己默认 baidu；这里显式钉成 bing（最稳），
    # 和 plugin.json 里给模型看的描述一致。
    argv += ["--engine", engine_of(params) or "bing"]
    argv += ["--max", str(number(params, "max", 10, 1, MAX_RESULTS))]
    pages = number(params, "pages", 1, 1, MAX_PAGES)
    if pages > 1:
        argv += ["--pages", str(pages)]
    domain = text(params, "domain", maxlen=200)
    if domain:
        argv += ["--domain", domain.lstrip(".")]
    fallback = text(params, "fallback", maxlen=200)
    if fallback:
        argv += ["--fallback", fallback.lower()]
    return argv + _common_flags(params)


def argv_read(params):
    url = text(params, "url", required=True, maxlen=2000)
    if not url.lower().startswith(("http://", "https://", "file://")):
        url = "https://" + url
    argv = ["read", url]
    fmt = (text(params, "format") or "markdown").lower()
    if fmt not in ("markdown", "text"):
        die("format 只认 markdown 或 text，收到 %r" % fmt)
    argv += ["--format", fmt]
    # 不给 --max-chars 的话 ws.py 默认 20000 字，中文正文会直接撞上宿主的 32KB 上限，
    # 所以这里主动夹住。
    argv += ["--max-chars", str(number(params, "max_chars", MAX_CHARS_DEFAULT, 500, MAX_CHARS_LIMIT))]
    selector = text(params, "wait_selector", maxlen=300)
    if selector:
        argv += ["--wait-selector", selector]
    if boolean(params, "scroll", False):
        argv.append("--scroll")
    return argv + _common_flags(params)


def argv_multi(params):
    raw = params.get("queries")
    if raw is None:
        raw = text(params, "query", required=True)
    if isinstance(raw, str):
        # 容忍模型把列表写成一行字符串
        queries = [q.strip() for q in re.split(r"[\n;|]", raw)]
    elif isinstance(raw, list):
        queries = [str(q).strip() for q in raw]
    else:
        die("queries 要写成字符串数组，或一个字符串")
    queries = [q for q in queries if q][:MAX_QUERIES]
    if not queries:
        die("参数 queries 不能为空")
    argv = ["multi"] + queries + ["--json"]
    argv += ["--engine", engine_of(params) or "bing"]
    argv += ["--max", str(number(params, "max", 5, 1, MAX_RESULTS))]
    return argv + _common_flags(params)


BUILDERS = {
    "search": argv_search,
    "read": argv_read,
    "multi": argv_multi,
}


# --------------------------------------------------------------------------

def main():
    _utf8_stdio()
    command = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    builder = BUILDERS.get(command)
    if builder is None:
        die("未知子命令 %r，可用：%s" % (command, " / ".join(sorted(BUILDERS))))

    params = read_params()
    # debug 只是把 ws.py 的日志开到 DEBUG（走 stderr，不污染 stdout）
    argv = builder(params)
    if boolean(params, "debug", False):
        argv.append("--verbose")

    cli_main = load_cli(web_search_home())
    try:
        return cli_main(argv)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        die("被用户中断", 130)
    except Exception as exc:  # 让模型看到可读的一行，而不是整页 traceback
        die("%s: %s\n（子命令 %s；可先跑 python %s\\ws.py doctor 自检）"
            % (type(exc).__name__, exc, command, web_search_home()), 1)


if __name__ == "__main__":
    sys.exit(main())
