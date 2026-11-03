# -*- coding: utf-8 -*-
"""搜索快路径 —— web-search 插件 v2 的引擎层（插件自包含，不依赖外部项目）。

和 v1（每次都冷启动 Chromium 的 web_search 包）的区别：

  1. **先走纯 HTTP**（不开浏览器）：so360 / cn.bing / sogou / baidu / ddg，
     单次 300-1300ms；实测本机 so360 连续 12 次不衰减，是这里最抗造的通道。
  2. **相关性闸门**：结果里含查询词的比例 < gate 就判为"引擎反爬降级"，不算成功，
     直接换下一个引擎。v1 是"只要有结果就返回"，所以假结果（58同城/腾讯体育/
     B站直播 这类引流页）会被当成 ok=true 交给模型。
  3. **浏览器只做兜底**（cn.bing / google），HTTP 链全挂时才懒启动；SERP 抽取不写死
     class（各家三天两头改），并在这一步把 /goto?url=、/link?url= 这类包装链还原成真链。
  4. 出口代理自动探测（环境变量 → 注册表系统代理 → 常见本地端口），墙外引擎可用。
  5. read 也是 HTTP 优先（trafilatura 抽正文），只有 JS 页 / 412 / 403 才开浏览器。

命令行（调试用，正常由 adapter.py 调用）：
    python fastpath.py search "vllm 0.11 发布" --json
    python fastpath.py search "..." --chain ddg,bing-cn --no-browser
"""
import argparse
import http.cookiejar
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64decode, urlsafe_b64decode

MAX_HTML = 800_000
DECOY_HOSTS = (  # 明确的引流/导航页特征：出现在 top 结果里就是被反爬降级了
    "translate.google", "cdn.cnipa", "alipay.com", "xiaohongshu.com", "bilibili.com",
    "zhihu.com/question", "tencent.com", "docs.qq.com", "baidu.com/translate",
)
# 搜索引擎塞进来的"自己的小工具"，跟查询无关，直接丢（实测英文查询会插一条 fanyi.so.com）
ONEBOX_HOSTS = ("fanyi.so.com", "fanyi.baidu.com", "fanyi.youdao.com", "dict.",
                "idich.com", "kejiyi.com", "image.baidu.com", "trends.google")

UA_POOL = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/130.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0"),
]

PROXY_CANDIDATES = ("127.0.0.1:7897", "127.0.0.1:7890", "127.0.0.1:10809",
                    "127.0.0.1:1080", "127.0.0.1:8118")


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def detect_proxy(timeout=0.35):
    """探测本机是否在跑本地代理（Clash/v2rayN 之类）。有则返回 http url，无则 None。"""
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(k)
        if v:
            return v
    for host_port in PROXY_CANDIDATES:
        host, port = host_port.rsplit(":", 1)
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return "http://%s" % host_port
        except OSError:
            continue
    return None


def build_opener(proxy=None):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def http_get(url, proxy=None, timeout=12, headers=None, retries=1):
    """带 UA 轮换和（可选）代理的 GET；返回 (html, status, ms, err)。"""
    hdrs = {
        "User-Agent": (headers or {}).get("User-Agent") or UA_POOL[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    hdrs.update(headers or {})
    last_err = ""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=hdrs)
        t0 = time.time()
        try:
            with build_opener(proxy).open(req, timeout=timeout) as resp:
                body = resp.read(MAX_HTML).decode("utf-8", "replace")
                return body, resp.status, int((time.time() - t0) * 1000), ""
        except urllib.error.HTTPError as e:
            try:
                body = e.read(50000).decode("utf-8", "replace")
            except Exception:
                body = ""
            last_err = "HTTP %s" % e.code
            if e.code in (403, 429, 503):        # 明确的反爬/限流，换引擎比重试有用
                return body, e.code, int((time.time() - t0) * 1000), last_err
            if 400 <= e.code < 500:              # 4xx 重试也不会变好，带上状态码直接回
                return body, e.code, int((time.time() - t0) * 1000), last_err
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, str(e)[:80])
        if attempt < retries:
            hdrs["User-Agent"] = UA_POOL[(attempt + 1) % len(UA_POOL)]
    return "", 0, 0, last_err


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s or "")
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#x27;", "'")
          .replace("&#39;", "'").replace("&#x2F;", "/"))
    return re.sub(r"\s+", " ", s).strip()


