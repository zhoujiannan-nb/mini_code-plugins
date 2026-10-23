#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 dsh-startup-secret(MIT)的启动动画移植成 mini_code 开机动画主题。

来源:https://github.com/huzhengcai471-crypto/dsh-startup-secret v1.4.2
      (MIT, Copyright (c) 2026 二次创作作者;它本身又是 dsh-startup-screen 的二次创作)
上游授权原文见插件仓库根目录 LICENSE-DSH-SECRET。
用法:
    python tools/port_secret.py --src <dsh-startup-secret 检出目录>

脚本是"可复现移植":逐条打补丁,任何一条匹配不上就直接失败退出,不产生半成品。
骨架与 tools/port_access.py 一致(patch / ALIAS / AUDIO_IMPL / BRIDGE / CSS_TAIL)。

和"接入序列"的三处本质区别:
  1. 上游把人物立绘 / 徽章 / 事件插画做成了内嵌图片(7 个巨大的 data URI)。
     这些是真人政治人物线稿与第三方标识,一律不打包:徽标换成自绘的
     六边形芯片 MARK,立绘换成自绘的红线「电路猫」内联 SVG,事件窗口整条
     代码路径删掉(动画结束直接交还宿主)。
  2. 上游用浏览器合成音(TTS)兜底 —— 这里永久移除,素材拿不到就安静。
  3. 音频从上游的内嵌 base64 资源包改成 <audio> 元素 + 同目录 mp3
     (宿主 CSP connect-src 'none',fetch 必被拦;media-src 'self' 已放行)。

注意:本脚本 stdout 只打 ASCII(Windows GBK 控制台),细节一律可自查。
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "boot-anim", "mc-secret")

# 需要一起搬走的真素材:5 句英文 + 5 句中文 + 两种咔哒音效。
# line-6*(欢迎语,带别家品牌名)与 jp/kr/ru 三个语种的主题不带。
ASSETS = ["line-1.mp3", "line-2.mp3", "line-3.mp3", "line-4.mp3", "line-5.mp3",
          "line-cn-1.mp3", "line-cn-2.mp3", "line-cn-3.mp3", "line-cn-4.mp3", "line-cn-5.mp3",
          "sfx-tick.mp3", "sfx-ticks-run.mp3"]

BANNER = """/* ============================================================================
 * 机密接入 —— mini_code 开机动画主题 (boot-anim/mc-secret)
 * ----------------------------------------------------------------------------
 * 移植自 dsh-startup-secret v1.4.2(MIT, Copyright (c) 2026 二次创作作者,
 * github.com/huzhengcai471-crypto/dsh-startup-secret;授权原文见插件仓库根目录
 * LICENSE-DSH-SECRET):暗色序列、节奏、真声播报与
 * 音效都来自那个项目,这里只做五件事 ——
 *   1. 品牌全部换成 Mini Code;上游自带的立绘 / 徽章(真人线稿、第三方标识)
 *      一律不打包:徽标换成自绘的"六边形芯片 + >"镂空 MARK,立绘换成自绘的
 *      红线「电路猫」内联 SVG,画面动效(辉光呼吸/色彩呼吸/信号错位)照旧;
 *   2. 删掉「事件窗口」整条路径:动画演完就交还界面,不再停下来等按键;
 *   3. 移除浏览器合成音兜底:素材拿不到就安静地不放,绝不现场合成难听的人声;
 *   4. 对接 mini_code 宿主的开机动画协议(ready / step / handoff / done,见
 *      插件仓库 docs/theme-contract.md),跳过按钮归宿主,主题不再自画;
 *   5. 素材加载改成 <audio> 元素 + 主题目录同名 mp3:宿主以
 *      CSP connect-src 'none' 提供主题文件,fetch 一定被拦。
 * 所有改动都带 "mini_code 补丁" 注释,由 tools/port_secret.py 生成,勿手改。
 * ========================================================================== */
"""

# 音频模块:对外 API 与上游一致(loadAsset / ensureAsset / playAsset / playAssetAndWait)
AUDIO_IMPL = """    /* mini_code 补丁:素材改用 <audio> 元素播放(宿主 CSP connect-src 'none',
       路径就是主题目录下的同名 mp3)。对外 API 与上游保持一致。 */
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

    /* mini_code 补丁:素材头尾若有"死空气"用 TRIMS 描述 [from, until](毫秒)。
       本主题的 10 句素材是上游按音节边界硬切的(见上游 AUDIO-FIELDS.md 的时长表),
       没有可裁的余量,所以表是空的;想再收紧节奏,拿逐 40ms 窗量 RMS 的方法补表。
       不在表里的文件照原样播。 */
    var TRIMS = {}

    /** 播素材并等它播完,resolve 实际时长(ms)。被自动播放策略拦掉时按素材
     *  时长照常返回 —— 画面节奏不能因为没有声音就变快。 */
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
        /* 到点自己停(裁过就按裁剪终点停);被自动播放拦下时 onended 永远不会来,
           也靠这两个定时器把"这一句该有的时长"交出去 */
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
      var msg = { mc: 'boot-anim', type: type, id: 'mc-secret' }
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

  /** 字母间距拉开的品牌小字排版(上游写死过别家品牌名,这里跟着配置生成) */
  function spaced(t) {
    var words = String(t || '').replace(/\\s+/g, ' ').replace(/^ | $/g, '').split(' ')
    var out = []
    for (var i = 0; i < words.length; i++) out.push(words[i].split('').join('\\u00a0'))
    return out.join('\\u00a0\\u00a0')
  }
"""

