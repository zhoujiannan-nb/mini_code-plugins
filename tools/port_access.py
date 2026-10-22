#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 dsh-startup-screen(MIT)的启动动画移植成 mini_code 开机动画主题。

来源:https://github.com/LeeRolling/dsh-startup-screen  (MIT, Copyright (c) 2026 LeeRolling)
用法:
    git clone https://github.com/LeeRolling/dsh-startup-screen  <某处>
    python tools/port_access.py --src <某处>

脚本是"可复现移植":逐条打补丁,任何一条匹配不上就直接失败退出,不产生半成品。
品牌文案换成 Mini Code,素材(真声播报 + 咔哒音效)原样搬进主题目录,
并按宿主的通信协议补上 ready / step / handoff / done。

宿主给主题的约束(CSP connect-src 'none'),所以素材加载不能用 fetch,
必须换成 <audio> 元素 —— 这是移植里唯一一处真正的重写。
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "boot-anim", "mc-access")

# 需要一起搬走的真素材(上游仓库里就带着,MIT 仓库随包分发)
ASSETS = ["line-1.mp3", "line-2.mp3", "line-3.mp3", "line-4.mp3",
          "line-5.mp3", "line-6.mp3", "sfx-tick.mp3", "sfx-ticks-run.mp3"]

BANNER = """/* ============================================================================
 * 接入序列 —— mini_code 开机动画主题 (boot-anim/mc-access)
 * ----------------------------------------------------------------------------
 * 移植自 dsh-startup-screen v0.x(MIT, Copyright (c) 2026 LeeRolling,
 * https://github.com/LeeRolling/dsh-startup-screen):画面、节奏、真声播报与
 * 音效都来自那个项目,这里只做三件事 ——
 *   1. 品牌全部换成 Mini Code(鲸鱼标识换成"芯片 + >"镂空标识,文案重写);
 *   2. 对接 mini_code 宿主的开机动画协议(ready / step / handoff / done,见
 *      插件仓库 docs/theme-contract.md),跳过按钮归宿主,主题不再自画;
 *   3. 素材加载从 fetch + decodeAudioData 改成 <audio> 元素:宿主以
 *      CSP connect-src 'none' 提供主题文件,fetch 一定被拦。
 * 上游 MIT 原文见插件仓库根目录 LICENSE-DSH。
 * 所有改动都带 "mini_code 补丁" 注释,由 tools/port_access.py 生成,勿手改。
 * ========================================================================== */
"""

