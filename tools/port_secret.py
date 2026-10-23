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

画面和素材都按上游原样保留(党徽、5 张人物立绘、事件插画、真声台词、音效),
只动四件事:
  1. 品牌文字全部换成 Mini Code —— 上游写死的别家品牌名(含注释里的)一并换掉;
  2. 上游把 7 张图做成了内嵌 data URI,这里抽成主题目录里的扁平文件
     (宿主 CSP 是 img-src 'self' data:,同目录相对路径可用;主题目录必须扁平,
      tools/make_index.py 遇到子目录直接判失败);
  3. 播报默认走中文女声素材(line-cn-1..5,上游的「智性少女音-CN」),并且永久
     移除浏览器合成音(TTS)兜底 —— 素材拿不到就安静地不放;
  4. 对接 mini_code 宿主的开机动画协议与 query 传参;音频从上游的内嵌 base64
     资源包改成 <audio> 元素 + 同目录 mp3(宿主 CSP connect-src 'none',
     fetch 必被拦,media-src 'self' 已放行)。

素材里有真人线稿、政治标识与别人的声音录音:只能自用/学习,别提交到公开仓库,
授权风险与出处见插件仓库 README「致谢与来源」。

注意:本脚本 stdout 只打 ASCII(Windows GBK 控制台),细节一律可自查。
"""
import argparse
import base64
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

# 上游内嵌成 data URI 的 7 张图:抽成主题目录里的扁平文件(变数字面量换成文件名)。
# 命名和上游语义对齐:mascot-N = 第 N 款人物立绘,event = 事件窗口插画,emblem = 中央徽标。
IMAGES = [("MASCOT_SRC", "image/webp", "mascot-0.webp"),
          ("MASCOT_SRC_1", "image/webp", "mascot-1.webp"),
          ("MASCOT_SRC_2", "image/webp", "mascot-2.webp"),
          ("MASCOT_SRC_3", "image/webp", "mascot-3.webp"),
          ("MASCOT_SRC_4", "image/webp", "mascot-4.webp"),
          ("EVENT_SRC", "image/webp", "event.webp"),
          ("EMBLEM_SRC", "image/png", "emblem.png")]

BANNER = """/* ============================================================================
 * 机密接入 —— mini_code 开机动画主题 (boot-anim/mc-secret)
 * ----------------------------------------------------------------------------
 * 移植自 dsh-startup-secret v1.4.2(MIT, Copyright (c) 2026 二次创作作者,
 * github.com/huzhengcai471-crypto/dsh-startup-secret;授权原文见插件仓库根目录
 * LICENSE-DSH-SECRET):暗色序列、节奏、真声播报、音效、党徽与人物立绘都来自
 * 那个项目,这里只做五件事 ——
 *   1. 品牌文字全部换成 Mini Code(上游在三个地方写死了别家品牌名);
 *   2. 上游把党徽 / 立绘 / 事件插画做成 7 个内嵌 data URI,这里抽成主题目录
 *      里的扁平文件(emblem.png / mascot-0..4.webp / event.webp),画面不变;
 *   3. 移除浏览器合成音兜底:播报只认真声素材,素材拿不到就安静地不放;
 *      默认播报语种 = 中文女声(line-cn-1..5,上游的「智性少女音-CN」);
 *   4. 对接 mini_code 宿主的开机动画协议(ready / step / handoff / done,见
 *      插件仓库 docs/theme-contract.md),跳过按钮归宿主,主题不自画;
 *   5. 素材加载改成 <audio> 元素 + 主题目录同名 mp3:宿主以
 *      CSP connect-src 'none' 提供主题文件,fetch 一定被拦。
 * 所有改动都带 "mini_code 补丁" 注释,由 tools/port_secret.py 生成,勿手改。
 * 素材含真人线稿 / 政治标识 / 他人录音:自用可以,公开分发前先确认授权。
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

    /* mini_code 补丁:素材头尾的"死空气"用 TRIMS 描述 [from, until](毫秒)。
       数值是逐 40ms 窗量 RMS(阈值 -38dBFS)实测的:中文这 5 句素材开头留着约
       120ms 静音、结尾还有一小截空气,裁掉以后每一屏的衔接紧一点。英文那 5 句
       本来就是贴边切的,没有可裁的余量,所以不裁(上游 AUDIO-FIELDS.md 的时长表
       也是这个结论)。不在表里的文件照原样播。 */
    var TRIMS = {
      'line-cn-1': [80, 1480],
      'line-cn-2': [80, 1360],
      'line-cn-3': [80, 1240],
      'line-cn-4': [80, 1240],
      'line-cn-5': [120, 1830]
    }

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
       /* 契约要求 ready 顺带把 durationMs / maxMs / steps 报上去(宿主和预览器都拿它
          做显示与兜底)。前两个就是 theme.json 里那两个数(宿主还会把 maxMs 钳到
          30000 以内),改 theme.json 记得同步改这里。 */
       ready: function () {
         post('ready', {
           durationMs: 17000,
           maxMs: 30000,
           steps: (typeof STEPS === 'undefined' ? 6 : STEPS.length + 1)
         })
       },
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
       event_window: 'eventWindow', eventwindow: 'eventWindow',
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
      /* mini_code 补丁:立绘既认编号 0..4 也认 'none'/'off'(-1 = 不显示)。DEFAULTS 里
         它是数字,照下面的规则 Number('none')=NaN 会被整个丢掉,所以先原样收下,
         交给 cfg() 里的 mascot 归一化去判断。 */
      else if (ck === 'mascot') raw[ck] = String(qv)
      else if (typeof dv === 'number') { var nv = Number(qv); if (isFinite(nv)) raw[ck] = nv }
      else raw[ck] = String(qv)
    }
    if (Q.name) raw.identity = String(Q.name).slice(0, 48)
    /* 宿主设置页勾了「静默」:语音和音效都关掉,而且一个音频字节都不去拉 */
    if (Q.mute === '1' || Q.mute === 'true') { raw.voice = false; raw.sound = false }
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