QUERY_CFG = """    /* mini_code 补丁:宿主的开机动画只通过 query 传参
       (?speed=&interactive=&mute=&name= + theme.json options 里声明的键)。
       只认 DEFAULTS 里出现过的配置项,按默认值的类型转换,其余键一律忽略。 */
    var ALIAS = {
      brand: 'brand1', slogan: 'brand2', tagline: 'brand3a', tagline2: 'brand3b',
      org: 'orgEn', org_en: 'orgEn', orgzh: 'orgZh', org_zh: 'orgZh',
      orgsub: 'orgSub', org_sub: 'orgSub',
      welcome: 'welcomeBox', welcome_box: 'welcomeBox',
      identityid: 'identityId', accesslevel: 'accessLevel',
      access_password: 'identityPassword', voice_lang: 'voiceLang',
      voicevolume: 'voiceVolume', voicecue: 'voiceCue', soundvolume: 'soundVolume',
      require_interaction: 'requireInteraction', interaction: 'requireInteraction',
      /* mini_code:宿主的 interactive 那项在设置页叫「片尾可交互」,意思是动画演完之后
         覆盖层还允许操作,不是"每一步都要点确认",所以不接到 requireInteraction 上。
         要人工确认请用主题自己的 require_interaction=1。 */
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

MASCOT_CAT = """  /* ── 自绘「电路猫」立绘:红色描边线稿、透明底、纯内联 SVG ────────────────
     上游的 5 款人物立绘(真人线稿)一律不打包;这里换成一只自画的赛博猫:
     猫耳 + 猫脸 + 机甲胸甲 + 电路走线,只描边不填充。
     挂的还是上游那个 .dsu-mascot-img 通道,辉光呼吸 / 色彩呼吸 / 信号错位
     这三条 CSS 动画原样生效;mascot='none' 时整块不渲染(上游 mascot=-1 的行为)。 */
  var MASCOT_SVG =
    '<svg class="dsu-mascot-img" viewBox="0 0 280 420" xmlns="http://www.w3.org/2000/svg" ' +
      'fill="none" stroke-linecap="round" stroke-linejoin="round">' +
      '<g stroke="#ff3b30" stroke-width="3">' +
        '<path d="M64 118 L86 34 L128 84"/>' +
        '<path d="M216 118 L194 34 L152 84"/>' +
        '<path d="M84 98 L97 60 L116 86"/>' +
        '<path d="M196 98 L183 60 L164 86"/>' +
        '<path d="M46 150 C46 92 92 64 140 64 C188 64 234 92 234 150 C234 206 190 236 140 236 C90 236 46 206 46 150 Z"/>' +
        '<path d="M84 148 Q104 132 124 148 Q104 164 84 148"/>' +
        '<path d="M156 148 Q176 132 196 148 Q176 164 156 148"/>' +
        '<path d="M104 140 L104 156"/>' +
        '<path d="M176 140 L176 156"/>' +
        '<path d="M132 176 L148 176 L140 186 Z"/>' +
        '<path d="M140 186 Q132 198 118 194"/>' +
        '<path d="M140 186 Q148 198 162 194"/>' +
      '</g>' +
      '<g stroke="#c70000" stroke-width="2.5">' +
        '<path d="M104 233 L104 252 M176 233 L176 252"/>' +
        '<path d="M92 250 Q140 274 188 250"/>' +
        '<path d="M66 292 Q140 262 214 292 L204 372 Q140 402 76 372 Z"/>' +
        '<path d="M140 304 L157 314 L157 334 L140 344 L123 334 L123 314 Z"/>' +
        '<path d="M123 314 L96 298 L96 278"/>' +
        '<path d="M157 314 L184 298 L184 278"/>' +
        '<path d="M86 330 L112 337 M194 330 L168 337"/>' +
        '<path d="M118 390 L115 414 M140 398 L140 418 M162 390 L165 414"/>' +
      '</g>' +
      '<g stroke="#ff6a5e" stroke-width="2">' +
        '<path d="M42 156 L10 148 M44 172 L6 172 M46 188 L10 198"/>' +
        '<path d="M238 156 L270 148 M236 172 L274 172 M234 188 L270 198"/>' +
        '<circle cx="9" cy="148" r="3"/><circle cx="5" cy="172" r="3"/><circle cx="9" cy="198" r="3"/>' +
        '<circle cx="271" cy="148" r="3"/><circle cx="275" cy="172" r="3"/><circle cx="271" cy="198" r="3"/>' +
        '<path d="M124 86 L124 100 L140 108 L156 100 L156 86"/>' +
        '<circle cx="140" cy="120" r="4"/>' +
        '<circle cx="96" cy="276" r="3"/><circle cx="184" cy="276" r="3"/>' +
      '</g>' +
    '</svg>'
"""

MARK = """  /* ── mini_code 标识:六边形芯片,中间镂空一个 ">"(终端提示符) ─────────
     上游用的是第三方徽章(内嵌位图),品牌换成 Mini Code 后不能带走,
      这里换一枚同量级的自绘几何标识:第二条子路径靠 evenodd 变成镂空箭头。 */
  var MARK_PATH =
    'M25 3 L45 14 L45 36 L25 47 L5 36 L5 14 Z ' +
    'M30 16 L36 25 L30 34 L25.2 34 L30.8 25 L25.2 16 Z'

  function svgMark(cls) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('viewBox', '0 0 50 50')
    if (cls) svg.setAttribute('class', cls)
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    p.setAttribute('d', MARK_PATH)
    p.setAttribute('fill-rule', 'evenodd')
    svg.appendChild(p)
    return svg
  }
