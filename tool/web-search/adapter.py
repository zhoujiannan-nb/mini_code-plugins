#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mini_code 工具插件「web-search」的适配器 v2（kind=tool）。

宿主的调用契约（见 mini_code/plugin/tool.go、docs/plugins.md 第三节）：

  * 模型给的参数对象以 **JSON 写到本脚本的 stdin**，不是命令行参数；
    plugin.json 里的 command/args 是静态的（不进命令行 → 没有引号/注入问题）。
  * 工作目录 = 插件目录。
  * stdout 就是返回给模型的结果；超过 32KB 宿主会截断（中文 1 字 3 字节）。
  * 失败时非零退出，原因写 stderr，stdout 保持干净。
  * 宿主会给子进程注入 PYTHONUTF8=1 / PYTHONIOENCODING=utf-8。

子命令（由 plugin.json 的 args 指定）：

    python adapter.py search  < params.json     # 搜关键词，输出 JSON
    python adapter.py read    < params.json     # 读正文，输出 markdown + 一行元信息
    python adapter.py multi   < params.json     # 一次查多个关键词，输出 JSON
    python adapter.py doctor  < params.json     # 自检（环境/代理/引擎），不参与模型调用

v2 和 v1 的区别：真正干活的是同目录的 fastpath.py，**默认走 HTTP**
（so360 → 必应 → 搜狗 → 百度 → DuckDuckGo，带相关性闸门），Playwright 只在
HTTP 全挂时懒启动。v1 每次调用都要冷启动一次 Chromium，且没有质量闸门，
实测 10 次查询只有 4 次能给出可用结果、中位 3.5s、最坏 90s 超时；
v2 同样 10 次查询 10 次可用、中位 1.3s。插件不再依赖外部的 web_search 项目
（装了它会给浏览器兜底多一套更准的选择器，没装也照样跑）。