# 音频模块:对外 API 与上游一致(loadAsset / ensureAsset / playAsset / playAssetAndWait)
AUDIO_IMPL = """    /* mini_code 补丁:素材改用 <audio> 元素播放(见文件头的 CSP 说明),
       路径就是主题目录下的同名 mp3。对外 API 与上游保持一致。 */
    var clips = {}   /* name -> {el, dur, state}  state: 0=加载中 1=就绪 -1=失败 */
    function clip(name) {
      var rec = clips[name]
      if (rec) return rec
      rec = { el: null, dur: 0, state: 0 }
      clips[name] = rec
      try {
        var a = new Audio(encodeURIComponent(name) + '.mp3')
        a.preload = 'auto'
        a.addEventListener('loadedmetadata', function () {
          var d = Number(a.duration)
          rec.dur = isFinite(d) && d > 0 ? Math.round(d * 1000) : 0
          rec.state = rec.dur > 0 ? 1 : -1
        })
        a.addEventListener('error', function () { rec.state = -1 })
        rec.el = a
        a.load()
      } catch (e) { rec.state = -1 }
      return rec
    }
    function loadAsset(name) { if (C.sound) clip(name) }

    /* 素材就绪与否:等 metadata 到手,最多 1.5s。静默(mute)时直接判不可用,
       这样连一个字节的音频都不会去下载。 */
    function ensureAsset(name) {
      if (!C.voice || C.voiceSource === 'tts') return Promise.resolve(false)
      var rec = clip(name)
      if (rec.state === 1) return Promise.resolve(true)
      if (rec.state === -1) return Promise.resolve(false)
      return new Promise(function (resolve) {
        var t0 = Date.now()
        ;(function poll() {
          if (rec.state === 1) return resolve(true)
          if (rec.state === -1 || Date.now() - t0 > 1500) return resolve(false)
          setTimeout(poll, 40)
        })()
      })
    }

    /** 播素材并等它播完,resolve 实际时长(ms)。被自动播放策略拦下时按素材
     *  时长照常返回 —— 画面节奏不能因为没有声音就变快。 */
    /* mini_code 补丁:每条真声素材的头尾死空气(拿 Web Audio 逐 40ms 窗量出来的,
       阈值 -38dBFS,见插件仓库 README「音频素材」)。跳过死空气既省时间也更紧凑,
       没在表里的文件照原样播。数值来源:line-N.mp3 的语音起止 =
       1:480~1960  2:0~1360  3:0~1320  4:0~1080  5:0~2720  6:1000~3480
       line-6 另有一处**内容裁剪**:原句是「Welcome to DeepSeek Harness」,按 20ms 窗
       量出音节边界 [1000~1220][1240~1600] = "Wel" "come",随后 800ms 停顿才是后半句,
       所以在 1700ms 处收 —— 只留一声 "Welcome",既对上画面(屏幕上写的就是
       WELCOME TO / MINI CODE),也把上游那句别人家的品牌名从声音里去掉。 */
    var TRIMS = {
      'line-1': [400, 2120],
      'line-2': [0, 1520],
      'line-6': [920, 1700]
    }

    function playAssetAndWait(name, gain) {
      return new Promise(function (resolve) {
        var rec = clips[name] || clip(name)
        if (rec.state !== 1) { resolve(0); return }
        var a = rec.el, settled = false
        var trim = TRIMS[name] || null
        var from = trim ? Math.max(0, Math.min(trim[0], rec.dur - 120)) : 0
        var until = trim ? Math.min(Math.max(from + 120, trim[1]), rec.dur) : rec.dur
        var span = Math.max(0, until - from)
        function settle() {
          if (settled) return
          settled = true
          try { a.onended = null; a.onerror = null } catch (e) {}
          resolve(span)
        }
        a.onended = settle
        a.onerror = settle
        try {
          a.volume = Math.min(1, Math.max(0, (gain == null ? 0.92 : gain) * clamp01(C.voiceVolume, 0, 1)))
          if (from > 0) a.currentTime = from / 1000
          var p = a.play()
          if (p && typeof p['catch'] === 'function') p['catch'](function () {})
        } catch (e) { settle() }
        /* 削掉尾部的死空气:到点自己停,别等 onended(那才是文件真正结束) */
        setTimeout(function () {
          if (settled) return
          try { a.pause() } catch (e2) {}
          settle()
        }, span + 80)
        setTimeout(settle, span + 900)
      })
    }

    function playAsset(name, gain) {
      if (!C.sound) return false
      var rec = clip(name)
      if (rec.state !== 1) return false
      try {
        var a = rec.el
        a.volume = Math.min(1, Math.max(0, (gain == null ? 0.55 : gain) * clamp01(C.soundVolume, 0, 1) * 2))
        a.currentTime = 0
        var p = a.play()
        if (p && typeof p['catch'] === 'function') p['catch'](function () {})
        return true
      } catch (e) { return false }
    }
"""