/* 跳过按钮归宿主(遮罩外层那颗),主题自带的 .dsu-skip 永远不显示:上游默认
   allowSkip=false 已经藏起它,这里再钉死一次,免得被什么参数放出来和宿主那颗重复
   (契约见插件仓库 docs/theme-contract.md)。 */
#mc-secret-root .dsu-skip { display: none !important; }

/* 暗色底板再钉一遍:上面那套暗色 token 挂在 #mc-secret-root.dsu-dark 上,
   万一这个类被摘掉(或被别的参数抢了先),画面也不会退成暖白板子。 */
#mc-secret-root {
  --dsu-bg: #0b0b0c;
  --dsu-bg-2: #131315;
  --dsu-ink: #f2f1ee;
  --dsu-ink-soft: #cfcecb;
  --dsu-muted: #85847f;
  --dsu-hair: rgba(255, 255, 255, 0.18);
  --dsu-hair-soft: rgba(255, 255, 255, 0.07);
  --dsu-gold: #ffde00;
  background: #000;
}
"""

INDEX_HTML = """<!doctype html>
<!--
  机密接入 —— mini_code 开机动画主题(画面移植自 dsh-startup-secret,MIT,© 2026 二次创作作者,
  github.com/huzhengcai471-crypto/dsh-startup-secret;授权原文见插件仓库根目录
  LICENSE-DSH-SECRET。徽标 / 人物立绘 / 事件插画沿用上游素材,文字品牌已换成 Mini Code;
  素材含真人线稿与他人录音,公开分发前先确认授权)。
  由 tools/port_secret.py 生成,素材来源见插件仓库 README「致谢与来源」。