def relevance_ratio(query, results):
    """结果里"命中查询词"的比例（和现状 web_search.utils 同口径，独立实现方便单飞）。"""
    q = (query or "").lower()
    words = [w for w in re.split(r"[\s,，。、（）()]+", q) if len(w) >= 2]
    if not words:
        return 1.0
    hits = 0
    for r in results:
        blob = ("%s %s %s" % (r.get("title", ""), r.get("link", ""),
                              r.get("snippet", ""))).lower()
        if any(w in blob for w in words):
            hits += 1
    return hits / max(1, len(results))


# ---------------------------------------------------------------------------
# 跳转链接还原
# ---------------------------------------------------------------------------

def unwrap_link(href, base=""):
    """把引擎跳转链接还原成真实 URL（离线能解的先解，解不了返回原链）。"""
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = base.rstrip("/") + href
    try:
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        for key in ("uddg", "url", "u", "q", "link"):
            if key in params:
                val = params[key][0]
                if val.startswith("http"):
                    return urllib.parse.unquote(val)
                if key == "u" and val.startswith("a1"):   # Bing ck/a?u=a1<base64>
                    enc = val[2:] + "=" * (-len(val[2:]) % 4)
                    for dec in (urlsafe_b64decode, b64decode):
                        try:
                            out = dec(enc).decode("utf-8", "ignore")
                            if out.startswith("http"):
                                return out
                        except Exception:
                            continue
    except Exception:
        pass
    return href


# ---------------------------------------------------------------------------
# 各引擎（纯 HTTP）
# ---------------------------------------------------------------------------

def _ddg(html, query):
    out = []
    for block in re.findall(r'(?is)<div class="result[^"]*[\s\S]{0,4000}?(?=<div class="result|\Z)',
                            html)[:40]:
        m = re.search(r'(?is)<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        link = m.group(1)
        if "uddg=" in link:                      # html 端点给的是 /l/?uddg=<urlencode> 跳转链
            link = urllib.parse.unquote(link.split("uddg=")[-1].split("&")[0])
        elif link.startswith("//"):
            link = "https:" + link
        sm = re.search(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', block)
        um = re.search(r'(?is)result__url[^>]*>(.*?)</', block)
        out.append({"title": strip_tags(m.group(2)), "link": link,
                    "snippet": strip_tags(sm.group(1)) if sm else "",
                    "source": strip_tags(um.group(1)) if um else ""})
    return out


def _bing(html, query):
    out = []
    blocks = re.split(r'(?is)<li class="b_algo', html)[1:41]
    for block in blocks:
        m = re.search(r'(?is)<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        sm = re.search(r'(?is)<p[^>]*class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block) \
            or re.search(r'(?is)<div class="b_caption[^"]*"[^>]*>[\s\S]{0,60}?<p[^>]*>(.*?)</p>', block)
        um = re.search(r'(?is)<cite[^>]*>(.*?)</cite>', block)
        out.append({"title": strip_tags(m.group(2)), "link": m.group(1),
                    "snippet": strip_tags(sm.group(1)) if sm else "",
                    "source": strip_tags(um.group(1)) if um else ""})
    return out


def _so360(html, query):
    out = []
    for block in re.split(r'(?is)<li class="res-list', html)[1:41]:
        m = re.search(r'(?is)<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        sm = (re.search(r'(?is)<p class="res-desc[^"]*"[^>]*>(.*?)</p>', block)
              or re.search(r'(?is)<div class="res-rich[^"]*"[^>]*>(.*?)</div>', block))
        um = re.search(r'(?is)class="res-site-name[^"]*"[^>]*>(.*?)</', block)
        out.append({"title": strip_tags(m.group(2)), "link": m.group(1),
                    "snippet": strip_tags(sm.group(1)) if sm else "",
                    "source": strip_tags(um.group(1)) if um else ""})
    return out


def _sogou(html, query):
    out = []
    for block in re.split(r'(?is)<div class="vrwrap|<div class="rb"', html)[1:41]:
        m = re.search(r'(?is)<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        sm = re.search(r'(?is)class="(?:text-wp|fz-mid space-txt)[^"]*"[^>]*>(.*?)</', block)
        out.append({"title": strip_tags(m.group(2)), "link": m.group(1),
                    "snippet": strip_tags(sm.group(1)) if sm else "", "source": ""})
    return out


def _baidu(html, query):
    out = []
    for block in re.split(r'(?is)<div[^>]+class="[^"]*(?:c-container|result c-container)', html)[1:41]:
        m = re.search(r'(?is)<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        sm = (re.search(r'(?is)<span[^>]*class="[^"]*content-right[^"]*"[^>]*>(.*?)</span>', block)
              or re.search(r'(?is)<div[^>]*class="[^"]*c-abstract[^"]*"[^>]*>(.*?)</div>', block))
        out.append({"title": strip_tags(m.group(2)), "link": m.group(1),
                    "snippet": strip_tags(sm.group(1)) if sm else "", "source": ""})
    return out


HTTP_ENGINES = {
    # name: (url 模板, 解析器, 是否建议走代理)
    "ddg": ("https://html.duckduckgo.com/html/?q={q}", _ddg, False),
    "bing-cn": ("https://cn.bing.com/search?q={q}&count=10", _bing, False),
    "bing": ("https://www.bing.com/search?q={q}&count=10", _bing, False),
    "so360": ("https://www.so.com/s?q={q}", _so360, False),
    "sogou": ("https://www.sogou.com/web?query={q}", _sogou, False),
    "baidu": ("https://www.baidu.com/s?wd={q}&rn=10", _baidu, False),
}

DEFAULT_CHAIN = ["so360", "bing-cn", "sogou", "baidu", "ddg"]
# 浏览器兜底顺序：cn.bing 给的是直链（最省事），google 的链接是加密包装链，
# 得多花一次 HTTP 才能还原；百度这边实测已经撞图形验证码，放最后。
BROWSER_CHAIN = ["bing", "google"]


def clean_items(items, limit=20):
    """去噪：引擎自己的小工具（翻译框、图片搜索）、重复链接、明显是验证页的标题。"""
    out, seen = [], set()
    for it in items or []:
        link = (it.get("link") or "").strip()
        title = (it.get("title") or "").strip()
        if not link.startswith("http") or not title:
            continue
        low = link.lower()
        if any(h in low for h in ONEBOX_HOSTS):
            continue
        if re.search(r"(安全验证|访问验证|请验证您是真人|unusual traffic|网络不给力|403|404 Not Found)",
                     title) and len(title) < 30:
            continue
        key = low.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        it["link"] = link
        it["title"] = title
        it.setdefault("source", urllib.parse.urlparse(link).netloc)
        it.setdefault("snippet", "")
        out.append(it)
        if len(out) >= limit:
            break
    return out



# ---------------------------------------------------------------------------
# 跳转链接还原（so.com/link?m=、sogou /link、百度 /link 这类不透明 token）
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, req, resp):       # noqa: N802 (urllib 命名)
        return resp

    https_response = http_response