BRIDGE = """
  /* ── mini_code 补丁:宿主通信 + query 配置 ─────────────────────────────
     协议见插件仓库 docs/theme-contract.md:
       parent.postMessage({mc:"boot-anim", type:"ready|step|handoff|done", id}, "*")
     ready   首帧已经画出来了(宿主这时才显示跳过按钮)
     handoff 开始交还界面(必须发生在淡出那一帧,宿主此刻叠化)
     done    收尾。跳过按钮归宿主画,主题自己不画(所以下面 allowSkip=false) */
  var Q = (function () {
    var out = {}
    try {
      var rawq = String(location.search || '').replace(/^\\?/, '')
      if (!rawq) return out
      var parts = rawq.split('&')
      for (var i = 0; i < parts.length; i++) {
        if (!parts[i]) continue
        var kv = parts[i].split('=')
        var k = decodeURIComponent(kv[0].replace(/\\+/g, ' '))
        var v = kv.length > 1 ? decodeURIComponent(kv.slice(1).join('=').replace(/\\+/g, ' ')) : ''
        out[k] = v
      }
    } catch (e) { /* 参数烂掉就用默认值,绝不影响动画 */ }
    return out
  })()

  var MC = (function () {
    var handed = false
    function post(type, extra) {
      var msg = { mc: 'boot-anim', type: type, id: 'mc-access' }
      if (extra) for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) msg[k] = extra[k]
      try { (window.parent || window).postMessage(msg, '*') } catch (e) {}
    }
    function handoff() { if (handed) return; handed = true; post('handoff') }
    return {
      post: post,
      ready: function () { post('ready') },
      step: function (n, total, label, progress) { post('step', { step: n, total: total, label: label, progress: progress }) },
      handoff: handoff,
      done: function () { handoff(); post('done') }
    }
  })()

  /** 字母间距拉开的品牌小字排版(上游写死 'D E E P S E E K',这里跟着配置生成) */
  function spaced(t) {
    var words = String(t || '').replace(/\\s+/g, ' ').replace(/^ | $/g, '').split(' ')
    var out = []
    for (var i = 0; i < words.length; i++) out.push(words[i].split('').join('\\u00a0'))
    return out.join('\\u00a0\\u00a0')
  }
"""

MARK = """  /* ── mini_code 标识:六边形芯片,中间镂空一个 ">"(终端提示符) ─────────
     上游是 DeepSeek 的鲸鱼路径,品牌换成 Mini Code 后不能沿用别人的商标,
     所以这里换一枚同量级的几何标识:第二条子路径靠 evenodd 变成镂空箭头,
     "一笔画成"的描边动画照旧可用。 */
  var MARK_PATH =
    'M25 3 L45 14 L45 36 L25 47 L5 36 L5 14 Z ' +
    'M30 16 L36 25 L30 34 L25.2 34 L30.8 25 L25.2 16 Z'
"""

QUERY_CFG = """    /* mini_code 补丁:宿主的开机动画只通过 query 传参
       (?speed=&interactive=&mute=&name= + theme.json options 里声明的键)。
       只认 DEFAULTS 里出现过的配置项,按默认值的类型转换,其余键一律忽略。 */
    var ALIAS = {
      brand: 'brand1', slogan: 'brand2', tagline: 'brand3a',
      org: 'orgEn', orgzh: 'orgZh', orgsub: 'orgSub',
      welcome: 'welcomeBox', footer: 'footer',
      require_interaction: 'requireInteraction', interaction: 'requireInteraction',
      identityid: 'identityId', accesslevel: 'accessLevel',
      glitcha: 'glitchA', glitchb: 'glitchB'
    }
    for (var qk in Q) {
      if (!Object.prototype.hasOwnProperty.call(Q, qk)) continue
      var lk = String(qk).toLowerCase()
      var ck = Object.prototype.hasOwnProperty.call(ALIAS, lk) ? ALIAS[lk] : lk
      if (!Object.prototype.hasOwnProperty.call(DEFAULTS, ck)) continue
      var dv = DEFAULTS[ck], qv = Q[qk]
      if (typeof dv === 'boolean') raw[ck] = (qv === '1' || qv === 'true' || qv === '')
      else if (typeof dv === 'number') { var nv = Number(qv); if (isFinite(nv)) raw[ck] = nv }
      else raw[ck] = String(qv)
    }
    if (Q.name) raw.identity = String(Q.name).slice(0, 48)
    /* 宿主设置页勾了「静默」:语音和音效都关掉,而且一个音频字节都不去拉 */
    if (Q.mute === '1' || Q.mute === 'true') { raw.voice = false; raw.sound = false }
"""

CSS_TAIL = """
/* ==========================================================================
 * mini_code 主题补丁
 * 主题被宿主放进一个全屏 iframe 里,iframe 自己就是整块画布:
 *   - html/body 去掉默认 8px 边距、铺黑底(白底会在首帧闪一下)
 *   - 宿主的滚动锁在宿主那一层做,这里不再动 overflow
 * ========================================================================== */
html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}
"""