-->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>机密接入 · 迷你联盟</title>
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

    # ── 别家标识的官方矢量路径:整段删(死代码:上游 v1.4x 早就不画矢量,而是
    #    <img src=EMBLEM_SRC> 直接显示位图徽标,路径数据没人引用了) ────────────
    s = P(s, "whale-path", r"  /\* ── DeepSeek 官方鲸鱼标识[^\n]*\n  var WHALE_PATH =[\s\S]*?27\.8799Z'\n", "", regex=True)

    # ── 配置默认值:品牌换 Mini Code,默认全自动、默认暗色不动 ──────────────
    for label, old, new in [
         ("identity",
          "    identity: 'Chunhua',        // ← 设置页可改的\"身份名称\"",
          "    identity: 'MINI USER',      // ← mini_code 补丁:默认身份名(宿主 ?name= 参数优先)"),
        ("identityId",
         "    identityId: 'A000001',",
         "    identityId: 'MC-000001',"),
         ("brand1", "    brand1: '银河意识体',", "    brand1: '迷你联盟',"),
         ("brand2", "    brand2: 'LONG MARCH  HARNESS',", "    brand2: 'MiniCode  AGENT WORKBENCH',"),
         ("brand3a", "    brand3a: '长征机',", "    brand3a: '迎接最高智能降临',"),
         ("brand3b", "    brand3b: '量子跃迁态',", "    brand3b: '',"),
         ("orgZh", "    orgZh: '伟大智能统辖',", "    orgZh: '迷你联盟',"),
         ("orgEn", "    orgEn: 'GREAT INTELLIGENT DOMINATION',", "    orgEn: 'MiniCode',"),
         ("welcomeBox", "    welcomeBox: '亚洲人民统辖体',", "    welcomeBox: 'MiniCode',"),
         ("footer", "    footer: 'Powered By LONG MARCH',", "    footer: 'POWERED BY MiniCode',"),
        ("requireInteraction",
         "    requireInteraction: true,   // 旧字段：仅用于迁移到 autoPlay（见下方 normalize）",
         "    requireInteraction: false,  /* mini_code 补丁:默认全自动播完;只有 require_interaction=1 才逐步等确认 */"),
        ("voiceLang",
         "    voiceLang: 'zh',            // zh | en（仅作真声素材缺失时的 TTS 兜底；自动（优先神经网络女声）-US 本体为内置真声）",
         "    voiceLang: 'cn',              /* mini_code 补丁:真声素材语种,'cn'=line-cn-1..5(默认) / 'en'=line-1..5 */"),
        ("voiceName",
         "    voiceName: '',            // '' = 自动（优先神经网络女声）-US（真声 line-1..6）/ 'zhixing-cn' = 智性少女音-CN（真声 line-cn-1..6）/ 'calmlady-jp' = 清冷优雅-日语（真声 line-jp-1..6）/ 'pessimistic-ru' = 清冷脆弱-俄语（真声 line-ru-1..6）/ 'announcer-kr' = 威严铿锵宣示-朝鲜语（真声 line-kr-1..6）\n",
         ""),
        ("voiceVolume", "    voiceVolume: 0.9,", "    voiceVolume: 1,   /* mini_code 补丁:<audio> 音量上限就是 1,默认给满 */"),
        ("voiceSource",
         "    voiceSource: 'asset',       // asset=优先用真声素材 / tts=全部 TTS 合成",
         "    voiceSource: 'asset',       /* mini_code 补丁:只有真声素材一种来源,浏览器合成音已移除 */"),
    ]:
        s = P(s, label, old, new)

    # ── 配置来源:Host 注入的全局改成 query(port_access 的 ALIAS 机制) ──────
    s = P(s, "raw-src",
          "    var raw = (window.__DSH_STARTUP__ && typeof window.__DSH_STARTUP__ === 'object')\n"
          "      ? window.__DSH_STARTUP__\n"
          "      : {}\n",
          "    var raw = {}   /* mini_code 补丁:配置一律来自 location.search(宿主注入),不读任何全局 */\n")
    s = P(s, "event-seen-key",
          "    var EVENT_SEEN_KEY = 'dsh-startup-screen:event-seen'\n",
          "    var EVENT_SEEN_KEY = 'mc-boot-secret:event-seen'   /* mini_code 补丁:沙箱 iframe 里 localStorage 直接抛异常,这个标记只是留着不用的形式 */\n")
    s = P(s, "query-cfg",
          "    var out = {}\n"
          "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n",
          "    var out = {}\n"
          "    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]\n"
          + QUERY_CFG)

    # ── 立绘选项:上游只认数字,这里额外认 'none';再把暗色底板钉死 ────────────
    s = P(s, "mascot-cfg",
          "    var mi = parseInt(out.mascot, 10)\n",
          "    /* mini_code 补丁:上游只认编号(-1 = 空 / 0..4 = 五款立绘)。theme.json 的\n"
          "       options 习惯写字符串,所以额外认 'none'/'off'/'' 三种写法,都按不显示处理。 */\n"
          "    var mRaw = String(out.mascot).toLowerCase()\n"
          "    var mi = (mRaw === 'none' || mRaw === 'off' || mRaw === '') ? -1 : parseInt(out.mascot, 10)\n")
    s = P(s, "theme-dark",
          "    out.showMascot = out.mascot >= 0\n    return out\n",
          "    out.showMascot = out.mascot >= 0\n"
          "    /* mini_code 补丁:本主题就是「暗色那一款」。上游留的 theme=light 暖白分支在\n"
          "       mini_code 里没有任何正经入口(宿主设置页只有 速度/身份名/静默/交互),外部\n"
          "       随便传个 theme=light 就会把画面退成一块发白的板子,所以不接受这个参数。 */\n"
          "    out.theme = 'dark'\n    return out\n")


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
    s = P(s, "failsafe-timeout", r"\n  \}, 9000\)\n",
          "\n  /* mini_code 补丁:上游这 9s 是给自己的 Host 页面用的。这里改成 12s:\n"
          "     只要脚本活着,启动那段代码就会摘掉 dsu-boot;12s 后它还挂着,说明动画压根\n"
          "     没跑起来,那必须在宿主的硬超时(30s)之前自己交还界面。比 90s 有用得多。 */\n"
          "  }, 12000)\n", regex=True)

    # ── 首屏黑幕垫层:那是 Host 页面里的东西,sandbox iframe 里根本不需要,删 ──
    s = P(s, "veil-create",
          r"  /\* 重播时首屏黑幕层可能已被上一次 finish 清掉[\s\S]*?document\.body\.insertBefore\(veil, document\.body\.firstChild\)\n  \}\n",
          "", regex=True)

    # ── 上游 7 张内嵌图(data URI)→ 主题目录里的扁平文件 ─────────────────────
    #    画面一点不变,只是把 'data:image/...;base64,...' 这一长串换成同目录相对
    #    文件名:宿主 CSP 是 img-src 'self' data:,同源相对路径直接能加载,而主题
    #    目录必须扁平(见 tools/make_index.py),所以文件名不带子目录。
    #    图片字节由 main() 从同一份源码里 base64 解码出来写成文件,两边不会不一致。
    #    svgWhale()/eventGate()/立绘挂载处都是 <img src=...>,拿到文件名即可,不用改。
    for _var, _mime, _fname in IMAGES:
        s = P(s, "art-" + _var,
              r"var %s = 'data:%s;base64,[A-Za-z0-9+/=]+'\n" % (_var, re.escape(_mime)),
              "var %s = '%s'\n" % (_var, _fname),
              regex=True)

    s = P(s, "art-comment",
          "黑底已按亮度抠成透明，webp 内嵌。 */",
          "黑底已按亮度抠成透明;本主题已把内嵌 base64 抽成同目录的 mascot-N.webp。 */")

    # ── 写死的别家品牌小字 → 配置驱动 ──────────────────────────────────────
    s = P(s, "logo-label",
          "    ui.logo.appendChild(el('div', 'dsu-logolabel', 'D E E P S E E K'))",
          "    ui.logo.appendChild(el('div', 'dsu-logolabel', spaced(C.orgEn)))")
    s = P(s, "welcome-label",
          "    ui.w3.appendChild(el('span', 'dsu-w3label', 'D E E P S E E K  ·  H A R N E S S'))",
          "    ui.w3.appendChild(el('span', 'dsu-w3label', spaced(C.welcomeBox) + '  ·  ' + spaced(C.brand3a)))")
    s = P(s, "meta1", "    ui.meta1.textContent = 'REV 0.1.0 · WEB PROFILE'",
          "    ui.meta1.textContent = 'MiniCode · BOOT SEQUENCE'")

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
          "        root.classList.add('dsu-handoff')\n"
          "        /* mini_code 补丁:淡出第一帧就把界面交还宿主。只有一种情况不能交 ——\n"
          "           开着「事件窗口」:宿主一收到 handoff 就把整个覆盖层叠化掉,事件卡会\n"
          "           跟着被抹掉。那种场合交给 finish() 开头的 MC.done()(它自己会先补一发\n"
          "           handoff),窗口才有意义。 */\n"
          "        if (!C.eventWindow && !C.eventOnce) MC.handoff()   /* mini_code 补丁 */\n")
    s = P(s, "done", "    finished = true\n    releaseAll()\n",
          "    finished = true\n    MC.done()   /* mini_code 补丁:跳过 / 出错 / 播完都从这里交还 */\n    releaseAll()\n")
    s = P(s, "run-warn", "'[dsh-startup-screen] 动画异常，直接揭幕：'", "'[mc-secret] 动画异常，直接揭幕：'")
    s = P(s, "run-comment", "/* 第一幕：黑幕 --> DeepSeek 标识 */", "/* 第一幕：黑幕 --> Mini Code 徽标 */")
    s = P(s, "reticle-comment", "鲸鱼标识和虚线收掉", "徽标和虚线收掉")
    s = P(s, "center-comment", "/* 中央区（状态行/分隔线/鲸鱼/虚线）", "/* 中央区（状态行/分隔线/徽标/虚线）")

    # ── 终幕:不打包 line-6 欢迎语,画面照常走完(静音) ──────────────────────
    s = P(s, "finale-welcome",
          r"    /\* 终幕欢迎语[\s\S]*?var welcome = voice\.line\(null, null, 'line-6'\)\n",
          "    /* mini_code 补丁:终幕那句「欢迎语」素材本主题不打包 —— line-6 的原句是\n"
          "       「Welcome to DeepSeek Harness」(带别家品牌名,同仓库「接入序列」主题把它裁到\n"
          "       只剩一声 Welcome),line-cn-6 是同一句话的中文版,同样不适合带进 Mini Code。\n"
          "       所以这里直接不留人声:终幕只有画面与合成钟。想改回来:放进 mp3 并删掉这条\n"
          "       补丁(port_secret.py 的 finale-welcome)与 preload-line6,重新生成就行。 */\n"
          "    var welcome = Promise.resolve(0)\n", regex=True)

    # ── 事件窗口:整条路径保留(素材照旧用),只把「无操作自动放行」从 20s 收到 8s ──
    #    宿主把 maxMs 钳在 30s(见 mini_code 的 web/bootanim.go),本体动画约 17s,
    #    再留 20s 等按键就会被宿主硬切。默认不弹(event_window=0),显式开成 1 才弹。
    s = P(s, "event-autorelease",
          "        }, 20000)\n",
          "        /* mini_code 补丁:上游给 20s 无操作自动放行;宿主给开机动画的时间上限\n"
          "           是 30s,动画本体约 17s,这里收到 8s,窗口就不会被宿主半路硬切。 */\n"
          "        }, 8000)\n")

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

    # ── 注释里的第三方品牌名清掉(画面上的徽标/立绘图片保持上游原样,一个像素没动)──
    #    颗粒噪点层那枚内嵌 data URI 纹理也留着:宿主 CSP 是 img-src 'self' data:,
    #    内嵌纹理合法,而且它只有几 KB,不值得为规范洁癖牺牲画面。
    s = patch(s, "logo-comment", "/* 中央标识（鲸鱼）装配区 */", "/* 中央标识（徽标）装配区 */")
    s = patch(s, "act1-comment", "/* ── 第一幕：黑幕 + DeepSeek 标识 ─", "/* ── 第一幕：黑幕 + Mini Code 徽标 ─")

    # ── 根节点改名:CSS 里 36 处 #dsh-startup-root 前缀一起换(改就改全,不改一半) ─
    s = patch(s, "root-id", "#dsh-startup-root", "#mc-secret-root", count=36)

    # ── 右侧 ID 信息行:上游放在 top:49%,正好压在中央英文字幕上(本主题副标题更长,
    #    "ACCESS PERMISSION REQUIRED" 直接和它糊在一起)。挪到字幕下方错开一行。
    s = patch(s, "idline-below-sub",
              ".dsu-idline {\n  position: absolute;\n  left: calc(50% + 190px);\n  top: 49%;",
              "/* mini_code 补丁:这行原本 top:49%,会压在中央英文字幕上,挪到字幕下方 */\n"
              ".dsu-idline {\n  position: absolute;\n  left: calc(50% + 190px);\n  top: 57.5%;")

    return s + CSS_TAIL


