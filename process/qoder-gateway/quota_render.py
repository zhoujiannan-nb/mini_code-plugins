#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Qoder 的额度数据渲染成宿主插件中心能显示的内容。

为什么要这么绕：插件中心的 process 卡片只显示 state/pid/uptime/endpoint 这几个固定字段，
插件没有权限往里塞自己的数据。宿主唯一开放的"演示文稿"位置是 `ui.slots` —— 一段
**无脚本、跨源隔离**的 <iframe>（裸 sandbox，连 allow-scripts 都没有）。

在这个沙箱里（已用 Chromium 151 实测，见 _work_20261028_quota_slot/refresh_matrix.py）：
  * 内联 <style> 正常生效          -> 能做卡片外观
  * 中文正常渲染                    -> 能直接写"剩余额度"
  * <meta http-equiv="refresh"> **不触发**（无 allow-scripts 的沙箱里被禁用）
  * 同源 <img> / <link> **发不出请求**（'self' 在 opaque origin 下不匹配）

结论：sandbox 里只能显示**静态**内容，做不了"实时刷新"的浮层。所以最终方案不是往
UI 上浮东西，而是把用量写成**插件自己卡片的描述**：`summary_line()` 返回一行摘要，
启动器每 60 秒把它写进已安装那份 plugin.json 的 description 首行（宿主会实时重读）。
`render_page()` 另外生成一份 quota.html，给人用浏览器看明细。