INDEX_HTML = """<!doctype html>
<!--
  接入序列 —— mini_code 开机动画主题(画面移植自 dsh-startup-screen,MIT,© LeeRolling,
  上游授权原文见插件仓库根目录 LICENSE-DSH;品牌与标识已换成 Mini Code)。
  由 tools/port_access.py 生成,素材来源见插件仓库 README「致谢与来源」。
-->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>接入序列 · Mini Code</title>
<link rel="stylesheet" href="boot.css">
</head>
<body>
<script src="boot.js"></script>
</body>
</html>
"""


def patch(s, label, old, new, count=1, regex=False, flags=0):
    """打一条补丁;匹配数不对就直接失败,避免生成半成品。"""
    if regex:
        out, n = re.subn(old, new, s, count=count + 1, flags=flags)
    else:
        n = s.count(old)
        out = s.replace(old, new) if n else s
    if n != count:
        sys.exit("[FAIL] 补丁 %s 匹配 %d 次(期望 %d): %r" % (label, n, count, old[:70]))
    return out


def js_patches(src):
    s = src

    # ── 文件头加移植说明(原版权注释保留在下面,署名照旧)────────────────
    s = BANNER + s

    # ── 桥 + query 配置 + spaced():插在 ROOT_ID 之后 ────────────────────
    s = patch(s, "bridge", "  var ROOT_ID = 'dsh-startup-root'\n",
              "  var ROOT_ID = 'dsh-startup-root'\n" + BRIDGE)

    # ── 配置默认值:品牌换 Mini Code、跳过按钮交还给宿主 ──────────────────
    for label, old, new in [
        # 终幕那句「欢迎 X 访问」里的 X。宿主配置里的「身份名」会通过 name= 覆盖它,
        # 这里只是没传名字时的兜底。
        ("identity", "    identity: 'JOYCE MOORE',", "    identity: '\u54c8\u57fa\u7c73\u6307\u6325\u5b98',"),
        ("brand1", "    brand1: 'DEEPSEEK',", "    brand1: 'MINI CODE',"),
        ("brand2", "    brand2: 'SYNTHESIZE INTELLIGENCE',", "    brand2: 'LOCAL AGENT WORKBENCH',"),
        ("brand3a", "    brand3a: 'HARNESS',", "    brand3a: 'AGENT',"),
        ("orgZh", "    orgZh: '深度求索',", "    orgZh: '迷你代码',"),
        ("orgEn", "    orgEn: 'DEEPSEEK',", "    orgEn: 'MINI CODE',"),
        ("orgSub", "    orgSub: 'DEEPSEEK HARNESS',", "    orgSub: 'MINI CODE AGENT',"),
        ("welcomeBox", "    welcomeBox: 'DEEPSEEK HARNESS',", "    welcomeBox: 'MINI CODE',"),
        ("footer", "    footer: 'POWERED BY DEEPSEEK',", "    footer: 'POWERED BY MINI CODE',"),
        ("allowSkip", "    allowSkip: true,", "    allowSkip: false,   /* mini_code 补丁:跳过按钮由宿主统一画 */"),
        # <audio> 的音量上限就是 1(不像 WebAudio 可以再推),默认给满
        ("voiceVolume", "    voiceVolume: 0.9,", "    voiceVolume: 1,"),
    ]:
        s = patch(s, label, old, new)

    # ── query -> 配置 ───────────────────────────────────────────────────
    s = patch(s, "query-cfg",
              "    var out = {}\n"
              "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n",
              "    var out = {}\n"
              "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n"
              + QUERY_CFG)

    # ── 标识:鲸鱼 → 芯片 + ">" 镂空,并把写死的 DEEPSEEK 小字改成配置驱动 ──
    s = patch(s, "mark-path", r"  var WHALE_PATH =[\s\S]*?Z'\n", MARK, regex=True)
    s = patch(s, "mark-usage", "WHALE_PATH", "MARK_PATH", count=1)
    s = patch(s, "fill-rule", "    p.setAttribute('fill-rule', 'nonzero')",
              "    p.setAttribute('fill-rule', 'evenodd')   /* mini_code 补丁:子路径镂空 */")
    s = patch(s, "mark-fn", "  function svgWhale(cls) {", "  function svgMark(cls) {")
    s = patch(s, "mark-calls", "svgWhale(", "svgMark(", count=3)
    s = patch(s, "logo-label",
              "    ui.logo.appendChild(el('div', 'dsu-logolabel', 'D E E P S E E K'))",
              "    ui.logo.appendChild(el('div', 'dsu-logolabel', spaced(C.orgEn)))")
    s = patch(s, "welcome-label",
              "    ui.w3.appendChild(el('span', 'dsu-w3label', 'D E E P S E E K  ·  H A R N E S S'))",
              "    ui.w3.appendChild(el('span', 'dsu-w3label', spaced(C.orgEn) + '  \\u00b7  ' + spaced(C.brand3a)))")
    s = patch(s, "meta1", r"    ui\.meta1\.textContent = 'REV[^']*'",
              u"    ui.meta1.textContent = 'MINI CODE \u00b7 BOOT SEQUENCE'".encode('utf-8').decode('utf-8'), regex=True)

    # ── 素材加载:fetch + decodeAudioData → <audio>(CSP connect-src 'none')─
    s = patch(s, "audio-impl",
              r"    /\* 从 /dsh-startup/asset/[\s\S]*?\n    function playAsset\(name, gain\) \{[\s\S]*?\n    \}\n",
              AUDIO_IMPL, regex=True)
    # 上游 return 表里 confirm 写了两次,后一条把"优先用真素材"的那条覆盖掉了
    s = patch(s, "dup-confirm",
              "      confirm: function () { tone(660, 0.09, 'triangle', 0.07); tone(990, 0.17, 'triangle', 0.055, 0.085) },\n",
              "")
    # 底噪床走的是 ac(true)(无视音效开关),静默时必须能关掉
    s = patch(s, "bed-mute", "        if (bedSrc) return\n", "        if (bedSrc || !C.sound) return   /* mini_code 补丁:静默连底噪一起关 */\n")

    # 语音电平:<audio> 不能再推增益,把原来的 0.85 抬到 0.92(素材峰值约 -13dBFS)
    s = patch(s, "voice-gain", "playAssetAndWait(asset, 0.85)", "playAssetAndWait(asset, 0.92)")

    # ── 不回落 TTS:素材拿不到就静音,绝不现场合成难听的人声 ──────────────
    s = patch(s, "no-tts", r"^(\s*)return ttsLine\(en, zh\)$",
              r"\1return Promise.resolve(0)   /* mini_code 补丁:不回落 TTS,没素材就静音 */",
              count=2, regex=True, flags=re.M)

    # ── 协议挂钩:ready / step / handoff / done ──────────────────────────
    s = patch(s, "ready", "  function run() {\n", "  function run() {\n    MC.ready()   /* mini_code 补丁:首帧交给宿主,可以显示跳过按钮了 */\n")
    s = patch(s, "step", "        setStepCount(n, step.badge)\n",
              "        setStepCount(n, step.badge)\n        MC.step(n, STEPS.length + 1, step.zh, step.progress)   /* mini_code 补丁 */\n")
    s = patch(s, "handoff", "        root.classList.add('dsu-handoff')\n",
              "        root.classList.add('dsu-handoff')\n        MC.handoff()   /* mini_code 补丁:淡出第一帧就交还界面 */\n")
    s = patch(s, "done", "    finished = true\n",
              "    finished = true\n    MC.done()   /* mini_code 补丁:跳过 / 出错 / 播完都从这里交还 */\n")
    # 兜底超时会把还卡在 dsu-boot 的画面直接拆掉,那种情况下也要交还界面
    s = patch(s, "failsafe-notify", "      if (r && r.classList && r.classList.contains('dsu-boot')) {\n",
              "      if (r && r.classList && r.classList.contains('dsu-boot')) {\n        MC.done()   /* mini_code 补丁:卡住了也得把界面还给宿主 */\n")
    s = patch(s, "failsafe-timeout", r"\n  \}, 9000\)\n", "\n  }, 90000)\n", regex=True)

    # ── 不需要用户确认时,别再弹"授予访问权限"按钮(整段自动播完)──────────
    s = patch(s, "action-gate",
              "        if (step.action === 'grant' || step.action === 'confirm') {",
              "        if (C.requireInteraction && (step.action === 'grant' || step.action === 'confirm')) {")

    # ── 重播:iframe 里没有"重新注入脚本"这回事,直接刷新 ─────────────────
    s = patch(s, "replay", r"  function injectSelf\(\) \{[\s\S]*?\n  \}\n",
              "  function injectSelf() { try { location.reload() } catch (e) {} }   /* mini_code 补丁:重播 = 重载 */\n", regex=True)
    return s