"""

VOICE_STUB = """  /* ── mini_code 补丁:女声播报 = 只有真声素材这一条路 ────────────────────
     浏览器合成音(TTS)整块移除:素材拿不到就安静地不放、返回 0 让画面按
     视觉基准走,绝不现场合成难听的人声。API 形态与上游保持一致。 */
  var voice = (function () {
    var meter = null
    function setMeter(on) { if (meter) meter.classList.toggle('dsu-on', !!on) }
    return {
      supported: false,
      load: function () {},
      attach: function (node) { meter = node },

      /** 念一行,resolve "这一行实际花了多久(ms)"。素材缺失/被自动播放拦掉时,
       *  分别返回 0 / 素材自身时长,动画永远不会被声音卡住。 */
      line: function (en, zh, asset) {
        if (!asset || !C.voice || finished) return Promise.resolve(0)
        var name = cnAsset(asset)
        return audio.ensureAsset(name).then(function (ok) {
          if (!ok || finished) return 0
          if (C.voiceCue !== false) audio.cue()
          return audio.playAssetAndWait(name, 0.92).then(function (d) {
            if (d > 0) setMeter(true)
            return d
          })
        })
      },

      /** 声卡要等用户手势才能出声:解锁一次 WebAudio(合成音效用) */
      unlock: function () { audio.resume() },

      /** 只有这里真的掐断(跳过 / 揭幕) */
      stop: function () { setMeter(false) }
    }
  })()
"""

CSS_TAIL = """
/* ==========================================================================
 * mini_code 主题补丁
 * 主题被宿主放进一个全屏 iframe 里,iframe 自己就是整块画布:
 *   - html/body 去掉默认 8px 边距、铺纯黑底(上游默认就是暗色底板 theme:'dark')
 *   - 锁死 overflow 并藏起所有滚动条:沙箱 iframe 里不该出现任何滚动条
 * ========================================================================== */
html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}
* { scrollbar-width: none; -ms-overflow-style: none; }
::-webkit-scrollbar { width: 0; height: 0; display: none; }
"""

INDEX_HTML = """<!doctype html>
<!--
  机密接入 —— mini_code 开机动画主题(画面移植自 dsh-startup-secret,MIT,© 2026 二次创作作者,
  github.com/huzhengcai471-crypto/dsh-startup-secret;授权原文见插件仓库根目录
  LICENSE-DSH-SECRET;品牌、徽标与立绘均为 Mini Code 自绘)。
  由 tools/port_secret.py 生成,素材来源见插件仓库 README「致谢与来源」。