本模块只做纯函数转换，不碰网络也不写盘，方便单测。
"""
import html
import time



def _esc(x):
    return html.escape("" if x is None else str(x), quote=True)


# 明细页自己的样式（这份页面是给人用浏览器打开的，不在 sandbox 里，所以随便写）。
PAGE_CSS = """
*{box-sizing:border-box}
body{margin:0;padding:18px;background:#17171b;color:#e8e8ea;
  font:13px/1.45 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
h1{font-size:15px;margin:0 0 12px;display:flex;gap:8px;align-items:center}
table{border-collapse:collapse;min-width:340px}
th{text-align:left;font-weight:500;color:#9aa0a6;padding:5px 16px 5px 0;white-space:nowrap}
td{padding:5px 0;font-variant-numeric:tabular-nums}
.big{font-size:16px;font-weight:700}
.unit{font-size:11px;color:#9aa0a6;margin-left:2px}
.muted{color:#9aa0a6}
.dot{width:7px;height:7px;border-radius:50%;background:#3ad07d;flex:0 0 auto}
.dot.warn{background:#f0b429}
.dot.bad{background:#ef5350}
.dot.off{background:#8b8b93}
.bar{display:block;width:220px;height:5px;border-radius:999px;
  background:rgba(255,255,255,.12);overflow:hidden}
.bar>i{display:block;height:100%;border-radius:999px;background:#3ad07d}
.bar>i.warn{background:#f0b429}
.bar>i.bad{background:#ef5350}
.foot{margin-top:14px;color:#7c8288;font-size:11px;line-height:1.6}
"""


def _num(v):
    """额度数字：整数就不带小数点，别的保留两位；None 变成空串。"""
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return "{:,}".format(int(f))
    return "{:,.2f}".format(f)


def _pct(used, total):
    try:
        t = float(total)
        if t <= 0:
            return 0.0
        return max(0.0, min(100.0, float(used) / t * 100.0))
    except (TypeError, ValueError):
        return 0.0


def state_of(usage, gateway_ok=True):
    """返回 (状态文字, 状态类名)。类名对应 CSS 里的 dot/bar 修饰。"""
    if not gateway_ok:
        return "网关未运行", "off"
    if not usage:
        return "暂无额度数据", "off"
    acct = usage.get("account") or {}
    if acct.get("quota_exceeded"):
        return "额度已用尽", "bad"
    uq = acct.get("user_quota") or {}
    used_pct = _pct(uq.get("used"), uq.get("total"))
    if used_pct >= 90:
        return "额度告急", "bad"
    if used_pct >= 70:
        return "额度偏低", "warn"
    return "正常", ""


def _plain(x, limit=40):
    """把可能来自上游的字符串变成安全的单行纯文本（摘要会写进 plugin.json）。"""
    s = "" if x is None else str(x)
    s = s.replace("<", "").replace(">", "").replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    return s[:limit]


def summary_line(usage, gateway_ok=True):
    """给插件卡片用的**一行**用量摘要（写在已装 plugin.json 的 description 首行）。

    插件中心那张卡只显示 manifest 的 description，没有别的动态字段；宿主会实时重读
    plugin.json，所以启动器把这一行写到已安装的那份 description 里，就能"在插件自己
    这里看到用量"，而不是往全局 UI 上浮一个遮罩。
    """
    text, _cls = state_of(usage, gateway_ok)
    if not usage:
        return ("额度：网关未运行" if not gateway_ok else "额度：暂无数据（检查 ~/.qoder-api/pat.txt）")
    acct = usage.get("account") or {}
    uq = acct.get("user_quota") or {}
    unit = _plain(uq.get("unit") or "credits", 12)
    pct = _pct(uq.get("used"), uq.get("total"))
    line = "额度 %s / %s %s（已用 %s，%.0f%%）· %s" % (
        _num(uq.get("remaining")), _num(uq.get("total")), unit, _num(uq.get("used")), pct, text)
    addon = acct.get("addon_quota") or {}
    try:
        if float(addon.get("total") or 0) > 0 and addon.get("remaining"):
            line += " · 附加包 %s/%s" % (_num(addon.get("remaining")), _num(addon.get("total")))
    except (TypeError, ValueError):
        pass
    if acct.get("tag") or acct.get("plan"):
        line += " · %s" % _plain(acct.get("tag") or acct.get("plan"), 24)
    return line


def render_page(usage, gateway_ok=True, now=None, detail=True):
    """渲染"完整额度页"（在浏览器里直接打开 quota.html 时看到的那份）。

    比徽标多：套餐/到期时间/账号、本进程 token 与缓存命中、刷新方式说明。
    """
    now = time.time() if now is None else now
    text, cls = state_of(usage, gateway_ok)
    rows = []
    acct = (usage or {}).get("account") or {}
    uq = acct.get("user_quota") or {}
    proc = (usage or {}).get("process") or {}

    if usage:
        used_pct = _pct(uq.get("used"), uq.get("total"))
        rows.append(("剩余", '<span class="big">%s<span class="unit">%s</span></span> / %s'
                     % (_num(uq.get("remaining")), _esc(uq.get("unit") or "credits"), _num(uq.get("total")))))
        rows.append(("已用", "%s（%.1f%%）" % (_num(uq.get("used")), used_pct)))
        rows.append(("进度", '<span class="bar" style="display:block;width:220px">'
                             '<i class="%s" style="width:%.1f%%"></i></span>' % (_esc(cls), used_pct)))
        addon = acct.get("addon_quota") or {}
        try:
            if float(addon.get("total") or 0) > 0:
                rows.append(("附加包", "%s / %s %s"
                             % (_num(addon.get("remaining")), _num(addon.get("total")),
                                _esc(addon.get("unit") or uq.get("unit") or "credits"))))
        except (TypeError, ValueError):
            pass
        if acct.get("plan") or acct.get("tag"):
            rows.append(("套餐", "%s%s" % (_esc(acct.get("tag") or ""), " · " + _esc(acct.get("plan")) if acct.get("plan") else "")))
        if acct.get("org"):
            rows.append(("组织", _esc(acct.get("org"))))
        if acct.get("org_package") and acct["org_package"].get("available"):
            op = acct["org_package"]
            rows.append(("团队池", "%s / %s" % (_num(op.get("remaining")), _num(op.get("cap")))))
        if acct.get("next_reset_at_ms"):
            try:
                ts = float(acct["next_reset_at_ms"]) / 1000.0
                rows.append(("重置", _esc(time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)))))
            except (TypeError, ValueError):
                pass
        if detail:
            rows.append(("本机请求", "%s 次（成功 %s / 失败 %s）"
                         % (_num(proc.get("requests")), _num(proc.get("ok")), _num(proc.get("failed")))))
            rows.append(("本机 token", "prompt %s · completion %s · reasoning %s"
                         % (_num(proc.get("prompt_tokens")), _num(proc.get("completion_tokens")),
                            _num(proc.get("reasoning_tokens")))))
            cached = proc.get("cached_tokens") or 0
            ptok = proc.get("prompt_tokens") or 0
            hit = (float(cached) / float(ptok) * 100.0) if ptok else 0.0
            rows.append(("前缀缓存", "%s / %s（%.1f%% 命中）" % (_num(cached), _num(ptok), hit)))
            rows.append(("本机花费", "%s credits" % _num(proc.get("credits_spent"))))

    trs = "".join('<tr><th>%s</th><td>%s</td></tr>' % (k, v) for k, v in rows)
    if not rows:
        trs = ('<tr><td class="muted">%s</td></tr>'
               % ("网关没运行，先到插件中心启动 qoder-gateway。"
                  if not gateway_ok else
                  "拿不到额度数据：确认 ~/.qoder-api/pat.txt 里有有效的 PAT。"))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>Qoder 额度</title><style>%s</style></head><body>"
            "<h1><span class=\"dot %s\"></span>Qoder 额度<span class=\"muted\">%s</span></h1>"
            "<table>%s</table>"
            "<div class=\"foot\">数据来自 GET /qoder/usage（本机网关，只监听 127.0.0.1）。"
            "渲染于 %s。<br>这个页面是启动器定时预渲染的静态文件，重新打开＝重新取一次；"
            "插件卡片描述第一行那串用量是同一份数据。</div>"
            "</body></html>"
            % (PAGE_CSS, _esc(cls), _esc(text), trs, _esc(stamp)))