REDIRECT_MARKS = ("/link?", "/redir", "/redirect", "/url?", "/goto?", "/ck/a")


def is_link_wrapper(url):
    return bool(url) and any(m in url for m in REDIRECT_MARKS)


def resolve_redirect(url, proxy=None, timeout=4, referer=None):
    """拿一次 302 的 Location 或 JS/meta 跳转目标；拿不到就返回原链。

    google 现在把真链藏在一个加密的 /goto?url=CAES... token 里（base64 解不出明文），
    但只要跟着 302 走就能拿到，所以必须发真实请求 —— 前提是 Referer 别太离谱。
    """
    js_pat = re.compile(
        r"""(?is)(?:window\.location\.replace\(|window\.replace\(location\.href=|"""
        r"""location\.href=|URL=['"]?|url=)['"]?(https?://[^'"()\s<>]+)""")
    headers = {"User-Agent": UA_POOL[0]}
    if referer:
        headers["Referer"] = referer
    elif "so.com" in url:
        headers["Referer"] = "https://www.so.com/"
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else
            urllib.request.BaseHandler(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            _NoRedirect)
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=timeout) as resp:
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location") or ""
                if loc.startswith("http"):
                    return loc
                if loc.startswith("/"):
                    p = urllib.parse.urlparse(url)
                    return "%s://%s%s" % (p.scheme, p.netloc, loc)
            if resp.status == 200:
                # 360/搜狗这类"包装页"：306 字节的 JS/meta-refresh，抓里面的目标 URL
                body = resp.read(4000).decode("utf-8", "replace")
                m = js_pat.search(body)
                if m:
                    return m.group(1).rstrip("\\")
    except Exception:
        pass
    return url



def resolve_items(items, proxy=None, budget=6.0, limit=10, referer=None):
    """把前 limit 条里"包装型跳转链"还原成真实 URL，总耗时不超过 budget 秒。"""
    t0 = time.time()
    for it in items[:limit]:
        if time.time() - t0 > budget:
            break
        if is_link_wrapper(it.get("link") or ""):
            real = resolve_redirect(it["link"], proxy=proxy, referer=referer)
            if real != it["link"]:
                it["link"] = real
                it["source"] = urllib.parse.urlparse(real).netloc   # 域名跟着换成真链的
    return items