-->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>机密接入 · Mini Code</title>
<link rel="stylesheet" href="boot.css">
</head>
<body>
<script src="boot.js"></script>
</body>
</html>
"""


PATCHED = []          # 补丁条数统计(回报用)


def patch(s, label, old, new, count=1, regex=False, flags=0):
    """打一条补丁;匹配数不对就直接失败,避免生成半成品。"""
    if regex:
        out, n = re.subn(old, new, s, count=count + 1, flags=flags)
    else:
        n = s.count(old)
        out = s.replace(old, new) if n else s
    if n != count:
        msg = "[FAIL] 补丁 %s 匹配 %d 次(期望 %d): %r" % (label, n, count, old[:70])
        # Windows GBK 控制台兜底:编码不了的字符转义掉,不许因打印崩掉
        try:
            sys.stderr.write(msg + "\n")
        except UnicodeEncodeError:
            sys.stderr.write(msg.encode(sys.stderr.encoding or "ascii", "backslashreplace").decode(sys.stderr.encoding or "ascii") + "\n")
        sys.exit(1)
    PATCHED.append(label)
    return out


def js_patches(src):
    s = src
    n_patch = 0

    def P(text, label, old, new, count=1, regex=False, flags=0):
        # 记录补丁条数用的小包装,行为与 patch() 完全一致
        return patch(text, label, old, new, count=count, regex=regex, flags=flags)

    # ── 文件头:去掉上游总说明(里面有别家品牌名),换成移植说明 ───────────
    s = P(s, "header-strip", r"^/\* =+\n[\s\S]*?\*/\n", "", regex=True)
    s = BANNER + s

    # ── 根节点 id 前缀 + 桥 + query 配置 + spaced():插在 ROOT_ID 之后 ─────
    # (CSS 里的 #dsh-startup-root 选择器同步改名,见 css_patches;类名 dsu-* 不改)
    s = P(s, "bridge", "  var ROOT_ID = 'dsh-startup-root'\n",
          "  var ROOT_ID = 'mc-secret-root'\n" + BRIDGE)

    # ── iframe 里每帧都是首帧:脚本重挂标志没有意义,删 ────────────────────
    s = P(s, "loaded-guard",
          "  if (window.__DSH_STARTUP_LOADED__) return\n"
          "  window.__DSH_STARTUP_LOADED__ = true\n", "")

    # ── 别家标识的官方路径数据:连注释一起删,换成自绘 MARK(见下方 svgMark) ─
    s = P(s, "whale-path", r"  /\* ── DeepSeek 官方鲸鱼标识[^\n]*\n  var WHALE_PATH =[\s\S]*?27\.8799Z'\n", "", regex=True)

    # ── 配置默认值:品牌换 Mini Code,默认全自动、默认暗色不动 ──────────────
    for label, old, new in [
        ("identity",
         "    identity: 'Chunhua',        // ← 设置页可改的\"身份名称\"",
         "    identity: '哈基米指挥官',    // ← mini_code 补丁:默认身份名(宿主 name= 参数优先)"),
        ("identityId",
         "    identityId: 'A000001',",
         "    identityId: 'MC-000001',"),
        ("brand1", "    brand1: '银河意识体',", "    brand1: '迷你代码',"),
        ("brand2", "    brand2: 'LONG MARCH  HARNESS',", "    brand2: 'MINI CODE  AGENT WORKBENCH',"),
        ("brand3a", "    brand3a: '长征机',", "    brand3a: '本地智能体',"),
        ("brand3b", "    brand3b: '量子跃迁态',", "    brand3b: '离线运行',"),
        ("orgZh", "    orgZh: '伟大智能统辖',", "    orgZh: '本地智能体工作台',"),
        ("orgEn", "    orgEn: 'GREAT INTELLIGENT DOMINATION',", "    orgEn: 'LOCAL AGENT WORKBENCH',"),
        ("welcomeBox", "    welcomeBox: '亚洲人民统辖体',", "    welcomeBox: 'MINI CODE',"),
        ("footer", "    footer: 'Powered By LONG MARCH',", "    footer: 'POWERED BY MINI CODE',"),
        ("requireInteraction",
         "    requireInteraction: true,   // 旧字段：仅用于迁移到 autoPlay（见下方 normalize）",
         "    requireInteraction: false,  /* mini_code 补丁:默认全自动播完;只有 require_interaction=1 才逐步等确认 */"),
        ("voiceLang",
         "    voiceLang: 'zh',            // zh | en（仅作真声素材缺失时的 TTS 兜底；自动（优先神经网络女声）-US 本体为内置真声）",
         "    voiceLang: 'en',            /* mini_code 补丁:真声素材语种 en=line-1..5 / cn=line-cn-1..5(theme.json 的 voice_lang) */"),
        ("voiceName",
         "    voiceName: '',            // '' = 自动（优先神经网络女声）-US（真声 line-1..6）/ 'zhixing-cn' = 智性少女音-CN（真声 line-cn-1..6）/ 'calmlady-jp' = 清冷优雅-日语（真声 line-jp-1..6）/ 'pessimistic-ru' = 清冷脆弱-俄语（真声 line-ru-1..6）/ 'announcer-kr' = 威严铿锵宣示-朝鲜语（真声 line-kr-1..6）\n",
         ""),
        ("voiceVolume", "    voiceVolume: 0.9,", "    voiceVolume: 1,   /* mini_code 补丁:<audio> 音量上限就是 1,默认给满 */"),
        ("voiceSource",
         "    voiceSource: 'asset',       // asset=优先用真声素材 / tts=全部 TTS 合成",
         "    voiceSource: 'asset',       /* mini_code 补丁:只有真声素材一种来源,浏览器合成音已移除 */"),
        ("mascot",
         "    mascot: 0,                  // 右下角人物立绘编号（0-3 对应设置页，-1 = 空 / 不显示立绘）",
         "    mascot: 'cat',              /* mini_code 补丁:立绘款式 'cat'=自绘电路猫 / 'none'=不显示 */"),
        ("eventWindow",
         "    eventWindow: false,         // 降世事件窗口：默认关闭；开启后每次动画结束都弹出\n",
         ""),
    ]:
        s = P(s, label, old, new)

    # ── 配置来源:Host 注入的全局改成 query(port_access 的 ALIAS 机制) ──────
    s = P(s, "raw-src",
          "    var raw = (window.__DSH_STARTUP__ && typeof window.__DSH_STARTUP__ === 'object')\n"
          "      ? window.__DSH_STARTUP__\n"
          "      : {}\n"
          "    /* 降世事件窗口「首次启动弹一次」的一次性标记（localStorage，跨会话） */\n"
          "    var EVENT_SEEN_KEY = 'dsh-startup-screen:event-seen'\n",
          "    var raw = {}   /* mini_code 补丁:配置一律来自 location.search(宿主注入),不读任何全局 */\n")
    s = P(s, "query-cfg",
          "    var out = {}\n"
          "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n",
          "    var out = {}\n"
          "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n"
          + QUERY_CFG)

    # ── 事件窗口「首次弹一次」的浏览器存储记录:整块删(sandbox 里也读不到) ──
    s = P(s, "event-cfg", r"    /\* ── 降世事件窗口 ─[\s\S]*?(?=    var mi = parseInt)", "", regex=True)

    # ── mascot 参数:'0..4/-1' 改成 'cat' / 'none' ──────────────────────────
    s = P(s, "mascot-cfg",
          r"    var mi = parseInt\(out\.mascot, 10\)\n[\s\S]*?    out\.showMascot = out\.mascot >= 0\n",
          "    /* mini_code 补丁:立绘只有自绘「电路猫」一款,除 'none' 外一律按猫处理 */\n"
          "    out.mascot = String(out.mascot).toLowerCase() === 'none' ? 'none' : 'cat'\n"
          "    out.showMascot = out.mascot !== 'none'\n", regex=True)

    # ── 代号允许连字符:兜底身份编号 MC-000001 别被洗成 MC000001 ────────────
    s = P(s, "identityid-sanitize",
          "out.identityId = String(out.identityId || out.identity).toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12)",
          "out.identityId = String(out.identityId || out.identity).toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 12)")

    # ── Host 侧配套(拉配置/重挂脚本/重播)整段删除:iframe 里没有这些东西 ───
    s = P(s, "host-plumbing",
          r"  /\* ── 让「设置里刚保存的配置」立刻生效（2026-10-18 新增）[\s\S]*?document\.head\.appendChild\(s\)\n  \}\n", "", regex=True)
    # 首屏「这次不播」短路分支:主题在 iframe 里,播不播由宿主决定
    s = P(s, "skip-branch", r"  /\* Host 侧的首屏兜底脚本[\s\S]*?return\n  \}\n", "", regex=True)

    # ── 兜底:超时必须触发 done;黑幕垫层/失败标记这些 Host 侧的东西删掉 ─────
    s = P(s, "failsafe-notify", "      if (r && r.classList && r.classList.contains('dsu-boot')) {\n",
          "      if (r && r.classList && r.classList.contains('dsu-boot')) {\n"
          "        MC.done()   /* mini_code 补丁:卡住了也得把界面还给宿主 */\n")
    s = P(s, "failsafe-veil",
          "        /* 首屏黑幕层也要一起撤，否则放行了却还是全黑 */\n"
          "        var v = document.getElementById('dsh-startup-veil')\n"
          "        if (v && v.parentNode) v.parentNode.removeChild(v)\n", "")
    s = P(s, "failsafe-flag", "        window.__DSH_STARTUP_FAILED__ = true\n", "")
    s = P(s, "failsafe-timeout", r"\n  \}, 9000\)\n", "\n  }, 90000)\n", regex=True)

    # ── 首屏黑幕垫层:那是 Host 页面里的东西,sandbox iframe 里根本不需要,删 ──
    s = P(s, "veil-create",
          r"  /\* 重播时首屏黑幕层可能已被上一次 finish 清掉[\s\S]*?document\.body\.insertBefore\(veil, document\.body\.firstChild\)\n  \}\n",
          "", regex=True)

    # ── 内嵌图片资源全部铲除:立绘 → 自绘电路猫,事件/徽章见下面的补丁 ───────
    s = P(s, "mascot-src",
          r"  /\* ── 中国共产党党徽[\s\S]*?var MASCOTS = \[MASCOT_SRC, MASCOT_SRC_1, MASCOT_SRC_2, MASCOT_SRC_3, MASCOT_SRC_4\]\n",
          MASCOT_CAT, regex=True)
    # 事件窗口插画声明(使用处在 eventGate,随后一并删)
    s = P(s, "event-src", r"  /\* ── 事件窗口（动画结束后、进入主界面前）[^\n]*\n  var EVENT_SRC = '[^\n]*\n", "", regex=True)
    # 第三方徽章 → 自绘 Mini Code 徽标(内联 SVG,不用任何图片资源)
    s = P(s, "emblem-mark",
          r"  var EMBLEM_SRC = '[^\n]*\n\n  function svgWhale\(cls\) \{[\s\S]*?\n  \}\n", MARK, regex=True)
    # 黑幕上的徽标:img → svg(变量顺手改名),后面两处调用点跟着改
    s = P(s, "mark-blackstage",
          "    var whale = svgWhale('dsu-whale')\n    inner.appendChild(whale)",
          "    var mark = svgMark('dsu-mark')\n    inner.appendChild(mark)")
    s = P(s, "mark-calls", "svgWhale(", "svgMark(", count=2)

    # ── 装配动画等的是 <img>,徽标换成 <svg> 后选择器要跟着改 ───────────────
    s = P(s, "assemble-img", "    /* 党徽图片：柔和放大淡入（图片版不再做勾线动画，保持丝滑） */",
          "    /* 徽标：柔和放大淡入（保持丝滑） */")
    s = P(s, "assemble-svg", "    var img = ui.logo.querySelector('img')", "    var img = ui.logo.querySelector('svg')")

    # ── 立绘挂载区:内嵌图片 → 内联 SVG;mascot='none' 时整块不渲染 ──────────
    s = P(s, "mascot-mount",
          r"  /\* 赛博风人物立绘（第二页起右下角）[\s\S]*?ui\.event = q\('\.dsu-event'\)\n",
          "  /* mini_code 补丁:右下角立绘 = 自绘「电路猫」红线稿(内联 SVG,无图片资源)。\n"
          "     设置 mascot='none' 时整块不渲染(上游「立绘=空」的行为)。 */\n"
          "  ui.mascot = q('.dsu-mascot')\n"
          "  if (C.showMascot) {\n"
          "    ui.mascot.setAttribute('data-mascot', 'cat')\n"
          "    ui.mascot.innerHTML = MASCOT_SVG\n"
          "  } else {\n"
          "    ui.mascot.hidden = true\n"
          "  }\n", regex=True)
    # html 模板里的事件窗口占位一起删
    s = P(s, "event-div",
          "    '<div class=\"dsu-mascot\" hidden></div>' +\n    '<div class=\"dsu-event\" hidden></div>'",
          "    '<div class=\"dsu-mascot\" hidden></div>'")

    # ── 写死的别家品牌小字 → 配置驱动 ──────────────────────────────────────
    s = P(s, "logo-label",
          "    ui.logo.appendChild(el('div', 'dsu-logolabel', 'D E E P S E E K'))",
          "    ui.logo.appendChild(el('div', 'dsu-logolabel', spaced(C.orgEn)))")
    s = P(s, "welcome-label",
          "    ui.w3.appendChild(el('span', 'dsu-w3label', 'D E E P S E E K  ·  H A R N E S S'))",
          "    ui.w3.appendChild(el('span', 'dsu-w3label', spaced(C.welcomeBox) + '  ·  ' + spaced(C.brand3a)))")
    s = P(s, "meta1", "    ui.meta1.textContent = 'REV 0.1.0 · WEB PROFILE'",
          "    ui.meta1.textContent = 'MINI CODE · BOOT SEQUENCE'")

    # ── 序列脚本注释:五个音色/六个槽位的说明换成本主题实际带的素材 ──────────
    s = P(s, "steps-comment",
          r"  /\* ── 序列脚本 ─[\s\S]*?TTS 兜底文本。 \*/\n",
          "  /* ── 序列脚本 ──────────────────────────────────────────────────────────\n"
          "     5 句播报与素材一一对应:line-1 需要访问许可 / line-2 身份资料确认\n"
          "     line-3 接收访问需求 / line-4 开始读取权限 / line-5 读取完毕核验通过。\n"
          "     voice_lang='en' 用 line-N,'cn' 用 line-cn-N(cnAsset 负责前缀映射)。\n"
          "     素材拿不到就安静地不出声,绝不回落浏览器合成音。 */\n", regex=True)

    # ── 五个音色前缀映射 → 两音色(en/cn);幂等形态保留,防前缀叠加 ──────────
    s = P(s, "cn-asset",
          r"  /\* 五个音色各用一套独立素材[\s\S]*?\n  \}\n",
          "  /* mini_code 补丁:主题只带中英两套素材,voice_lang='cn' 走 line-cn-N,否则 line-N。\n"
          "     幂等形态保留:重复解析结果不变,避免前缀叠加。 */\n"
          "  function cnAsset(n) {\n"
          "    if (!n) return n\n"
          "    var m = /^line-(?:cn-)?([0-9]+)$/.exec(n)\n"
          "    if (!m) return n\n"
          "    return (C.voiceLang === 'cn' ? 'line-cn-' : 'line-') + m[1]\n"
          "  }\n", regex=True)

    # ── 声音总说明改口径(音效=素材+合成兜底;播报=只有真声素材) ────────────
    s = P(s, "sound-comment", r"  /\* ── 声音 ─[\s\S]*?\*/\n",
          "  /* ── 声音 ──────────────────────────────────────────────────────────────\n"
          "   *   audio —— 界面音效:真素材(sfx-tick / sfx-ticks-run)优先,合成音兜底\n"
          "   *   voice —— 女声播报:真声素材(line-* / line-cn-*),素材缺失就安静\n"
          "   * 浏览器可能拦自动播放:每个 play() 都 catch,没声音也把动画演完。 */\n", regex=True)

    # ── 素材加载:内嵌资源包 + decodeAudioData → <audio>(CSP connect-src 'none')─
    s = P(s, "audio-impl",
          r"    /\* 真声素材[\s\S]*?function playAsset\(name, gain\) \{[\s\S]*?\n    \}\n",
          AUDIO_IMPL, regex=True)
    # 上游 return 表里 confirm 写了两次,后一条把"优先用真素材"的那条覆盖掉了
    s = P(s, "dup-confirm",
          "      confirm: function () { tone(660, 0.09, 'triangle', 0.07); tone(990, 0.17, 'triangle', 0.055, 0.085) },\n", "")

    # ── 浏览器合成音(TTS)整块移除:换成只走真声素材的小模块 ────────────────
    s = P(s, "voice-module", r"  var voice = \(function \(\) \{[\s\S]*?\n  \}\)\(\)\n", VOICE_STUB, regex=True)
    # 终幕 line-6 素材本主题不打包:预取列表里去掉,免得空跑一次 404
    s = P(s, "preload-line6",
          "\n    audio.ensureAsset(cnAsset('line-6'))   /* 终幕欢迎语 */", "")
    # voiceschanged 监听是合成音配套,删
    s = P(s, "wire-sound",
          "    voice.load()\n"
          "    if (voice.supported && typeof window.speechSynthesis.addEventListener === 'function') {\n"
          "      try { window.speechSynthesis.addEventListener('voiceschanged', function () { voice.load() }) } catch (e) {}\n"
          "    }\n",
          "    voice.load()\n")

    # ── 协议挂钩:ready / step / handoff / done ─────────────────────────────
    s = P(s, "ready", "  function run() {\n",
          "  function run() {\n    MC.ready()   /* mini_code 补丁:首帧交给宿主,可以显示跳过按钮了 */\n")
    s = P(s, "step", "        setStepCount(n, step.badge)\n",
          "        setStepCount(n, step.badge)\n        MC.step(n, STEPS.length + 1, step.zh, step.progress)   /* mini_code 补丁 */\n")
    s = P(s, "handoff", "        root.classList.add('dsu-handoff')\n",
          "        root.classList.add('dsu-handoff')\n        MC.handoff()   /* mini_code 补丁:淡出第一帧就交还界面 */\n")
    s = P(s, "done", "    finished = true\n    releaseAll()\n",
          "    finished = true\n    MC.done()   /* mini_code 补丁:跳过 / 出错 / 播完都从这里交还 */\n    releaseAll()\n")
    s = P(s, "run-warn", "'[dsh-startup-screen] 动画异常，直接揭幕：'", "'[mc-secret] 动画异常，直接揭幕：'")
    s = P(s, "run-comment", "/* 第一幕：黑幕 --> DeepSeek 标识 */", "/* 第一幕：黑幕 --> Mini Code 徽标 */")
    s = P(s, "reticle-comment", "鲸鱼标识和虚线收掉", "徽标和虚线收掉")
    s = P(s, "center-comment", "/* 中央区（状态行/分隔线/鲸鱼/虚线）", "/* 中央区（状态行/分隔线/徽标/虚线）")

    # ── 终幕:不打包 line-6 欢迎语,画面照常走完(静音) ──────────────────────
    s = P(s, "finale-welcome",
          r"    /\* 终幕欢迎语[\s\S]*?var welcome = voice\.line\(null, null, 'line-6'\)\n",
          "    /* mini_code 补丁:上游终幕那句「欢迎语」语音素材本主题不携带 ——\n"
          "       终幕只有画面与合成钟,不再等一句不存在的人声。 */\n"
          "    var welcome = Promise.resolve(0)\n", regex=True)

    # ── 「降世事件窗口」整条路径删除(动画演完直接交还宿主) ─────────────────
    s = P(s, "event-call", "      .then(function () { return eventGate() })\n", "")
    s = P(s, "event-gate", r"  /\* 事件窗口：动画播完、揭幕之后弹出[\s\S]*?(?=  function finish\(\) \{)", "", regex=True)

    # ── 立绘相关收尾:显示条件跟着 mascot 新语义走 ──────────────────────────
    s = P(s, "mascot-gate",
          "    if (C.showMascot !== false && C.mascot >= 0 && (step.action === 'grant' || step.action === 'confirm')) {",
          "    if (C.showMascot && (step.action === 'grant' || step.action === 'confirm')) {")
    s = P(s, "mascot-action-comment",
          "       立绘设为「空」（mascot = -1）时整块保持隐藏。 */",
          "       mascot='none' 时整块保持隐藏。 */")

    # ── finish:「这次是否已播」归宿主记录,主题不碰浏览器存储 ───────────────
    s = P(s, "finish-storage",
          "    try {\n"
          "      if (C.mode === 'session') window.sessionStorage.setItem('dsh-startup-screen:shown', '1')\n"
          "      if (C.mode === 'daily') {\n"
          "        window.localStorage.setItem('dsh-startup-screen:day', new Date().toISOString().slice(0, 10))\n"
          "      }\n"
          "    } catch (err) { /* 隐私模式下不可写，忽略 */ }\n",
          "    /* mini_code 补丁:「本次是否已播」由宿主记录,主题不读写任何浏览器存储 */\n")
    s = P(s, "finish-veil",
          "    /* 首屏黑幕层：dsu-lock 撤掉后它已不可见，这里顺手把节点清掉别留垃圾 */\n"
          "    var veil = document.getElementById('dsh-startup-veil')\n"
          "    if (veil && veil.parentNode) veil.parentNode.removeChild(veil)\n", "")
    s = P(s, "finish-event",
          "    try { window.dispatchEvent(new CustomEvent('dsh-startup:done')) } catch (err) { /* noop */ }\n", "")

    # ── Host 侧设置面板 API:iframe 里没人调,删(重播=刷新,由宿主决定) ───────
    s = P(s, "api-block", r"  /\* 对外 API：settings 面板里的[\s\S]*?config: C\n  \}\n", "", regex=True)

    # ── 人工确认不许把开机卡死:没有密码的那一步最多等 12s 就自动往下走 ────────
    #    用户走开、或者压根不知道该按回车时,动画照样该进软件。要密码那一步不放行,
    #    那种情况由宿主的 Esc 跳过兜底。fin() 自带 done 标志,重复调用没有副作用。
    s = P(s, "action-autorelease",
          "      ui.btn.addEventListener('click', onClick)\n"
          "      ui.action.addEventListener('click', onClick)\n"
          "      document.addEventListener('keydown', onKey)\n"
          "      waiters.push(fin)\n",
          "      ui.btn.addEventListener('click', onClick)\n"
          "      ui.action.addEventListener('click', onClick)\n"
          "      document.addEventListener('keydown', onKey)\n"
          "      waiters.push(fin)\n"
          "      /* mini_code 补丁:等待也要有尽头,别把人卡在开机动画前 */\n"
          "      if (!needPwd) setTimeout(function () { fin() }, ms(12000))\n")

    return s


def css_patches(src):
    s = src

    # ── 文件头:上游样式总说明换成本主题的移植说明(署名 MIT 上游见 LICENSE-DSH-SECRET)─
    s = patch(s, "css-header", r"^/\* =+\n \* dsh-startup-screen[\s\S]*?\*/\n",
              "/* ============================================================================\n"
              " * 机密接入 —— mini_code 开机动画主题样式 (boot-anim/mc-secret)\n"
              " * ----------------------------------------------------------------------------\n"
              " * 画面样式移植自 dsh-startup-secret v1.4.2(MIT, © 2026 二次创作作者,\n"
              " * 授权原文见插件仓库根目录 LICENSE-DSH-SECRET);品牌与标识已换成 Mini Code,\n"
              " * 由 tools/port_secret.py 生成,勿手改。风格骨架:黑色序幕 → 洗白转场 →\n"
              " * 暗色终端底板 → 等宽字距状态行 → 环形准星扫描 → WELCOME 版式 → 收尾。\n"
              " * ========================================================================== */\n",
              regex=True)

    # ── 颗粒噪点层自带一枚内嵌 data URI 纹理:按插件规范不打包内嵌图片,删纹理留节点 ─
    s = patch(s, "grain-uri", r"  background-image: url\(\"data:image[^\n]*\n", "", regex=True)
    s = patch(s, "grain-comment", '/* 细颗粒噪点，让大色块不"塑料" */',
              '/* 颗粒层(上游内嵌噪点纹理已按插件规范移除,保留节点与透明度动画) */')

    # ── 第 5 款立绘(纪念碑浮雕)注释与选择器 → 自绘「电路猫」 ───────────────
    #    动效三条(scan=辉光呼吸 / hue=色彩呼吸 / glitch=信号错位)原样保留。
    s = patch(s, "mascot-cat-rule",
              r"/\* ── 第 5 款立绘[\s\S]*?#dsh-startup-root \.dsu-mascot\[data-mascot=\"4\"\] \.dsu-mascot-img \{",
              "/* ── mini_code 立绘「电路猫」：自绘红色描边线稿(内联 SVG) ──────────────\n"
              "   上游这一组是第 5 款浮雕的电子风动效;本主题的猫挂同一个通道,三条全保留:\n"
              "   辉光呼吸(scan) + 色彩呼吸(hue) + 偶发信号错位(glitch)。 */\n"
              "#dsh-startup-root .dsu-mascot[data-mascot=\"cat\"] .dsu-mascot-img {", regex=True)
    s = patch(s, "mascot-cat-reduced",
              "  #dsh-startup-root .dsu-mascot[data-mascot=\"4\"] .dsu-mascot-img { animation: none; }",
              "  #dsh-startup-root .dsu-mascot[data-mascot=\"cat\"] .dsu-mascot-img { animation: none; }")

    # ── 徽标配色:金色(第三方徽章色) → 故障红(跟随 --dsu-glitch-a) ──────────
    s = patch(s, "mark-fill",
              "/* 中央标识与终幕标识：金黄镰刀锤头，固定金色不随主题变化 */\n"
              ".dsu-logo svg,\n"
              ".dsu-w3 svg { fill: #fdd000; }",
              "/* 中央标识与终幕标识：Mini Code 芯片徽标,跟着故障红走 */\n"
              ".dsu-logo svg,\n"
              ".dsu-w3 svg { fill: var(--dsu-glitch-a, #ff3b30); }")
    s = patch(s, "whale-fill",
              ".dsu-whale {\n  display: block;\n  fill: #fdd000;\n}",
              ".dsu-whale {\n  display: block;\n  fill: var(--dsu-glitch-a, #ff3b30);\n}")
    # 类名 dsu-whale → dsu-mark(与 JS 里 svgMark('dsu-mark') 同步)
    s = patch(s, "whale-rename", "dsu-whale", "dsu-mark", count=2)
    # 注释里的第三方品牌名 / 「鲸鱼」字样清掉
    s = patch(s, "logo-comment", "/* 中央标识（鲸鱼）装配区 */", "/* 中央标识（徽标）装配区 */")
    s = patch(s, "act1-comment", "/* ── 第一幕：黑幕 + DeepSeek 标识 ─", "/* ── 第一幕：黑幕 + Mini Code 徽标 ─")

    # ── 根节点改名:CSS 里 36 处 #dsh-startup-root 前缀一起换(改就改全,不改一半) ─
    s = patch(s, "root-id", "#dsh-startup-root", "#mc-secret-root", count=36)

    # ── 「事件窗口」整段样式删除(JS 侧这条路径已移除) ──────────────────────
    s = patch(s, "event-css", r"\n/\* ── 事件窗口（动画结束后、进入主界面前）─[\s\S]*$", "\n", regex=True)

    # ── 右侧 ID 信息行:上游放在 top:49%,正好压在中央英文字幕上(本主题副标题更长,
    #    "ACCESS PERMISSION REQUIRED" 直接和它糊在一起)。挪到字幕下方错开一行。
    s = patch(s, "idline-below-sub",
              ".dsu-idline {\n  position: absolute;\n  left: calc(50% + 190px);\n  top: 49%;",
              "/* mini_code 补丁:这行原本 top:49%,会压在中央英文字幕上,挪到字幕下方 */\n"
              ".dsu-idline {\n  position: absolute;\n  left: calc(50% + 190px);\n  top: 57.5%;")

    return s + CSS_TAIL


# voice_lang 决定念哪套台词(en=line-1..5 / cn=line-cn-1..5)。宿主设置页只给 速度/身份名/
# 静默/交互 四个开关,没有它 —— 想听中文播报,把下面这个默认值改成 cn 重新生成本主题,或者
# 直接改本地主题目录 ~/.mini_code/boot-anim/mc-secret/theme.json。
THEME_JSON = {
    "id": "mc-secret",
    "name": "机密接入",
    "nameEn": "Secret Access",
    "author": "zhoujiannan-nb",
    "version": "1.0.0",
    "license": "MIT",
    "entry": "index.html",
    "preview": "preview.svg",
    "description": "黑底开机的一个:红色 Mini Code 徽标先亮起来,然后「需要访问许可」「身份资料确认」一屏一屏走到「核验通过」才进软件,右下角有只红线描的电路猫陪着你,每一步有外国女声报读。全程约 16 秒,嫌慢就把速度调快,不想听声音就勾「静默」。",
    "durationMs": 16500,
    "maxMs": 45000,
    "colors": ["dark"],
    "interactive": False,
    "minViewport": 480,
    "tags": ["开机", "暗色", "语音", "音效", "小猫"],
    "options": {
        "voice_lang": "en",
        "mascot": "cat",
        "access_password": "",
        "brand1": "迷你代码",
        "brand2": "MINI CODE  AGENT WORKBENCH",
        "org_zh": "本地智能体工作台",
        "org_en": "LOCAL AGENT WORKBENCH",
        "org_sub": "效率高于一切",
        "welcome_box": "MINI CODE",
        "footer": "POWERED BY MINI CODE",
        "require_interaction": 0
    }
}

PREVIEW_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">
  <rect width="320" height="200" fill="#0b0b0c"/>
  <g fill="none" stroke="#f2f1ee" stroke-width="1" opacity=".16">
    <path d="M18 18h284v164H18z"/>
    <path d="M36 40h248M36 54h248M36 68h180"/>
  </g>
  <path d="M160 48 L182 61 L182 87 L160 100 L138 87 L138 61 Z" fill="#c70000"/>
  <path d="M164 62 L173 74 L164 86 L159 86 L167.5 74 L159 62 Z" fill="#0b0b0c"/>
  <text x="160" y="126" font-family="Arial Narrow, sans-serif" font-size="13" fill="#f2f1ee" text-anchor="middle" letter-spacing="3">MINI CODE</text>
  <text x="160" y="142" font-family="Consolas, monospace" font-size="7.5" fill="#ff3b30" text-anchor="middle" letter-spacing="1.5">SECRET ACCESS</text>
  <g fill="none" stroke="#ff3b30" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
    <path d="M262 160 l6 -15 9 10M294 160 l-6 -15 -9 10"/>
    <path d="M258 172c0-9 7-15 19-15s19 6 19 15-7 15-19 15-19-6-19-15z"/>
    <path d="M269 171h5M281 171h5"/>
    <path d="M255 168h-9M255 175h-9M296 168h9M296 175h9"/>
  </g>
  <rect x="36" y="176" width="180" height="3" fill="#3a0a0a"/>
  <rect x="36" y="176" width="118" height="3" fill="#ff3b30"/>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dsh-startup-secret 的本地检出目录")
    a = ap.parse_args()
    lib = os.path.join(a.src, "lib")
    assets_dir = os.path.join(lib, "assets")
    for need in ["splash.js", "splash.css"]:
        if not os.path.isfile(os.path.join(lib, need)):
            sys.exit("[FAIL] missing lib/%s -- wrong --src?" % need)
    for m in ASSETS:
        if not os.path.isfile(os.path.join(assets_dir, m)):
            sys.exit("[FAIL] missing asset %s" % m)

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

    # stdout 只出 ASCII(Windows GBK 控制台),文件名本身都是 ASCII
    print("[OK] patches applied: %d" % len(PATCHED))
    print("[OK] generated %s" % OUT)
    for n in sorted(os.listdir(OUT)):
        print("     %-18s %8d B" % (n, os.path.getsize(os.path.join(OUT, n))))


if __name__ == "__main__":
    main()