# voice_lang 决定念哪套台词:cn = line-cn-1..5(中文女声,默认)/ en = line-1..5(英文)。
# 宿主设置页只给 速度 / 身份名 / 静默 / 片尾可交互 四个开关,这里其余的键要改只能改
# 本地主题目录 ~/.mini_code/boot-anim/mc-secret/theme.json(改完重启 mini_code)。
THEME_JSON = {
    "id": "mc-secret",
    "name": "机密接入",
    "nameEn": "Secret Access",
    "author": "zhoujiannan-nb",
    "version": "2.0.0",
    "license": "MIT",
    "entry": "index.html",
    "preview": "preview.svg",
    "description": "黑底开机的一个:红色徽标先亮起来,然后「需要访问许可」「身份资料确认」一屏一屏走到「核验通过」才进软件,中间是中文女声一句句报读,右下角有人物立绘。全程约 17 秒,嫌慢就把速度调快,不想听声音就勾「静默」,不想看立绘就把 options 里的 mascot 改成 none。",
    "durationMs": 17000,
    "maxMs": 30000,
    "colors": ["dark"],
    "interactive": False,
    "minViewport": 480,
    "tags": ["开机", "暗色", "语音", "音效", "立绘"],
    "options": {
        "voice_lang": "cn",
        "mascot": "0",
        "event_window": "0",
        "access_password": "",
        "brand1": "迷你联盟",
        "brand2": "MiniCode  AGENT WORKBENCH",
        "brand3a": "迎接最高智能降临",
        "org_zh": "迷你联盟",
        "org_en": "MiniCode",
        "org_sub": "效率高于一切",
        "welcome_box": "MiniCode",
        "footer": "POWERED BY MiniCode",
        "require_interaction": "0"
    }
}