def search_http(engine, query, proxy=None, max_results=10):
    tpl, parser, prefer_proxy = HTTP_ENGINES[engine]
    url = tpl.format(q=urllib.parse.quote(query))
    html, code, ms, err = http_get(url, proxy=proxy or (proxy if prefer_proxy else None))
    items = []
    if html:
        try:
            items = parser(html, query)
        except Exception as e:
            err = "parse: %s" % str(e)[:80]
    for it in items:
        it["link"] = unwrap_link(it["link"], base=tpl.split("?")[0])
    return {"engine": engine, "channel": "http", "url": url, "code": code, "ms": ms,
            "err": err, "items": clean_items(items, max_results)}


# ---------------------------------------------------------------------------
# 浏览器兜底（只在 HTTP 链全挂时懒启动）
# ---------------------------------------------------------------------------

# 浏览器兜底默认无头运行；adapter.py 会按参数 headless 改这个进程级开关
HEADLESS = True

BROWSER_URLS = {
    "google": "https://www.google.com/search?q={q}&num=20&hl=zh-CN",
    "bing": "https://cn.bing.com/search?q={q}&count=20",
    "baidu": "https://www.baidu.com/s?wd={q}&rn=20",
    "so360": "https://www.so.com/s?q={q}",
    "sogou": "https://www.sogou.com/web?query={q}",
}

# 通用抽取：先按 SERP 常见的"标题在 h3 里"取，取不满就退化成全量 a[href]。
# 各家 class 名三天两头改，所以不写死 class。
_JS_EXTRACT = r"""
() => {
  // class 名三天两头改，所以只认结构 + 事后过滤；相对链接必须绝对化（google 现在给
  // /goto?url=CAES... 这种相对包装链，不绝对化后面根本还原不出来）。
  const BAD_EXT = /\.(js|css|png|jpe?g|gif|svg|ico|woff2?|ttf|zip|rar|7z|pdf|mp4|avi|exe)($|\?)/i;
  const WRAP = /\/(goto|url|link|redirect|redir|ck\/a|imgurl)(\?|\/|$)/i;
  let baseHost = '';
  try { baseHost = new URL(document.baseURI).hostname.toLowerCase(); } catch (e) {}
  const SERP_FAMILY = /(^|\.)(google|bing|microsoft|baidu|so|sogou|sm|duckduckgo|yandex|zsos)\.(com|cn|com\.cn|ru)$/;
  const absolutize = (h) => { try { return new URL(h, document.baseURI).href; } catch (e) { return h; } };
  const out = [], seen = new Set();
  const groups = [
    document.querySelectorAll('h3 a, .zReHs, .c-title a, .t a, [data-ved] a[href]'),
    document.querySelectorAll('.g a, .result a, .b_algo a, article a, li a'),
    document.querySelectorAll('a[href]')
  ];
  for (const list of groups) {
    for (const a of list) {
      const t = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
      let h = a.getAttribute('href') || '';
      if (!h || /^(mailto|tel|javascript|data|about):/i.test(h)) continue;
      h = absolutize(h);
      const m = h.match(/[?&](?:uddg|url|u|URL|q)=([^&#]+)/);      // ddg 的 uddg= 是明文
      if (m) { let d = ''; try { d = decodeURIComponent(m[1]); } catch (e) {}
               if (/^https?:/i.test(d)) h = d; }
      if (!/^https?:/i.test(h) || t.length < 6 || t.length > 200) continue;
      if (BAD_EXT.test(h)) continue;
      const hh = ((h.match(/^https?:\/\/([^/?#]+)/i) || [])[1] || '').toLowerCase();
      const isSerp = hh === baseHost || hh === 'www.' + baseHost || SERP_FAMILY.test(hh);
      // 搜索引擎自己的域名：只留跳转包装链（后面会还原成真链），其余（搜索建议、
      // 图片、登录、翻译、sets）全是噪音
      if (isSerp && !WRAP.test(h)) continue;
      if (/(翻译此页|安全验证|网络不给力|请验证您是真人|unusual traffic|访问验证|登录)/.test(t)) continue;
      const key = h.split('#')[0];
      if (seen.has(key)) continue;
      seen.add(key);
      let snip = '';
      let box = a.closest('div,li,article');
      for (let i = 0; box && i < 3 && snip.length < 60; i++, box = box.parentElement)
        snip = (box.innerText || '').replace(/\s+/g, ' ').trim();
      out.push({title: t.slice(0, 200), link: h,
                snippet: snip.replace(t, '').replace(/\s+/g, ' ').trim().slice(0, 240)});
      if (out.length >= 25) return out;
    }
    if (out.length >= 3) return out;                 // 第一组就够，别拿导航栏凑数
  }
  return out;
}
"""

_WS_HOME_ENV = "MINICODE_WEB_SEARCH_HOME"
_engine_factory_cache = {}


