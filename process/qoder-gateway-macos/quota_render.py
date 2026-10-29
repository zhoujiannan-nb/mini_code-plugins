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

结论：sandbox 里只能显示**静态**内容。所以额度面板由启动器定时把数据渲染成静态 HTML，
落成插件目录里的 `quota.html`；宿主每次打开页面都重新拉（Cache-Control: no-store），
因此"打开/刷新页面"就是刷新额度。想要更勤的更新，见 README 里的"手动刷新"。

本模块只做纯函数转换，不碰网络也不写盘，方便单测。
"""
import html
import time

# 宿主给 slot 片段的 CSP 是 default-src 'none'，所以这里只用内联样式与文字。
# 颜色取 mini_code 深色主题的观感：半透明深底 + 细边 + 白字。
CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:transparent;
  font:12px/1.35 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  color:#e8e8ea;-webkit-font-smoothing:antialiased}
.wrap{display:flex;justify-content:flex-end;padding:10px 12px}
.card{display:inline-flex;flex-direction:column;gap:5px;min-width:196px;
  padding:8px 11px 9px;border-radius:12px;
  background:rgba(22,22,26,.86);border:1px solid rgba(255,255,255,.13);
  box-shadow:0 3px 14px rgba(0,0,0,.36)}
.row{display:flex;align-items:center;gap:6px;justify-content:space-between}
.title{display:flex;align-items:center;gap:6px;font-weight:600;letter-spacing:.2px}
.dot{width:7px;height:7px;border-radius:50%;flex:0 0 auto;
  background:#3ad07d;box-shadow:0 0 0 2px rgba(58,208,125,.16)}
.dot.warn{background:#f0b429;box-shadow:0 0 0 2px rgba(240,180,41,.16)}
.dot.bad{background:#ef5350;box-shadow:0 0 0 2px rgba(239,83,80,.16)}
.dot.off{background:#8b8b93;box-shadow:0 0 0 2px rgba(139,139,147,.16)}
.big{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.unit{font-size:11px;font-weight:500;color:#9aa0a6;margin-left:2px}
.sub{color:#9aa0a6;font-variant-numeric:tabular-nums}
.bar{position:relative;height:4px;border-radius:999px;background:rgba(255,255,255,.12);
  overflow:hidden}
.bar>i{position:absolute;inset:0 auto 0 0;border-radius:999px;background:#3ad07d}
.bar>i.warn{background:#f0b429}
.bar>i.bad{background:#ef5350}
.muted{color:#7c8288;font-size:11px}
"""


def _esc(x):
    return html.escape("" if x is None else str(x), quote=True)


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


def render_card(usage, gateway_ok=True, now=None, max_age_seconds=60):
    """渲染右上角那枚额度徽标（slot=overlay）。

    usage: GET /qoder/usage 的 JSON；None 表示拿不到。
    now:   渲染时刻（time.time()），用于"多久以前"。
    """
    now = time.time() if now is None else now
    text, cls = state_of(usage, gateway_ok)
    if not usage:
        body = ('<div class="wrap"><div class="card">'
                '<div class="row"><span class="title"><span class="dot %s"></span>Qoder</span>'
                '<span class="muted">%s</span></div>'
                '<div class="muted">%s</div></div></div>'
                % (_esc(cls), _esc(text),
                   "先放 PAT 到 ~/.qoder-api/pat.txt" if gateway_ok else "在插件中心启动它"))
        return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<style>%s</style></head><body>%s</body></html>' % (CSS, body))

    acct = usage.get("account") or {}
    uq = acct.get("user_quota") or {}
    addon = acct.get("addon_quota") or {}
    proc = usage.get("process") or {}

    total = uq.get("total")
    used = uq.get("used")
    remain = uq.get("remaining")
    unit = _esc(uq.get("unit") or "credits")
    used_pct = _pct(used, total)

    aria = "Qoder 剩余 %s %s，共 %s，已用 %s" % (_num(remain), unit, _num(total), _num(used))
    # 徽标要塞进 iframe 的固定高度（plugin.json 的 ui.slots[].height），所以只放四行：
    # 标题+状态 / 剩余额度 / 进度条 / 已用。附加包、token、缓存命中这些都在完整额度页里。
    body = (
        '<div class="wrap"><div class="card" role="status" aria-label="%s">'
        '<div class="row"><span class="title"><span class="dot %s"></span>Qoder 额度</span>'
        '<span class="muted">%s</span></div>'
        '<div class="row"><span class="big">%s<span class="unit">%s</span></span>'
        '<span class="sub">/ %s</span></div>'
        '<div class="bar"><i class="%s" style="width:%.1f%%"></i></div>'
        '<div class="row sub"><span>已用 %s</span><span>%.1f%%</span></div>'
        '</div></div>'
        % (_esc(aria), _esc(cls), _esc(text),
           _num(remain), unit, _num(total),
           _esc(cls), used_pct,
           _num(used), used_pct)
    )
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<style>%s</style></head><body>%s</body></html>' % (CSS, body))


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
            "<title>Qoder 额度</title><style>%s"
            "body{background:#17171b;padding:18px;font-size:13px}"
            "h1{font-size:15px;margin:0 0 10px;display:flex;gap:8px;align-items:center}"
            "table{border-collapse:collapse;min-width:340px}"
            "th{text-align:left;font-weight:500;color:#9aa0a6;padding:5px 14px 5px 0;white-space:nowrap}"
            "td{padding:5px 0;font-variant-numeric:tabular-nums}"
            ".bar{height:5px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden}"
            ".bar>i{display:block;height:100%%;border-radius:999px;background:#3ad07d}"
            ".bar>i.warn{background:#f0b429}.bar>i.bad{background:#ef5350}"
            ".foot{margin-top:14px;color:#7c8288;font-size:11px}"
            "</style></head><body>"
            "<h1><span class=\"dot %s\"></span>Qoder 额度<span class=\"muted\">%s</span></h1>"
            "<table>%s</table>"
            "<div class=\"foot\">数据来自 GET /qoder/usage（本机网关，只监听 127.0.0.1）。"
            "渲染于 %s。<br>这个页面是启动器定时预渲染的静态文件，刷新页面＝重新取一次；"
            "插件中心右上角那枚徽标同理。</div>"
            "</body></html>"
            % (CSS, _esc(cls), _esc(text), trs, _esc(stamp)))