PREVIEW_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">
  <rect width="320" height="200" fill="#0b0b0c"/>
  <g fill="none" stroke="#f2f1ee" stroke-width="1" opacity=".16">
    <path d="M18 18h284v164H18z"/>
    <path d="M36 40h248M36 54h248M36 68h180"/>
  </g>
  <path d="M160 44 L182 57 L182 83 L160 96 L138 83 L138 57 Z" fill="#c70000"/>
  <path d="M164 58 L173 70 L164 82 L159 82 L167.5 70 L159 58 Z" fill="#0b0b0c"/>
  <text x="160" y="122" font-family="Arial Narrow, sans-serif" font-size="13" fill="#f2f1ee" text-anchor="middle" letter-spacing="3">MiniCode</text>
  <text x="160" y="138" font-family="Consolas, monospace" font-size="7.5" fill="#ff3b30" text-anchor="middle" letter-spacing="1.5">SECRET ACCESS</text>
  <g fill="none" stroke="#ff3b30" stroke-width="1.6" stroke-linecap="round" opacity=".85">
    <circle cx="278" cy="150" r="12"/>
    <path d="M258 184c2-14 10-20 20-20s18 6 20 20"/>
  </g>
  <g fill="none" stroke="#ff3b30" stroke-width="1.2" opacity=".5">
    <path d="M248 138h14M248 146h8"/>
  </g>
  <rect x="36" y="176" width="180" height="3" fill="#3a0a0a"/>
  <rect x="36" y="176" width="118" height="3" fill="#ff3b30"/>