def _engine_factory(engine):
    """可选加速带：本机若装了 web_search 包，就用它现成的 SERP 选择器（更准）。

    插件**不依赖**它 —— 找不到就返回 None，_JS_EXTRACT 自己搞定。
    """
    if engine in _engine_factory_cache:
        return _engine_factory_cache[engine]
    factory = None
    try:
        try:
            from web_search.engines import EngineFactory
        except ImportError:
            home = os.environ.get(_WS_HOME_ENV) or r"D:\project_ai\web_search"
            if os.path.isfile(os.path.join(home, "web_search", "cli.py")):
                if home not in sys.path:
                    sys.path.insert(0, home)
                from web_search.engines import EngineFactory
        factory = EngineFactory.create(engine)
    except Exception:
        factory = None
    _engine_factory_cache[engine] = factory
    return factory


class BrowserFallback:
    """兜底用的浏览器。整个进程只开一次 Chromium，多引擎复用同一个 page。

    HEADLESS 是进程级开关（adapter 按参数里的 headless 写它），
    调试时设成 false 就能看着浏览器跑。
    """

    def __init__(self, proxy=None, headless=None):
        self.proxy = proxy
        self.headless = HEADLESS if headless is None else headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        for attr in ("_browser", "_pw"):
            obj = getattr(self, attr, None)
            try:
                if obj is not None:
                    (obj.stop() if attr == "_pw" else obj.close())
            except Exception:
                pass
            setattr(self, attr, None)

    def _ensure_page(self):
        """懒启动：整个进程只开一次 Chromium，多引擎复用同一个 page。"""
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            args = ["--disable-blink-features=AutomationControlled", "--no-sandbox",
                    "--disable-dev-shm-usage", "--disable-gpu"]
            kwargs = {}
            if self.proxy:
                kwargs["proxy"] = {"server": self.proxy}
            self._browser = self._pw.chromium.launch(headless=self.headless, args=args, **kwargs)
        if self._ctx is None:
            self._ctx = self._browser.new_context(
                user_agent=UA_POOL[0], locale="zh-CN", timezone_id="Asia/Shanghai",
                viewport={"width": 1366, "height": 900})
            self._page = self._ctx.new_page()
        return self._page

    def search(self, engine, query, max_results=10, nav_timeout=20000, settle=8):
        t0 = time.time()
        url = BROWSER_URLS.get(engine, BROWSER_URLS["bing"]).format(
            q=urllib.parse.quote(query))
        try:
            page = self._ensure_page()
        except Exception as e:                     # 没装 playwright / 没装 chromium
            return {"engine": engine, "channel": "browser", "url": url, "code": 0,
                    "ms": int((time.time() - t0) * 1000), "err": "browser: %s" % str(e)[:100],
                    "items": []}
        try:
            page.goto(url, timeout=nav_timeout, wait_until="domcontentloaded")
            eng = _engine_factory(engine)          # 有 web_search 就用它的选择器（更准）
            base = page.url

            def fix(its):
                """把相对链接绝对化 —— google 现在给的是 /goto?url=…，不绝对化后面
                既过不了 clean_items，也没法跟 302 还原成真链。"""
                for it in its or []:
                    link = (it.get("link") or "").strip()
                    if link and not link.lower().startswith(("http://", "https://")):
                        it["link"] = urllib.parse.urljoin(base, link)
                return its or []

            deadline = time.time() + settle
            items = []
            while True:
                if eng is not None:
                    try:
                        items = fix([r.to_dict() for r in eng.extract_results(page)])
                    except Exception:
                        items = []
                if not clean_items(items, max_results):
                    items = fix(page.evaluate(_JS_EXTRACT))   # 选择器过期了就自己抽
                if items or time.time() > deadline:
                    break
                page.wait_for_timeout(250)
            return {"engine": engine, "channel": "browser", "url": url, "code": 200,
                    "ms": int((time.time() - t0) * 1000), "err": "",
                    "items": clean_items(items, max_results)}
        except Exception as e:
            return {"engine": engine, "channel": "browser", "url": url,
                    "ms": int((time.time() - t0) * 1000), "err": str(e)[:120], "items": []}

    def fetch_html(self, url, nav_timeout=20000, wait_selector=None, scroll=False,
                   settle_ms=1200):
        """read 的浏览器兜底：HTTP 拿不到正文（JS 渲染 / 412 / 反爬）时才走这里。"""
        page = self._ensure_page()
        page.goto(url, timeout=nav_timeout, wait_until="domcontentloaded")
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=min(nav_timeout, 8000))
            except Exception:
                pass
        if scroll:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
            except Exception:
                pass
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(settle_ms)       # 给 SPA 一点水合时间
        except Exception:
            pass
        return page.content()