配置：本目录 config.json，逐字段可省。环境变量 MINICODE_WEB_SEARCH_* 优先。
"""

import json
import os
import re
import sys
import time

# 别在插件目录里留 __pycache__：插件目录必须保持"只有文件"，多一个子目录
# 宿主的升级/校验就会出问题（仓库里专门为它写过一条规则）。
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CONFIG_FILE = "config.json"

MAX_RESULTS = 20
MAX_QUERIES = 8
MAX_CHARS_DEFAULT = 8000
MAX_CHARS_LIMIT = 12000
DEADLINE_RANGE = (5, 120)          # 整链路预算（秒），宿主侧 timeout_seconds 是硬上限
GATE_RANGE = (0.0, 0.95)

# HTTP 引擎（fastpath.HTTP_ENGINES 的键）
HTTP_ENGINES = ("so360", "bing-cn", "bing", "sogou", "baidu", "ddg")
BROWSER_ENGINES = ("google", "bing", "baidu", "so360", "sogou")
MODES = ("auto", "fast", "browser")

# 老参数名的兼容映射：模型缓存里可能还写着 v1 的 engine 值
ENGINE_ALIAS = {
    "bing-cn": "bing-cn", "bingcn": "bing-cn", "cnbing": "bing-cn", "cn": "bing-cn",
    "bing": "bing-cn", "www.bing": "bing",
    "360": "so360", "so": "so360", "so.com": "so360", "qihoo": "so360",
    "sogou": "sogou", "soso": "sogou",
    "baidu": "baidu", "百度": "baidu",
    "ddg": "ddg", "duckduckgo": "ddg", "duck": "ddg",
    "google": "google",
}
# 知乎的浏览器抓取路径在实测里 12 次全 0（登录墙 + 选择器失效），别再骗模型了
RETIRED_ENGINE_HINT = {
    "zhihu": ("zhihu 已从引擎里下线（无头浏览器 12 次全 0 条），改用 sogou/so360 搜中文内容；"
              "只想看知乎就加 domain=zhihu.com"),
}


# --------------------------------------------------------------------------
# 小工具（宿主要求：错误进 stderr + 非零退出）
# --------------------------------------------------------------------------

def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(message, code=2):
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
        try:
            num = int(float(val))
        except (TypeError, ValueError):
            die("参数 %r 必须是整数，收到 %r" % (key, val))
    return max(low, min(high, num))


def floater(params, key, default, low, high):
    val = params.get(key)
    if val is None or val == "":
        return default
    try:
        num = float(val)
    except (TypeError, ValueError):
        die("参数 %r 必须是数字，收到 %r" % (key, val))
    return max(low, min(high, num))


def boolean(params, key, default=False):
    val = params.get(key)
    if val is None:
        return default
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(val)


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

def apply_headless(params, fastpath):
    """headless=false 只影响浏览器兜底 —— HTTP 路径压根不开浏览器。"""
    if params.get("headless") is not None:
        fastpath.HEADLESS = boolean(params, "headless", True)


def load_config():
    """config.json（可缺）+ 环境变量覆盖。字段全可省，缺了用代码里的默认。"""
    cfg = {}
    path = os.path.join(HERE, CONFIG_FILE)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh) or {}
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception as exc:
            sys.stderr.write("config.json 读失败（用默认值）：%s\n" % exc)
    for key in ("chain", "browser_chain", "mode", "proxy", "searxng_url",
                "log_path", "web_search_home"):
        env = os.environ.get("MINICODE_WEB_SEARCH_" + key.upper())
        if env:
            cfg[key] = env
    for key in ("gate", "deadline_s", "max_results", "log"):
        env = os.environ.get("MINICODE_WEB_SEARCH_" + key.upper())
        if env:
            cfg[key] = env
    if cfg.get("web_search_home"):
        # 装了外部 web_search 就顺手告诉 fastpath（浏览器兜底会多一套选择器）
        os.environ.setdefault("MINICODE_WEB_SEARCH_HOME", str(cfg["web_search_home"]))
    if cfg.get("searxng_url"):
        import fastpath
        if not fastpath.add_searxng(cfg["searxng_url"]):
            sys.stderr.write("searxng_url 不像合法 URL，忽略：%r\n" % cfg.get("searxng_url"))
        else:
            cfg["chain"] = "searxng," + str(cfg.get("chain") or "so360,bing-cn,sogou,baidu,ddg")
    return cfg


def chain_of(cfg, params, key="chain", default=None):
    """没写这个参数时返回 None（=「没意见」，让上层去用默认链），别在这里替模型做主。"""
    raw = text(params, key, maxlen=300) or cfg.get(key) or default
    if raw is None:
        return None
    if isinstance(raw, str):
        names = [n.strip().lower() for n in re.split(r"[,;|/]", raw) if n.strip()]
    elif isinstance(raw, (list, tuple)):
        names = [str(n).strip().lower() for n in raw if str(n).strip()]
    else:
        die("%s 要写成引擎名，或逗号分隔的引擎链" % key)
    return names


def resolve_engine(params, cfg):
    """engine（钉一个）/ chain（自己排）/ 默认链，三种写法收拢成 (chain, browser_chain)。

    返回 (chain, browser_chain, note)；note 是给用户看的解释（比如 zhihu 的下线提示）。
    """
    import fastpath
    note = None
    eng = text(params, "engine")
    if eng:
        key = eng.lower()
        if key in RETIRED_ENGINE_HINT:
            note = RETIRED_ENGINE_HINT[key]
            # 360 排前面：它给的是直链，搜狗给的是 /link?url= 跳转链（可读性差一档）
            return (["so360", "sogou"], [], note)
        if key in ("auto", "default", ""):
            eng = None
        else:
            mapped = ENGINE_ALIAS.get(key)
            if mapped is None:
                die("engine 只认 %s（也可以传 chain=自定义链），收到 %r"
                    % ("/".join(sorted(set(list(HTTP_ENGINES) + list(BROWSER_ENGINES) + ["auto"]))), eng))
            if mapped == "google":                      # 只有浏览器通道
                return ([], ["google"], note)
            return ([mapped], [], note)

    chain = chain_of(cfg, params, "chain")
    browser = chain_of(cfg, params, "browser_chain")
    mode = (text(params, "mode") or cfg.get("mode") or "auto").lower()
    if mode not in MODES:
        die("mode 只认 %s，收到 %r" % ("/".join(MODES), mode))
    fallback = text(params, "fallback", maxlen=200)     # v1 的参数，仍然认
    if chain is None and fallback and fallback.lower() not in ("auto", "none"):
        chain = [ENGINE_ALIAS.get(n.strip().lower(), n.strip().lower())
                 for n in re.split(r"[,;|]", fallback) if n.strip()]
    if chain is None:
        chain = list(fastpath.DEFAULT_CHAIN)
    if browser is None:
        browser = list(fastpath.BROWSER_CHAIN) if mode != "fast" else []
    if mode == "browser":
        chain, browser = [], browser or list(fastpath.BROWSER_CHAIN)
    elif mode == "fast":
        browser = []
    bad = [n for n in chain if n not in HTTP_ENGINES and n != "searxng"]
    if bad:
        die("chain 里有不支持的 HTTP 引擎：%s（可用：%s）"
            % ("、".join(bad), "、".join(HTTP_ENGINES + ["searxng"])))
    return chain, browser, note


# --------------------------------------------------------------------------
# 观测日志（P3）：每次调用记一行 JSONL，出问题时有据可查
# --------------------------------------------------------------------------

def log_path(cfg):
    p = cfg.get("log_path")
    if p:
        return os.path.expanduser(str(p))
    home = os.environ.get("MINICODE_HOME") or os.path.join(os.path.expanduser("~"), ".mini_code")
    return os.path.join(home, "logs", "web-search.jsonl")


def observe(cfg, record):
    """写失败不能影响主流程，静默吞掉；超过 512KB 轮转一次。"""
    if not boolean(cfg, "log", True):
        return
    try:
        path = log_path(cfg)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path) and os.path.getsize(path) > 512 * 1024:
            try:
                os.replace(path, path + ".1")
            except OSError:
                pass
        record = dict(record)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def cmd_search(params, cfg):
    import fastpath
    query = text(params, "query", required=True, maxlen=300)
    chain, browser, note = resolve_engine(params, cfg)
    gate = floater(params, "gate", float(cfg.get("gate", 0.5)), *GATE_RANGE)
    deadline = number(params, "deadline_s", int(cfg.get("deadline_s", 25)), *DEADLINE_RANGE)
    max_results = number(params, "max", int(cfg.get("max_results", 10)), 1, MAX_RESULTS)
    proxy = text(params, "proxy") or cfg.get("proxy") or "auto"
    if proxy.lower() in ("off", "none", "no", "direct"):
        proxy = None
    domain = text(params, "domain", maxlen=200)
    if domain:
        domain = domain.lstrip(".")
    debug = boolean(params, "debug", False)
    apply_headless(params, fastpath)

    res = fastpath.search(query, chain=chain, browser_chain=browser,
                          max_results=max_results, gate=gate, proxy=proxy,
                          allow_browser=bool(browser), timeout=deadline, domain=domain)
    items = res.get("items") or []
    rel = float(res.get("rel") or 0.0)
    warning = res.get("warning") or (res.get("err") or None)
    if domain and not items:
        warning = (warning + "；" if warning else "") + \
            "整条引擎链上都没有 %s 的结果：去掉 domain 再搜一次试试" % domain
    if note:
        warning = (warning + "；" if warning else "") + note

    # 闸门没过 / 一条没有 / 被引流页顶掉 —— 一律显式标 degraded，让模型知道别直接引用
    degraded = bool(not items or rel < gate or warning)
    payload = {
        "ok": bool(items),
        "command": "search",
        "query": query,
        "engine": res.get("engine"),
        "channel": res.get("channel"),
        "relevance": round(rel, 2),
        "degraded": degraded,
        "count": len(items),
        "results": [dict(it, position=i + 1) for i, it in enumerate(items)],
        "engines_tried": res.get("engines_tried") or [],
        "elapsed_ms": res.get("elapsed_ms"),
    }
    if degraded:
        payload["warning"] = warning or "相关性不足（%.0f%% < %.0f%%）" % (rel * 100, gate * 100)
        payload["hint"] = ("这些结果不可信：换个 engine/chain、换关键词（试试加限定词或换英文）"
                           "重搜，别直接引用上面的标题下结论。")
    if domain:
        payload["domain"] = domain
    if debug:
        payload["debug"] = {"chain": chain, "browser_chain": browser, "gate": gate,
                            "deadline_s": deadline, "proxy": proxy,
                            "url": res.get("url"), "http_code": res.get("code")}
    observe(cfg, {"cmd": "search", "query": query, "ok": payload["ok"],
                  "engine": payload["engine"], "channel": payload["channel"],
                  "rel": payload["relevance"], "degraded": degraded,
                  "count": payload["count"], "elapsed_ms": payload["elapsed_ms"],
                  "tried": payload["engines_tried"], "warning": payload.get("warning")})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if items else 1


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------

def cmd_read(params, cfg):
    import fastpath
    url = text(params, "url", required=True, maxlen=2000)
    fmt = (text(params, "format") or "markdown").lower()
    if fmt not in ("markdown", "text"):
        die("format 只认 markdown 或 text，收到 %r" % fmt)
    max_chars = number(params, "max_chars", MAX_CHARS_DEFAULT, 500, MAX_CHARS_LIMIT)
    proxy = text(params, "proxy") or cfg.get("proxy") or "auto"
    if proxy.lower() in ("off", "none", "no", "direct"):
        proxy = None
    apply_headless(params, fastpath)
    res = fastpath.read_url(
        url, max_chars=max_chars, fmt=fmt,
        wait_selector=text(params, "wait_selector", maxlen=300),
        scroll=boolean(params, "scroll", False),
        timeout_ms=number(params, "timeout_ms", 15000, 3000, 60000),
        proxy=proxy,
        allow_browser=boolean(params, "browser", True) and
        (text(params, "mode") or cfg.get("mode") or "auto") != "fast")

    observe(cfg, {"cmd": "read", "query": url, "ok": res["ok"], "code": res.get("code"),
                  "chars": res.get("chars"), "backend": res.get("backend"),
                  "elapsed_ms": res.get("ms"), "warning": res.get("warning")})
    if not res["ok"]:
        die("读不到 %s：%s（backend=%s，%dms）"
            % (url, res.get("err"), res.get("backend"), res.get("ms") or 0), 1)

    if boolean(params, "json", False):
        print(json.dumps(dict(res, command="read"), ensure_ascii=False, indent=2))
        return 0
    # 默认回 markdown：宿主只留 32KB，包成 JSON 会把换行全转义成 \n 白白吃 token。
    # 元信息压成一行 HTML 注释，模型看得见、下游好剥（v1 就是这个格式，保持兼容）。
    meta = "%s | %s | %d chars | %s | %dms" % (res.get("url"), res.get("title") or "-",
                                               res.get("chars"), res.get("backend"),
                                               res.get("ms"))
    if res.get("truncated"):
        meta += " | truncated, raise max_chars for the rest"
    if res.get("warning"):
        meta += " | WARNING: %s" % res["warning"]
    print(res["text"].rstrip())
    print("\n<!-- %s -->" % meta)
    return 0


# --------------------------------------------------------------------------
# multi
# --------------------------------------------------------------------------

def cmd_multi(params, cfg):
    raw = params.get("queries")
    if raw is None:
        raw = text(params, "query", required=True)
    if isinstance(raw, str):
        queries = [q.strip() for q in re.split(r"[\n;|]", raw)]
    elif isinstance(raw, list):
        queries = [str(q).strip() for q in raw]
    else:
        die("queries 要写成字符串数组，或一个字符串（\\n ; | 分隔）")
    queries = [q for q in queries if q][:MAX_QUERIES]
    if not queries:
        die("参数 queries 不能为空")

    import fastpath
    chain, browser, note = resolve_engine(params, cfg)
    gate = floater(params, "gate", float(cfg.get("gate", 0.5)), *GATE_RANGE)
    deadline_each = number(params, "deadline_s", int(cfg.get("deadline_s", 25)), *DEADLINE_RANGE)
    max_results = number(params, "max", 5, 1, MAX_RESULTS)
    proxy = text(params, "proxy") or cfg.get("proxy") or "auto"
    if proxy.lower() in ("off", "none", "no", "direct"):
        proxy = None

    apply_headless(params, fastpath)
    entries, any_ok = [], False
    for i, q in enumerate(queries):
        if i:
            time.sleep(number(params, "gap_ms", 1200, 0, 10000) / 1000.0)
        res = fastpath.search(q, chain=chain, browser_chain=browser, max_results=max_results,
                              gate=gate, proxy=proxy, allow_browser=bool(browser),
                              timeout=deadline_each)
        items = res.get("items") or []
        rel = float(res.get("rel") or 0.0)
        warning = res.get("warning") or (res.get("err") or None)
        if note:
            warning = (warning + "；" if warning else "") + note
        degraded = bool(not items or rel < gate or warning)
        any_ok = any_ok or bool(items)
        entries.append({
            "query": q, "ok": bool(items), "engine": res.get("engine"),
            "channel": res.get("channel"), "relevance": round(rel, 2), "degraded": degraded,
            "elapsed_ms": res.get("elapsed_ms"),
            "results": [dict(it, position=n + 1) for n, it in enumerate(items)],
            "warning": warning if degraded else None,
        })
        observe(cfg, {"cmd": "multi", "query": q, "ok": bool(items),
                      "engine": res.get("engine"), "rel": round(rel, 2),
                      "degraded": degraded, "count": len(items),
                      "elapsed_ms": res.get("elapsed_ms")})
    print(json.dumps({"ok": any_ok, "command": "web_search_multi", "count": len(entries),
                      "results": entries}, ensure_ascii=False, indent=2))
    return 0 if any_ok else 1


# --------------------------------------------------------------------------
# doctor：环境自检（不参与模型调用，给人排障用）
# --------------------------------------------------------------------------

def cmd_doctor(params, cfg):
    import fastpath
    report = {"python": sys.version.split()[0], "here": HERE, "config": cfg,
              "log_path": log_path(cfg), "deps": {}, "proxy": None, "engines": {}}
    for mod in ("playwright", "trafilatura", "bs4", "lxml"):
        try:
            m = __import__(mod)
            report["deps"][mod] = getattr(m, "__version__", "ok")
        except Exception as exc:
            report["deps"][mod] = "缺：%s" % type(exc).__name__
    proxy = cfg.get("proxy") or "auto"
    report["proxy"] = fastpath.detect_proxy() if proxy == "auto" else proxy
    chain = chain_of(cfg, params, "chain") or list(fastpath.DEFAULT_CHAIN)
    for eng in chain:
        if eng not in fastpath.HTTP_ENGINES:
            report["engines"][eng] = "未知引擎"
            continue
        t0 = time.time()
        try:
            r = fastpath.search_http(eng, "python 3.14 发布", proxy=report["proxy"], max_results=5)
            rel = fastpath.relevance_ratio("python 3.14 发布", r["items"]) if r["items"] else 0.0
            report["engines"][eng] = {"http": r["code"], "items": len(r["items"]),
                                      "rel": round(rel, 2), "ms": int((time.time() - t0) * 1000),
                                      "err": (r.get("err") or "")[:80]}
        except Exception as exc:
            report["engines"][eng] = "炸了：%s" % str(exc)[:100]
    if boolean(params, "browser", False):
        with fastpath.BrowserFallback(proxy=report["proxy"]) as bf:
            for eng in ("google", "baidu"):
                r = bf.search(eng, "python 3.14 发布", max_results=5, nav_timeout=20000)
                report["engines"]["browser:" + eng] = {
                    "items": len(r["items"]),
                    "rel": fastpath.relevance_ratio("python 3.14 发布", r["items"]),
                    "ms": r.get("ms"), "err": (r.get("err") or "")[:100]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


BUILDERS = {
    "search": cmd_search,
    "read": cmd_read,
    "multi": cmd_multi,
    "doctor": cmd_doctor,
}


def main():
    _utf8_stdio()
    command = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    builder = BUILDERS.get(command)
    if builder is None:
        die("未知子命令 %r，可用：%s" % (command, " / ".join(sorted(BUILDERS))))
    params = read_params()
    cfg = load_config()
    try:
        return builder(params, cfg)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        die("被用户中断", 130)
    except Exception as exc:                      # 给模型一行可读的错，而不是整页 traceback
        die("%s: %s\n（子命令 %s；排障先跑 python %s doctor）"
            % (type(exc).__name__, exc, command, os.path.join(HERE, "adapter.py")), 1)


if __name__ == "__main__":
    sys.exit(main())