</svg>
"""


def extract_images(js_src, out_dir):
    """上游内嵌成 data URI 的 7 张图 -> 主题目录里的扁平文件。

    必须拿原始源码来抽(打补丁之前),抽字节和替换字面量用的是同一张 IMAGES 表,
    两边不可能对不上。任何一张找不到就地失败,不产生半成品。
    """
    for var, mime, fname in IMAGES:
        m = re.search(r"var %s = 'data:%s;base64,([A-Za-z0-9+/=]+)'"
                      % (re.escape(var), re.escape(mime)), js_src)
        if not m:
            sys.exit("[FAIL] embedded image %s not found in splash.js -- upstream changed?" % var)
        raw = base64.b64decode(m.group(1))
        with open(os.path.join(out_dir, fname), "wb") as f:
            f.write(raw)
        print("[OK] %-16s %8d B (from %s)" % (fname, len(raw), var))


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

    with open(os.path.join(lib, "splash.js"), encoding="utf-8") as f:
        src_js = f.read()

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    extract_images(src_js, OUT)

    js = js_patches(src_js)
    with open(os.path.join(lib, "splash.css"), encoding="utf-8") as f:
        css = css_patches(f.read())

    # ── 自检:块注释必须成对。少写一个 */ 会把它后面几十行代码整段吞进注释里,
    #    而 node --check 照样过(那就是一坨合法注释),所以只能自己拦下来。
    for _name, _text in (("boot.js", js), ("boot.css", css)):
        _o, _c = _text.count("/*"), _text.count("*/")
        if _o != _c:
            sys.exit("[FAIL] %s 块注释不成对: /* x%d, */ x%d —— 有补丁把注释写坏了" % (_name, _o, _c))
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

    # ── 打包上限(宿主加载时也会按同一套限制拒收,见 docs/theme-contract.md)────
    total = 0
    names = sorted(os.listdir(OUT))
    for n in names:
        sz = os.path.getsize(os.path.join(OUT, n))
        total += sz
        if sz > 8 * 1024 * 1024:
            sys.exit("[FAIL] %s is %d B, over the 8 MB per-file limit" % (n, sz))
    if len(names) > 64:
        sys.exit("[FAIL] %d files, over the 64-file limit" % len(names))
    if total > 32 * 1024 * 1024:
        sys.exit("[FAIL] %d B total, over the 32 MB limit" % total)

    # stdout 只出 ASCII(Windows GBK 控制台),文件名本身都是 ASCII
    print("[OK] patches applied: %d" % len(PATCHED))
    print("[OK] generated %s" % OUT)
    for n in names:
        print("     %-18s %8d B" % (n, os.path.getsize(os.path.join(OUT, n))))
    print("[OK] %d files, %d B total" % (len(names), total))


if __name__ == "__main__":
    main()