# ---------------------------------------------------------------------------
# 编排：引擎链 + 相关性闸门
# ---------------------------------------------------------------------------

def looks_decoy(items):
    """top3 全是已知引流页 → 判定反爬降级。"""
    if len(items) < 3:
        return False
    top = items[:3]
    hit = sum(1 for it in top if any(d in (it.get("link") or "") for d in DECOY_HOSTS))
    return hit >= 2


def search(query, chain=None, browser_chain=None, max_results=10, gate=0.5,
           proxy="auto", allow_browser=True, timeout=25, domain=None):
    """引擎链 + 相关性闸门：过了闸门才算成功，否则换下一个引擎。

    domain 不是"事后过滤"而是"整条链都找不到这个域名就继续换引擎"——
    不然第一个引擎交卷就把它筛成 0 条，白瞎了后面的机会。
    """
    chain = list(chain) if chain is not None else list(DEFAULT_CHAIN)
    browser_chain = list(browser_chain) if browser_chain is not None else list(BROWSER_CHAIN)
    proxy_url = detect_proxy() if proxy == "auto" else (proxy or None)
    domain = (domain or "").lower().strip() or None
    t_start = time.time()
    tried, best, best_score = [], None, -1.0
    warnings = []

    def verdict(r):
        """算相关性 + 引流页判定，顺手记一条人话日志。"""
        rel = relevance_ratio(query, r["items"]) if r["items"] else 0.0
        r["rel"] = round(rel, 2)
        decoy = looks_decoy(r["items"])
        if r["items"]:
            warnings.append("%s: %d 条但相关性 %.0f%%%s"
                            % (r["engine"], len(r["items"]), rel * 100,
                               "（疑似引流页）" if decoy else ""))
        else:
            warnings.append("%s: 0 条（%s）" % (r["engine"], (r.get("err") or "空/反爬")[:70]))
        return rel, decoy

    def by_domain(r):
        """domain 过滤：有匹配就只留匹配的，一条都没有就当这个引擎没交卷。"""
        if not domain or not r["items"]:
            return True
        keep = [it for it in r["items"] if domain in (it.get("link") or "").lower()]
        if keep:
            r["items"] = keep
            return True
        warnings.append("%s: %d 条里没有 %s 的结果" % (r["engine"], len(r["items"]), domain))
        r["items"] = []
        return False

    def done(r, degraded_reason=None):
        r["engines_tried"] = tried
        r["elapsed_ms"] = int((time.time() - t_start) * 1000)
        r["proxy"] = proxy_url
        if degraded_reason:
            r["warning"] = degraded_reason
        return r

    for engine in chain:
        if time.time() - t_start > timeout:
            warnings.append("超时预算用尽（%.0fs）" % timeout)
            break
        tried.append(engine)
        r = search_http(engine, query, proxy=proxy_url, max_results=max_results)
        rel, decoy = verdict(r)
        if by_domain(r) and r["items"] and rel >= gate and not decoy:
            resolve_items(r["items"], proxy=proxy_url, limit=max_results, referer=r.get("url"))
            return done(r)
        if rel > best_score and r["items"]:
            best, best_score = r, rel

    if allow_browser:
        with BrowserFallback(proxy=proxy_url) as bf:
            for engine in browser_chain:
                if time.time() - t_start > timeout + 15:      # 浏览器一次给足，但别无限拖
                    warnings.append("浏览器兜底超时预算用尽")
                    break
                tried.append(engine + "(br)")
                r = bf.search(engine, query, max_results=max_results)
                rel, decoy = verdict(r)
                if by_domain(r) and r["items"] and rel >= gate and not decoy:
                    resolve_items(r["items"], proxy=proxy_url, limit=max_results,
                                  referer=r.get("url"))
                    r["channel"] = "browser"
                    return done(r)
                if rel > best_score and r["items"]:
                    best, best_score = r, rel

    # 全链都没过闸门：退而求其次返回相关性最高的，并明确告警（degraded 由上层看 warning）
    if best:
        resolve_items(best["items"], proxy=proxy_url, limit=max_results,
                      referer=best.get("url"))
        return done(best, "全部引擎未过相关性闸门，给的是最接近的一版：" + "；".join(warnings))
    return {"engine": (tried[0] if tried else "").replace("(br)", ""),
            "channel": "none", "items": [], "code": 0, "ms": 0,
            "err": "所有引擎均失败：" + "；".join(warnings)
                   + (("；整条链上都没有 %s 的结果，去掉 domain 再试" % domain) if domain else ""),
            "engines_tried": tried,
            "elapsed_ms": int((time.time() - t_start) * 1000), "rel": 0.0,
            "proxy": proxy_url}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="search")
    ap.add_argument("query", nargs="?", default="vllm 0.11 发布")
    ap.add_argument("--chain", default=None)
    ap.add_argument("--browser-chain", default=None)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--gate", type=float, default=0.5)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--proxy", default="auto")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = search(a.query,
               chain=a.chain.split(",") if a.chain else None,
               browser_chain=a.browser_chain.split(",") if a.browser_chain else None,
               max_results=a.max, gate=a.gate, proxy=a.proxy,
               allow_browser=not a.no_browser)
    payload = {"ok": bool(r["items"]), "command": "search", "query": a.query,
               "engine": r["engine"], "channel": r.get("channel"),
               "engines_tried": r.get("engines_tried"), "rel": r.get("rel"),
               "elapsed_ms": r.get("elapsed_ms"), "proxy": r.get("proxy"),
               "count": len(r["items"]),
               "results": [dict(it, position=i + 1) for i, it in enumerate(r["items"])],
               "warning": r.get("warning") or (r.get("err") or None)}
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for it in payload["results"]:
            print("%2d. %s\n    %s\n    %s" % (it["position"], it["title"], it["link"],
                                               it["snippet"][:120]))
        print("[%s %s rel=%s %sms tried=%s] %s"
              % (payload["engine"], payload["channel"], payload["rel"], payload["elapsed_ms"],
                 payload["engines_tried"], payload["warning"] or ""))
    return 0 if payload["ok"] else 1