def css_patches(src):
    return src + CSS_TAIL


THEME_JSON = {
    "id": "mc-access",
    "name": "接入序列",
    "nameEn": "Access Sequence",
    "author": "zhoujiannan-nb",
    "version": "1.0.1",
    "license": "MIT",
    "entry": "index.html",
    "preview": "preview.svg",
    "description": "最有大片感的一个:黑屏亮起 Mini Code 的标志,一屏一屏走到进软件,中间有个外国女声在念操作提示,最后说一声 Welcome。全程约 18 秒,嫌慢就把速度调快,不想听声音就勾「静默」。",
    "durationMs": 17800,
    "maxMs": 40000,
    "colors": ["light", "dark"],
    "interactive": False,
    "minViewport": 480,
    "tags": ["开机", "电影感", "语音", "音效", "复刻"],
    "options": {
        "speed": 1,
        "theme": "light",
        "accent": "#ff7500",
        "brand": "MINI CODE",
        "slogan": "LOCAL AGENT WORKBENCH",
        "orgzh": "迷你代码",
        "org": "MINI CODE",
        "orgsub": "MINI CODE AGENT",
        "welcome": "MINI CODE",
        "footer": "POWERED BY MINI CODE",
        "require_interaction": 0
    }
}

PREVIEW_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">
  <rect width="320" height="200" fill="#e5e3df"/>
  <g fill="none" stroke="#0a0a0a" stroke-width="1" opacity=".35">
    <path d="M18 18h284v164H18z"/>
  </g>
  <path d="M160 62 L184 76 L184 108 L160 122 L136 108 L136 76 Z" fill="#0a0a0a"/>
  <path d="M166 78 L176 92 L166 106 L161 106 L171 92 L161 78 Z" fill="#e5e3df"/>
  <text x="160" y="146" font-family="Arial Narrow, sans-serif" font-size="13" fill="#0a0a0a" text-anchor="middle" letter-spacing="3">MINI CODE</text>
  <text x="160" y="163" font-family="Consolas, monospace" font-size="8" fill="#7a7873" text-anchor="middle" letter-spacing="1.5">ACCESS SEQUENCE</text>
  <rect x="36" y="176" width="180" height="3" fill="#ff7500"/>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dsh-startup-screen 的本地检出目录")
    a = ap.parse_args()
    lib = os.path.join(a.src, "lib")
    assets_dir = os.path.join(lib, "assets")
    for need in ["splash.js", "splash.css"]:
        if not os.path.isfile(os.path.join(lib, need)):
            sys.exit("[FAIL] 找不到 %s,先 git clone https://github.com/LeeRolling/dsh-startup-screen" % need)
    for m in ASSETS:
        if not os.path.isfile(os.path.join(assets_dir, m)):
            sys.exit("[FAIL] 缺少素材 %s" % m)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    with open(os.path.join(lib, "splash.js"), encoding="utf-8") as f:
        js = js_patches(f.read())
    with open(os.path.join(lib, "splash.css"), encoding="utf-8") as f:
        css = css_patches(f.read())
    with open(os.path.join(OUT, "boot.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)
    with open(os.path.join(OUT, "boot.css"), "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(INDEX_HTML)
    with open(os.path.join(OUT, "theme.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(THEME_JSON, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(OUT, "preview.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PREVIEW_SVG)
    for m in ASSETS:
        shutil.copyfile(os.path.join(assets_dir, m), os.path.join(OUT, m))

    print("[OK] 生成 %s" % OUT)
    for n in sorted(os.listdir(OUT)):
        print("     %-18s %8d B" % (n, os.path.getsize(os.path.join(OUT, n))))


if __name__ == "__main__":
    main()