# ---------------------------------------------------------------------------
# read：正文抽取（HTTP 优先，浏览器只做兜底）
# ---------------------------------------------------------------------------

READ_BLOCK_SCHEMES = ("javascript:", "data:", "javascript", "about:")
_MIN_TEXT = 400          # 少于这个字数就认为 HTTP 没抓到正文，值得再开浏览器


def norm_url(url):
    url = (url or "").strip().strip("<>\"'")
    if not url:
        return ""
    if url.lower().startswith(READ_BLOCK_SCHEMES):
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url


def page_title(html):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html or "")
    if not m:
        m = re.search(r"(?is)<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)",
                      html or "")
    return _unesc(m.group(1)).strip()[:200] if m else ""


def _unesc(s):
    import html as _html
    return _html.unescape(re.sub(r"\s+", " ", s or ""))


def trafilatura_extract(html, url, fmt="markdown"):
    """装了 trafilatura 就用它（实测正文质量最好），没装返回 (None, 原因)。"""
    try:
        import trafilatura
    except ImportError:
        return None, "no trafilatura"
    names = ("markdown", "md", "txt") if fmt == "markdown" else ("txt", "text")
    last = "empty"
    for name in names:
        for kwargs in ({"url": url, "output_format": name, "include_links": fmt == "markdown",
                        "include_tables": True, "favor_recall": True},
                       {"url": url}):
            try:
                out = trafilatura.extract(html, **kwargs)
                if out and out.strip():
                    return out.strip(), "trafilatura:%s" % name
            except TypeError as exc:          # 版本差异：参数不认识，退一档再试
                last = str(exc)[:60]
            except Exception as exc:
                last = str(exc)[:60]
    return None, last


_TAG_RE = re.compile(r"(?is)<(script|style|noscript|svg|nav|footer|header|form)[^>]*>.*?</\1>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")


def fallback_text(html, url=""):
    """没 trafilatura / trafilatura 吃不下时的兜底：优先 <article>/<main> 块，正则剥标签。"""
    body = html or ""
    for tag in ("article", "main"):
        m = re.search(r"(?is)<%s[^>]*>(.*?)</%s>" % (tag, tag), body)
        if m and len(m.group(1)) > 500:
            body = m.group(1)
            break
    body = _TAG_RE.sub(" ", body)
    body = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", body)
    text = _unesc(_ANY_TAG.sub(" ", body))
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in text.splitlines()]
    out, prev = [], None
    for ln in lines:                      # 去重相邻重复行（SPA 骨架常见）
        if ln and ln != prev:
            out.append(ln)
            prev = ln
    return "\n".join(out)


def extract_text(html, url, fmt="markdown"):
    text, how = trafilatura_extract(html, url, fmt)
    if not text:
        text, how = fallback_text(html, url), "heuristic"
    return text or "", how


def read_url(url, max_chars=8000, fmt="markdown", wait_selector=None, scroll=False,
             timeout_ms=15000, proxy="auto", allow_browser=True, browser=None):
    """抓一个 URL 的正文。HTTP（trafilatura）先上，拿不动再开浏览器。"""
    t0 = time.time()
    url = norm_url(url)
    if not url:
        return {"ok": False, "url": url, "err": "不是合法的 http(s) URL", "text": "", "ms": 0}
    proxy_url = detect_proxy() if proxy == "auto" else (proxy or None)
    backend, warning, html, code = "", 0, "", 0

    html, code, ms_http, err = http_get(url, proxy=proxy_url, timeout=max(4, timeout_ms // 1000))
    text, how = extract_text(html, url, fmt) if html else ("", "none")
    backend = "http+%s" % how
    # 404/410/451 是"确定没有这页"，开浏览器也变不出正文，别白等 4 秒
    dead_end = code in (404, 410, 451)
    if len(text) < _MIN_TEXT and allow_browser and not dead_end:
        # 正文太短：要么是 JS 渲染，要么被反爬（412/403/验证页）——交给浏览器
        bf = browser or BrowserFallback(proxy=proxy_url)
        try:
            if browser is None:
                bf.__enter__()
            bhtml = bf.fetch_html(url, nav_timeout=timeout_ms,
                                  wait_selector=wait_selector, scroll=scroll)
            if len(bhtml or "") > len(html or ""):
                btext, bhow = extract_text(bhtml, url, fmt)
                if len(btext) > len(text):
                    text, backend = btext, "browser+%s" % bhow
                    html = bhtml
        except Exception as exc:
            warning = "浏览器兜底失败：%s" % str(exc)[:100]
        finally:
            if browser is None:
                bf.close()
    if len(text) < _MIN_TEXT:
        # 短到这份上基本不是正文：404 页、JS 壳子、或登录墙，明确告诉调用方
        warning = (warning + "；" if warning else "") + \
            "正文只有 %d 字（HTTP %s），大概是不存在的页面 / JS 页 / 要登录" % (len(text), code or err)
    if dead_end or len(text) < 24:
        # 404/410/451，或者正文短到只有十几个字（网关错误页）：直说，别让模型以为读到了
        return {"ok": False, "url": url, "code": code,
                "err": "%s页面只有 %d 字（HTTP %s），读到的是「%s」"
                       % ((warning + "；") if warning else "", len(text), code or err,
                          text.strip()[:40]),
                "text": text[:200], "chars": len(text),
                "ms": int((time.time() - t0) * 1000), "backend": backend}
    if not text:
        return {"ok": False, "url": url, "code": code, "err": warning or "没抽到正文（HTTP %s）" % code,
                "text": "", "ms": int((time.time() - t0) * 1000), "backend": backend}
    title = page_title(html)
    total = len(text)
    truncated = total > max_chars
    if truncated:
        text = text[:max_chars]
    return {"ok": True, "url": url, "code": code or 200, "title": title, "text": text,
            "chars": total, "returned": len(text), "truncated": truncated,
            "backend": backend, "ms": int((time.time() - t0) * 1000),
            "warning": warning or None}


# ---------------------------------------------------------------------------
# 可选：自建 SearXNG 端点（P3）。没有也不影响，配了就插到引擎链最前面。
# ---------------------------------------------------------------------------

def add_searxng(base_url):
    """把自建 SearXNG 注册成一个引擎（JSON API：/search?q=..&format=json）。"""
    base = (base_url or "").rstrip("/")
    if not base.startswith("http"):
        return False

    def _parse(body, query):
        import json as _json
        try:
            data = _json.loads(body)
        except Exception:
            return []
        out = []
        for r in (data.get("results") or [])[:20]:
            link = r.get("url") or r.get("link") or ""
            title = _unesc(r.get("title") or "")
            if not link.startswith("http") or not title:
                continue
            out.append({"title": title[:200], "link": link,
                        "snippet": _unesc(r.get("content") or "")[:240],
                        "source": r.get("parsed_url", [""])[0] if isinstance(r.get("parsed_url"), list)
                        else urllib.parse.urlparse(link).netloc})
        return out

    HTTP_ENGINES["searxng"] = (base + "/search?q={q}&format=json", _parse, True)
    return True


# ---------------------------------------------------------------------------
# multi：一个进程里连查多个关键词（省得每次重开解释器 / 浏览器）
# ---------------------------------------------------------------------------

def search_multi(queries, **kwargs):
    gap = kwargs.pop("gap", 1.2)
    results = []
    bf = None
    try:
        for i, q in enumerate(queries):
            if i and gap:
                time.sleep(gap)
            results.append(dict(search(q, **kwargs), query=q))
    finally:
        if bf is not None:
            bf.close()
    return results


if __name__ == "__main__":
    sys.exit(main())
