/* ============================================================================
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
(function () {
  'use strict'


  var ROOT_ID = 'mc-secret-root'

  /* ── mini_code 补丁:宿主通信 + query 配置 ─────────────────────────────
     协议见插件仓库 docs/theme-contract.md:
       parent.postMessage({mc:"boot-anim", type:"ready|step|handoff|done", id}, "*")
     ready   首帧已经画出来了(宿主这时才显示跳过按钮)
     handoff 开始交还界面(必须发生在淡出那一帧,宿主此刻叠化)
     done    收尾。跳过按钮归宿主画,主题自己不画(所以下面 allowSkip=false) */
  var Q = (function () {
    var out = {}
    try {
      var rawq = String(location.search || '').replace(/^\?/, '')
      if (!rawq) return out
      var parts = rawq.split('&')
      for (var i = 0; i < parts.length; i++) {
        if (!parts[i]) continue
        var kv = parts[i].split('=')
        var k = decodeURIComponent(kv[0].replace(/\+/g, ' '))
        var v = kv.length > 1 ? decodeURIComponent(kv.slice(1).join('=').replace(/\+/g, ' ')) : ''
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
    var words = String(t || '').replace(/\s+/g, ' ').replace(/^ | $/g, '').split(' ')
    var out = []
    for (var i = 0; i < words.length; i++) out.push(words[i].split('').join('\u00a0'))
    return out.join('\u00a0\u00a0')
  }


  /* ── 默认配置（与 Host 侧 lib/index.js 的 DEFAULTS 保持一致）──────────── */
  var DEFAULTS = {
    enabled: true,
    mode: 'session',            // session | daily（原 always 已删除）
    theme: 'dark',              // light | dark
    speed: 1,
    requireInteraction: false,  /* mini_code 补丁:默认全自动播完;只有 require_interaction=1 才逐步等确认 */
    /* 出厂留空：老配置（只有 requireInteraction）必须能被识别并迁移，
       写死 'full' 会让 requireInteraction=true 的老用户被悄悄改成全自动。 */
    autoPlay: '',               // full=完全自动播放 / once=仅需点击一次进入（需空密码）/ off=不自动播放
    allowSkip: false,
    sound: true,                // 界面音效（WebAudio 合成，无音频文件）
    soundVolume: 0.5,
    voice: true,                // 女声播报
    voiceLang: 'en',            /* mini_code 补丁:真声素材语种 en=line-1..5 / cn=line-cn-1..5(theme.json 的 voice_lang) */
    voiceRate: 0.88,            // 电影旁白档：比朗读慢，字与字之间才有重量
    voicePitch: 0.85,           // 压低音调，深沉的 AI 女声
    voiceVolume: 1,   /* mini_code 补丁:<audio> 音量上限就是 1,默认给满 */
    voiceCue: true,             // 念台词前的一声轻提示
    sfx: 'audio',               // audio=真素材（用户音频里抠的音效）/ synth=现场合成
    voiceSource: 'asset',       /* mini_code 补丁:只有真声素材一种来源,浏览器合成音已移除 */
    voiceLead: 240,             // 提示音之后留一小段空白再开口
    mascot: 'cat',              /* mini_code 补丁:立绘款式 'cat'=自绘电路猫 / 'none'=不显示 */
    identity: '哈基米指挥官',    // ← mini_code 补丁:默认身份名(宿主 name= 参数优先)
    identityId: 'MC-000001',
    accessLevel: '最高权限',
    identityPassword: '',       // ← 第二步身份确认的访问密码（空 = 不启用）
    brand1: '迷你代码',
    brand2: 'MINI CODE  AGENT WORKBENCH',
    brand3a: '本地智能体',
    brand3b: '离线运行',
    orgZh: '本地智能体工作台',
    orgEn: 'LOCAL AGENT WORKBENCH',
    orgSub: '效率高于一切',
    welcomeBox: 'MINI CODE',
    footer: 'POWERED BY MINI CODE',
    accent: '#c70000',
    glitchA: '#ff3b30',
    glitchB: '#ce0912'
  }

  /* ── 序列脚本：中文主字 + 英文等宽字幕 + 底部日志 ───────────────────────
     `say` 是专门给语音播报用的自然语句（照着参考片里女声念状态行的节奏，
     正好卡在各自文字出现的时间点上）。 */
  /* ── 序列脚本 ──────────────────────────────────────────────────────────
     5 句播报与素材一一对应:line-1 需要访问许可 / line-2 身份资料确认
     line-3 接收访问需求 / line-4 开始读取权限 / line-5 读取完毕核验通过。
     voice_lang='en' 用 line-N,'cn' 用 line-cn-N(cnAsset 负责前缀映射)。
     素材拿不到就安静地不出声,绝不回落浏览器合成音。 */
  var STEPS = [
    {
      zh: '需要访问许可',
      en: 'ACCESS PERMISSION REQUIRED',
      say: 'Access permission required.',
      audio: 'line-1',
      log: '等待用户授权…',
      logEn: 'AWAITING OPERATOR CONSENT',
      badge: 'AUTHORIZATION',
      action: 'grant',
      btnZh: '授予访问权限',
      btnEn: 'GRANT ACCESS',
      hold: 900,
      progress: 0.34
    },
    {
      zh: '身份资料确认',
      en: 'IDENTITY VERIFICATION',
      say: 'Identity verification.',
      audio: 'line-2',
      log: '核对身份资料…',
      logEn: 'MATCHING OPERATOR RECORD',
      badge: 'IDENTITY',
      action: 'confirm',
      btnZh: '确认身份',
      btnEn: 'CONFIRM IDENTITY',
      hold: 700,
      progress: 0.5
    },
    {
      zh: '接收访问需求',
      en: 'ACCESS REQUEST RECEIVED',
      say: 'Access request received.',
      audio: 'line-3',
      log: '接收访问需求，建立会话通道…',
      logEn: 'HANDSHAKE ESTABLISHED',
      badge: 'REQUEST',
      action: 'auto',
      hold: 1200,
      progress: 0.66,
      assembleLogo: true
    },
    {
      zh: '开始读取权限',
      en: 'PERMISSION READ STARTED',
      say: 'Beginning permission read.',
      audio: 'line-4',
      log: '开始读取权限，索引工作区与会话…',
      logEn: 'READING PERMISSION SET',
      badge: 'READ',
      action: 'auto',
      hold: 1200,
      progress: 0.8,
      hex: true
    },
    {
      zh: '读取完毕 · 核验通过',
      en: 'READ COMPLETE · VERIFIED',
      say: 'Read complete. Verification passed.',
      audio: 'line-5',
      log: '读取完毕，核验通过，权限已授予',
      logEn: 'PERMISSION AUTHORIZED',
      badge: 'VERIFY',
      action: 'auto',
      hold: 1600,
      progress: 0.93,
      reticle: true
    }
  ]

  /* mini_code 补丁:主题只带中英两套素材,voice_lang='cn' 走 line-cn-N,否则 line-N。
     幂等形态保留:重复解析结果不变,避免前缀叠加。 */
  function cnAsset(n) {
    if (!n) return n
    var m = /^line-(?:cn-)?([0-9]+)$/.exec(n)
    if (!m) return n
    return (C.voiceLang === 'cn' ? 'line-cn-' : 'line-') + m[1]
  }

  function cfg() {
    var raw = {}   /* mini_code 补丁:配置一律来自 location.search(宿主注入),不读任何全局 */
    var out = {}
    for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) out[k] = DEFAULTS[k]
    /* mini_code 补丁:宿主的开机动画只通过 query 传参
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
    for (var k2 in raw) {
      if (Object.prototype.hasOwnProperty.call(raw, k2) && raw[k2] !== undefined && raw[k2] !== null) {
        out[k2] = raw[k2]
      }
    }
    out.speed = Math.min(3, Math.max(0.35, Number(out.speed) || 1))
    out.identity = String(out.identity || DEFAULTS.identity).slice(0, 48)
    /* 代号取身份名称里的字母数字；纯中文名字取不到时退回 OPERATOR */
    out.identityId = String(out.identityId || out.identity).toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 12)
    if (!out.identityId) out.identityId = 'OPERATOR'
    /* 身份密码：空字符串 = 不启用密码校验；非空时第二步需输对才能继续 */
    out.identityPassword = String(out.identityPassword || '').slice(0, 128)

    /* ── 自动播放三档（2026-10-18）──────────────────────────────────────
       full = 完全自动播放：五步全自动，不需要任何操作
       once = 仅需点击一次进入：开头停下来等一次确认（要求身份密码为空）
       off  = 不自动播放：第 1、2 步都等用户确认（相当于旧的「需要人工确认」）
       旧配置只有 requireInteraction(true/false)，按它迁移，老用户无感。 */
    var ap = String(out.autoPlay || '')
    if (ap !== 'full' && ap !== 'once' && ap !== 'off') {
      ap = (out.requireInteraction === false || out.requireInteraction === 'false' || out.requireInteraction === 0)
        ? 'full'
        : 'off'
    }
    out.autoPlay = ap
    /* 只有「不自动播放」才需要逐步停止；另外两档都不在第二步停 */
    out.requireInteraction = ap === 'off'

    /* mini_code 补丁:立绘只有自绘「电路猫」一款,除 'none' 外一律按猫处理 */
    out.mascot = String(out.mascot).toLowerCase() === 'none' ? 'none' : 'cat'
    out.showMascot = out.mascot !== 'none'
    return out
  }

  var C = cfg()



  /* 最后一道保险：无论前面哪一步抛异常，都不许把用户留在黑幕里 */
  setTimeout(function () {
    try {
      var r = document.getElementById(ROOT_ID)
      if (r && r.classList && r.classList.contains('dsu-boot')) {
        MC.done()   /* mini_code 补丁:卡住了也得把界面还给宿主 */
        if (r.parentNode) r.parentNode.removeChild(r)
        document.documentElement.classList.remove('dsu-lock')
        if (document.body) document.body.style.overflow = ''
      }
    } catch (e) { /* 兜底本身不许再抛 */ }
  }, 90000)

  /* ── 小工具 ───────────────────────────────────────────────────────────── */
  function el(tag, cls, text) {
    var n = document.createElement(tag)
    if (cls) n.className = cls
    if (text != null) n.textContent = text
    return n
  }

  /* ── 自绘「电路猫」立绘:红色描边线稿、透明底、纯内联 SVG ────────────────
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


  /* ── mini_code 标识:六边形芯片,中间镂空一个 ">"(终端提示符) ─────────
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

  /** 逐字渐显：比逐字截断更稳（居中排版不会因为字宽变化而抖动） */
  function typeIn(host, text, stagger) {
    host.textContent = ''
    var frag = document.createDocumentFragment()
    var n = 0
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i)
      if (ch === ' ') {
        frag.appendChild(document.createTextNode('\u00a0'))
        continue
      }
      var s = el('span', 'dsu-ch', ch)
      s.style.transitionDelay = Math.round(n * stagger) + 'ms'
      frag.appendChild(s)
      n++
    }
    host.appendChild(frag)
  }

  function setIn(node, on, cls) {
    if (!node) return
    node.classList.toggle(cls || 'dsu-in', !!on)
  }

  /* ── DOM 搭建 ─────────────────────────────────────────────────────────── */
  var root = document.getElementById(ROOT_ID)
  if (!root) {
    root = el('div')
    root.id = ROOT_ID
    root.className = 'dsu-root'
    document.body.appendChild(root)
  }
  root.classList.add('dsu-boot')
  root.classList.toggle('dsu-dark', C.theme === 'dark')
  root.style.setProperty('--dsu-speed', String(C.speed))
  root.style.setProperty('--dsu-accent', C.accent)
  root.style.setProperty('--dsu-glitch-a', C.glitchA)
  root.style.setProperty('--dsu-glitch-b', C.glitchB)

  var ui = {}
  var clockTimer = null
  var html =
    '<div class="dsu-plate"></div>' +
    '<div class="dsu-vignette"></div>' +
    '<div class="dsu-watermark"></div>' +
    '<div class="dsu-grain"></div>' +
    '<div class="dsu-black">' +
      '<div class="dsu-black-inner"></div>' +
      '<div class="dsu-sweep"></div>' +
    '</div>' +
    '<div class="dsu-wash"></div>' +
    '<header class="dsu-brand">' +
      '<div class="dsu-brand-1"></div><div class="dsu-brand-2"></div>' +
      '<div class="dsu-brand-3"><b></b><span></span></div>' +
    '</header>' +
    '<div class="dsu-stepcount">[ 00 / 06 ] INIT</div>' +
    '<div class="dsu-center">' +
      '<div class="dsu-status"><span class="dsu-status-zh"></span><i class="dsu-caret"></i></div>' +
      '<div class="dsu-sub-en"></div>' +
      '<div class="dsu-rule"></div>' +
      '<div class="dsu-logo"></div>' +
      '<div class="dsu-dots" hidden></div>' +
    '</div>' +
    '<div class="dsu-idline"></div>' +
    '<div class="dsu-reticle"></div>' +
    '<div class="dsu-hex"></div>' +
    '<div class="dsu-welcome">' +
      '<div class="dsu-w1">WELCOME TO</div>' +
      '<div class="dsu-w2"></div>' +
      '<div class="dsu-w3"></div>' +
      '<div class="dsu-w4"></div>' +
    '</div>' +
    '<div class="dsu-action">' +
      '<div class="dsu-card" hidden></div>' +
      '<button class="dsu-btn" type="button">' +
        '<span class="dsu-btn-zh"></span><span class="dsu-btn-en"></span>' +
      '</button>' +
      '<div class="dsu-hint"></div>' +
    '</div>' +
    '<div class="dsu-frame">' +
      '<i class="dsu-corner dsu-c-tl"></i><i class="dsu-corner dsu-c-tr"></i>' +
      '<i class="dsu-corner dsu-c-bl"></i><i class="dsu-corner dsu-c-br"></i>' +
      '<div class="dsu-scanline"></div>' +
    '</div>' +
    '<div class="dsu-slats"></div>' +
    '<div class="dsu-voice"><i></i><i></i><i></i><i></i><i></i></div>' +
    '<div class="dsu-meta"><span class="dsu-meta-1"></span><span class="dsu-meta-2"></span></div>' +
    '<div class="dsu-skip">SKIP ▸</div>' +
    '<footer class="dsu-foot"><span></span><i></i></footer>' +
    '<div class="dsu-subtitle">' +
      '<span class="dsu-sub-zh"></span><span class="dsu-sub-en2"></span>' +
    '</div>' +
    '<div class="dsu-progress"><i></i></div>' +
    '<div class="dsu-bloom"></div>' +
    '<div class="dsu-streak"></div>' +
    '<div class="dsu-flash"></div>' +
    '<div class="dsu-mascot" hidden></div>'

  root.innerHTML = html

  function q(sel) { return root.querySelector(sel) }
  ui.plate = q('.dsu-plate')
  ui.watermark = q('.dsu-watermark')
  ui.black = q('.dsu-black')
  ui.blackInner = q('.dsu-black-inner')
  ui.sweep = q('.dsu-sweep')
  ui.wash = q('.dsu-wash')
  ui.flash = q('.dsu-flash')
  ui.bloom = q('.dsu-bloom')
  ui.streak = q('.dsu-streak')
  /* mini_code 补丁:右下角立绘 = 自绘「电路猫」红线稿(内联 SVG,无图片资源)。
     设置 mascot='none' 时整块不渲染(上游「立绘=空」的行为)。 */
  ui.mascot = q('.dsu-mascot')
  if (C.showMascot) {
    ui.mascot.setAttribute('data-mascot', 'cat')
    ui.mascot.innerHTML = MASCOT_SVG
  } else {
    ui.mascot.hidden = true
  }
  ui.vignette = q('.dsu-vignette')
  ui.brand = q('.dsu-brand')
  ui.center = q('.dsu-center')
  ui.brand1 = q('.dsu-brand-1')
  ui.brand2 = q('.dsu-brand-2')
  ui.brand3b = q('.dsu-brand-3 b')
  ui.brand3s = q('.dsu-brand-3 span')
  ui.stepcount = q('.dsu-stepcount')
  ui.status = q('.dsu-status')
  ui.statusZh = q('.dsu-status-zh')
  ui.caret = q('.dsu-caret')
  ui.subEn = q('.dsu-sub-en')
  ui.rule = q('.dsu-rule')
  ui.logo = q('.dsu-logo')
  ui.dots = q('.dsu-dots')
  ui.idline = q('.dsu-idline')
  ui.reticle = q('.dsu-reticle')
  ui.hex = q('.dsu-hex')
  ui.welcome = q('.dsu-welcome')
  ui.w1 = q('.dsu-w1')
  ui.w2 = q('.dsu-w2')
  ui.w3 = q('.dsu-w3')
  ui.w4 = q('.dsu-w4')
  ui.action = q('.dsu-action')
  ui.card = q('.dsu-card')
  ui.btn = q('.dsu-btn')
  ui.btnZh = q('.dsu-btn-zh')
  ui.btnEn = q('.dsu-btn-en')
  ui.hint = q('.dsu-hint')
  ui.skip = q('.dsu-skip')
  ui.foot = q('.dsu-foot')
  ui.footText = q('.dsu-foot span')
  ui.subZh = q('.dsu-sub-zh')
  ui.subEn2 = q('.dsu-sub-en2')
  ui.progress = q('.dsu-progress')
  ui.bar = q('.dsu-progress i')
  ui.frame = q('.dsu-frame')
  ui.scanline = q('.dsu-scanline')
  ui.slats = q('.dsu-slats')
  ui.voice = q('.dsu-voice')
  ui.meta = q('.dsu-meta')
  ui.meta1 = q('.dsu-meta-1')
  ui.meta2 = q('.dsu-meta-2')

  /* 内容填充 */
  ui.brand1.textContent = C.brand1
  ui.brand2.textContent = C.brand2
  ui.brand3b.textContent = C.brand3a
  ui.brand3s.textContent = C.brand3b
  ui.footText.textContent = C.footer
  ui.w2.textContent = C.welcomeBox
  ui.w4.textContent = '欢迎 ' + C.identity + ' 访问'
  ui.idline.textContent = '· ID CONFIRMED : ' + C.identityId

  ;(function blackStage() {
    var inner = ui.blackInner
    var mark = svgMark('dsu-mark')
    inner.appendChild(mark)
    inner.appendChild(el('div', 'dsu-black-zh', C.orgZh))
    var en = el('div', 'dsu-black-en', C.orgEn)
    inner.appendChild(en)
    inner.appendChild(el('div', 'dsu-black-sub', C.orgSub))
    ui.blackEn = en
  })()

  ;(function logoStage() {
    ui.logo.appendChild(svgMark())
    ui.logo.appendChild(el('div', 'dsu-logolabel', spaced(C.orgEn)))
  })()

  ;(function welcomeLogo() {
    ui.w3.appendChild(svgMark())
    ui.w3.appendChild(el('span', 'dsu-w3label', spaced(C.welcomeBox) + '  ·  ' + spaced(C.brand3a)))
  })()

  ;(function watermark() {
    var boxes = [
      [0.60, 0.02, 0.16, 0.96], [0.78, 0.02, 0.16, 0.96], [0.96, 0.02, 0.16, 0.96],
      [0.05, 0.02, 0.10, 0.5]
    ]
    for (var i = 0; i < boxes.length; i++) {
      var b = boxes[i]
      var n = el('div', 'dsu-wm')
      n.style.left = (b[0] * 100) + '%'
      n.style.top = (b[1] * 100) + '%'
      n.style.width = (b[2] * 100) + '%'
      n.style.height = (b[3] * 100) + '%'
      ui.watermark.appendChild(n)
    }
  })()

  /* 左侧六格阶段柱 + 品牌块下方的小字数据行 + 实时时钟 */
  ;(function slatsAndMeta() {
    for (var i = 0; i < STEPS.length + 1; i++) ui.slats.appendChild(el('i', 'dsu-slat'))
    ui.meta1.textContent = 'MINI CODE · BOOT SEQUENCE'
    paintClock()
    clockTimer = setInterval(paintClock, 1000)
  })()

  ;(function reticle() {
    var ns = 'http://www.w3.org/2000/svg'
    var svg = document.createElementNS(ns, 'svg')
    svg.setAttribute('viewBox', '0 0 400 400')
    function arc(cx, cy, r, a0, a1, cls, cap) {
      var rad = function (d) { return (d - 90) * Math.PI / 180 }
      var x0 = cx + r * Math.cos(rad(a0)), y0 = cy + r * Math.sin(rad(a0))
      var x1 = cx + r * Math.cos(rad(a1)), y1 = cy + r * Math.sin(rad(a1))
      var large = (a1 - a0) > 180 ? 1 : 0
      var p = document.createElementNS(ns, 'path')
      p.setAttribute('d', 'M' + x0.toFixed(2) + ' ' + y0.toFixed(2) +
        ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x1.toFixed(2) + ' ' + y1.toFixed(2))
      p.setAttribute('class', cls)
      if (cap) p.setAttribute('stroke-linecap', cap)
      return { node: p, x: x1, y: y1, x0: x0, y0: y0 }
    }
    var gA = document.createElementNS(ns, 'g')
    gA.setAttribute('class', 'dsu-ret-rot-a')
    /* 300° 弧，缺口留在正下方 6 点钟方向：底部字幕永远不会被压到，
       弧末端圆点落在 5 点钟位置，和原片一致。 */
    var a = arc(200, 200, 150, 215, 505, 'dsu-ring-a', 'round')
    gA.appendChild(a.node)
    var da = document.createElementNS(ns, 'circle')
    da.setAttribute('class', 'dsu-dot-a')
    da.setAttribute('cx', a.x.toFixed(2)); da.setAttribute('cy', a.y.toFixed(2)); da.setAttribute('r', '7')
    gA.appendChild(da)
    svg.appendChild(gA)

    var gB = document.createElementNS(ns, 'g')
    gB.setAttribute('class', 'dsu-ret-rot-b')
    var b = arc(200, 200, 104, 200, 490, 'dsu-ring-b', 'round')
    gB.appendChild(b.node)
    var db = document.createElementNS(ns, 'circle')
    db.setAttribute('class', 'dsu-dot-b')
    db.setAttribute('cx', b.x0.toFixed(2)); db.setAttribute('cy', b.y0.toFixed(2)); db.setAttribute('r', '4')
    gB.appendChild(db)
    svg.appendChild(gB)

    var gC = document.createElementNS(ns, 'g')
    var bl = arc(200, 200, 62, 118, 242, 'dsu-bracket', 'round')
    var br = arc(200, 200, 62, 298, 62, 'dsu-bracket', 'round')
    gC.appendChild(bl.node); gC.appendChild(br.node)
    svg.appendChild(gC)

    var pts = [[152, 132], [252, 268], [278, 150]]
    for (var i = 0; i < pts.length; i++) {
      var c = document.createElementNS(ns, 'circle')
      c.setAttribute('class', 'dsu-dot-o')
      c.setAttribute('cx', pts[i][0]); c.setAttribute('cy', pts[i][1]); c.setAttribute('r', '2.8')
      svg.appendChild(c)
    }
    ui.reticle.appendChild(svg)
  })()

  /* ── 时间线引擎 ───────────────────────────────────────────────────────── */
  var timers = []
  var waiters = []
  var skipped = false
  var finished = false
  var hexTimer = null

  function ms(base) { return Math.round(base / C.speed) }

  function wait(base) {
    return new Promise(function (resolve) {
      if (skipped) return resolve()
      var done = false
      function fin() {
        if (done) return
        done = true
        var i = waiters.indexOf(fin)
        if (i >= 0) waiters.splice(i, 1)
        resolve()
      }
      var t = setTimeout(fin, Math.max(0, ms(base)))
      timers.push(t)
      waiters.push(fin)
    })
  }

  function waitAction(step) {
    return new Promise(function (resolve) {
      if (skipped) return resolve()
      /* ── 三档自动播放（设置页「自动播放」）──────────────────────────
         full：任何一步都不等；
         once：只在第一步（授予访问权限）等一次，之后全自动；
         off ：第 1、2 步都等（grant/confirm 两步）。
         第二步的密码校验只在「不自动播放」档启用，所以用 needPwd 兜住，
         保证「仅需点击一次进入」不会漏一道密码闸。 */
      var isWaitStep = step && (step.action === 'grant' || step.action === 'confirm')
      if (C.autoPlay === 'full') return resolve()
      if (C.autoPlay === 'once' && !(step && step.action === 'grant')) return resolve()
      if (C.autoPlay === 'off' && !isWaitStep) return resolve()
      /* 第二步密码校验：设置了 identityPassword 才拦截，输对才推进 */
      var needPwd = step && step.action === 'confirm' && C.identityPassword
      /* 「仅需点击一次进入」要求空密码；万一配置里还留着密码，这里跳过密码闸，
         否则等一次点击就变成「必须先输对密码」，与选项描述不符。 */
      if (C.autoPlay === 'once') needPwd = false
      /* 空档里刚按过 Enter（「不自动播放」连按两下）→ 这一步直接放行。
         有密码时不这么做：密码必须真的输进去。 */
      if (!needPwd && consumeRecentPress()) return resolve()
      if (needPwd && ui.pwdInput) {
        ui.pwdInput.value = ''
        if (ui.pwdErr) ui.pwdErr.textContent = ''
        ui.pwdInput.classList.remove('dsu-pwd-shake')
        try { ui.pwdInput.focus() } catch (e) {}
      }
      var done = false
      function fin() {
        if (done) return
        if (needPwd) {
          var input = ui.pwdInput ? ui.pwdInput.value : ''
          if (input !== C.identityPassword) {
            if (ui.pwdErr) ui.pwdErr.textContent = '密码错误，无法进入'
            if (ui.pwdInput) {
              ui.pwdInput.classList.add('dsu-pwd-shake')
              ui.pwdInput.value = ''
              try { ui.pwdInput.focus() } catch (e) {}
            }
            audio.deny()
            return
          }
        }
        done = true
        cleanup()
        resolve()
      }
      function onKey(e) {
        if (needPwd) {
          /* 密码模式只响应 Enter（空格留给输入框打字） */
          if (e.key === 'Enter') { e.preventDefault(); fin() }
          return
        }
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); fin() }
      }
      function onClick(e) {
        /* 密码模式下点击输入框本身只是聚焦，不触发确认 */
        if (needPwd && ui.pwdInput && e.target === ui.pwdInput) return
        e.preventDefault(); fin()
      }
      function cleanup() {
        ui.btn.removeEventListener('click', onClick)
        ui.action.removeEventListener('click', onClick)
        document.removeEventListener('keydown', onKey)
        var i = waiters.indexOf(fin)
        if (i >= 0) waiters.splice(i, 1)
      }
      ui.btn.addEventListener('click', onClick)
      ui.action.addEventListener('click', onClick)
      document.addEventListener('keydown', onKey)
      waiters.push(fin)
      /* mini_code 补丁:等待也要有尽头,别把人卡在开机动画前 */
      if (!needPwd) setTimeout(function () { fin() }, ms(12000))
    })
  }

  function releaseAll() {
    for (var i = 0; i < timers.length; i++) clearTimeout(timers[i])
    timers.length = 0
    var list = waiters.slice()
    waiters.length = 0
    for (var j = 0; j < list.length; j++) { try { list[j]() } catch (err) { /* noop */ } }
  }

  /* ── 确认连按：前后两次确认之间的空档也能用 Enter 快进 ──────────────────
     「不自动播放」档：第一步按 Enter 确认后，要等语音念完 + 320ms 才切到第二步，
     这一秒多里没有任何「等待确认」的状态，此时按的 Enter 会被直接丢掉 ——
     用户连按两下，第二下就像没反应。
     做法：只记录「没有在等待时」按下的 Enter；下一步开始等待时若在 1.5 秒内就直接放行。
     等待中的 Enter 由各自的监听处理，不会被这里重复计数。 */
  var CONFIRM_GRACE_MS = 1500
  var idlePressAt = 0

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || skipped || finished) return
    if (waiters.length === 0) idlePressAt = Date.now()
  })

  /** 开始等待时调用：刚在空档里按过 Enter 就直接放行（一次只放行一步）。 */
  function consumeRecentPress() {
    var fresh = idlePressAt > 0 && (Date.now() - idlePressAt) < CONFIRM_GRACE_MS
    idlePressAt = 0
    return fresh
  }

  function setProgress(p) {
    var pct = Math.max(0, Math.min(1, p))
    ui.bar.style.width = Math.round(pct * 100) + '%'
  }

  /** 六格阶段柱：走过的压暗、当前的拉满并点亮主题橙 */
  function setSlats(active) {
    var items = ui.slats.children
    for (var i = 0; i < items.length; i++) {
      var idx = i + 1
      items[i].classList.toggle('dsu-on', idx === active)
      items[i].classList.toggle('dsu-past', idx < active)
    }
  }

  /** 扫描线自上而下扫一遍（底板洗白后一次，验准时再一次） */
  function sweep() {
    if (!ui.scanline) return
    ui.scanline.classList.remove('dsu-go')
    void ui.scanline.offsetWidth
    ui.scanline.classList.add('dsu-go')
  }

  function paintClock() {
    var d = new Date()
    var pad = function (n) { return (n < 10 ? '0' : '') + n }
    ui.meta2.textContent = pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
  }

  function setSubtitle(zh, en) {
    ui.subZh.classList.remove('dsu-in')
    ui.subEn2.classList.remove('dsu-in')
    setTimeout(function () {
      ui.subZh.textContent = zh || ''
      ui.subEn2.textContent = en || ''
      ui.subZh.classList.add('dsu-in')
      if (en) ui.subEn2.classList.add('dsu-in')
    }, ms(140))
  }

  function setStepCount(i, code) {
    var totalSteps = STEPS.length + 1
    ui.stepcount.textContent = '[ ' + String(i).padStart(2, '0') + ' / ' +
      String(totalSteps).padStart(2, '0') + ' ] ' + code
  }

  function startHex() {
    var lines = 12
    function line() {
      var s = ''
      for (var i = 0; i < 26; i++) {
        s += '0123456789ABCDEF'.charAt(Math.floor(Math.random() * 16))
        if (i % 2 === 1) s += ' '
      }
      return s
    }
    function paint() {
      var out = []
      for (var i = 0; i < lines; i++) out.push(line())
      ui.hex.innerHTML = out.join('<br>')
    }
    paint()
    ui.hex.classList.add('dsu-in')
    audio.tickRun()
    hexTimer = setInterval(paint, 110)
  }
  function stopHex() {
    if (hexTimer) { clearInterval(hexTimer); hexTimer = null }
    ui.hex.classList.remove('dsu-in')
  }

  /* ── 声音 ──────────────────────────────────────────────────────────────
   *   audio —— 界面音效:真素材(sfx-tick / sfx-ticks-run)优先,合成音兜底
   *   voice —— 女声播报:真声素材(line-* / line-cn-*),素材缺失就安静
   * 浏览器可能拦自动播放:每个 play() 都 catch,没声音也把动画演完。 */
  function clamp01(v, lo, hi) {
    var n = Number(v)
    return isFinite(n) ? Math.min(hi, Math.max(lo, n)) : lo
  }

  var audio = (function () {
    var ctx = null
    function ac(force) {
      /* 语音素材要独立于「界面音效」开关：force=true 时无视 C.sound */
      if (!C.sound && !force) return null
      try {
        var AC = window.AudioContext || window.webkitAudioContext
        if (!AC) return null
        if (!ctx) ctx = new AC()
        if (ctx.state === 'suspended' && typeof ctx.resume === 'function') ctx.resume()
        return ctx
      } catch (e) { return null }
    }
    function vol(gain) { return Math.max(0.0002, (gain == null ? 0.05 : gain) * clamp01(C.soundVolume, 0, 1) * 2) }
    function tone(freq, dur, type, gain, delay, glideTo) {
      var c = ac(); if (!c) return
      try {
        var t0 = c.currentTime + (delay || 0)
        var o = c.createOscillator(), g = c.createGain()
        o.type = type || 'sine'
        o.frequency.setValueAtTime(freq, t0)
        if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur)
        g.gain.setValueAtTime(0.0001, t0)
        g.gain.exponentialRampToValueAtTime(vol(gain), t0 + Math.min(0.02, dur * 0.3))
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
        o.connect(g); g.connect(c.destination)
        o.start(t0); o.stop(t0 + dur + 0.03)
      } catch (e) { /* 静默降级 */ }
    }
    function noise(dur, gain) {
      var c = ac(); if (!c) return
      try {
        var n = Math.floor(c.sampleRate * dur)
        var buf = c.createBuffer(1, n, c.sampleRate)
        var d = buf.getChannelData(0)
        for (var i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n)
        var src = c.createBufferSource(); src.buffer = buf
        var f = c.createBiquadFilter(); f.type = 'bandpass'
        f.frequency.value = 1500; f.Q.value = 0.6
        var g = c.createGain(); g.gain.value = vol(gain)
        src.connect(f); f.connect(g); g.connect(c.destination)
        src.start()
      } catch (e) { /* 静默降级 */ }
    }
    /* mini_code 补丁:素材改用 <audio> 元素播放(宿主 CSP connect-src 'none',
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

    return {
      resume: function () { ac(); loadAsset('sfx-tick'); loadAsset('sfx-ticks-run') },
      preload: function () { loadAsset('sfx-tick'); loadAsset('sfx-ticks-run') },
      ensureAsset: ensureAsset,
      playAssetAndWait: playAssetAndWait,
      /* 文字渐显 / 阶段推进 / 按钮确认 —— 优先用真素材 */
      tick: function () { if (!playAsset('sfx-tick', 0.45)) tone(1760, 0.035, 'square', 0.022) },
      confirm: function () { if (!playAsset('sfx-tick', 0.85)) { tone(660, 0.09, 'triangle', 0.07); tone(990, 0.17, 'triangle', 0.055, 0.085) } },
      tickRun: function () { playAsset('sfx-ticks-run', 0.5) },
      step: function () { if (!playAsset('sfx-tick', 0.6)) { tone(880, 0.05, 'sine', 0.05); tone(1320, 0.07, 'sine', 0.028, 0.045) } },
      hover: function () { tone(2200, 0.02, 'sine', 0.018) },
      /* 密码错误 / 访问拒绝：两声下沉的钝响，和 confirm 的上行音反着来 */
      deny: function () { tone(196, 0.18, 'sawtooth', 0.05); tone(130, 0.24, 'sawtooth', 0.045, 0.09) },
      sweep: function () { noise(0.75, 0.035) },
      /* 念台词之前的两声轻提示：这一笔让 TTS 从"浏览器念字"变成"系统播报" */
      cue: function () { tone(1046.5, 0.05, 'sine', 0.028); tone(1568, 0.06, 'sine', 0.02, 0.075) },
      rise: function () { tone(220, 1.1, 'sine', 0.032, 0, 990) },
      chime: function () {
        tone(659.25, 0.9, 'sine', 0.055)
        tone(830.61, 0.9, 'sine', 0.04, 0.09)
        tone(987.77, 1.3, 'sine', 0.045, 0.18)
      }
    }
  })()

  /* ── mini_code 补丁:女声播报 = 只有真声素材这一条路 ────────────────────
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

  /* 语音/音效接线：声卡要等用户手势才能出声，这里挂一次性解锁 */
  voice.attach(q('.dsu-voice'))
  ;(function preloadVoices() {
    if (C.voiceSource === 'tts') return
    for (var i = 0; i < STEPS.length; i++) if (STEPS[i].audio) audio.ensureAsset(cnAsset(STEPS[i].audio))
  })()
  ;(function wireSound() {
    voice.load()
    var unlocked = false
    function unlock() {
      if (unlocked) return
      unlocked = true
      voice.unlock()
      document.removeEventListener('pointerdown', unlock, true)
      document.removeEventListener('keydown', unlock, true)
      document.removeEventListener('touchstart', unlock, true)
    }
    document.addEventListener('pointerdown', unlock, true)
    document.addEventListener('keydown', unlock, true)
    document.addEventListener('touchstart', unlock, true)
  })()

  /* ── 时间线 ───────────────────────────────────────────────────────────── */
  function run() {
    MC.ready()   /* mini_code 补丁:首帧交给宿主,可以显示跳过按钮了 */
    return Promise.resolve()
      /* 第一幕：黑幕 --> Mini Code 徽标 */
      .then(function () { return wait(820) })
      .then(function () {
        ui.blackInner.classList.add('dsu-in')
        audio.rise()
        return wait(240)
      })
      .then(function () {
        ui.blackEn.classList.add('dsu-tighten')
        return wait(880)
      })
      .then(function () {
        ui.sweep.classList.add('dsu-go')
        return wait(760)
      })
      /* 过场：过曝洗白 */
      .then(function () {
        ui.blackInner.classList.add('dsu-out')
        audio.sweep()
        ui.wash.style.transition = 'opacity ' + ms(220) + 'ms linear'
        ui.wash.style.opacity = '1'
        return wait(260)
      })
      .then(function () {
        ui.plate.style.transition = 'opacity ' + ms(900) + 'ms ease'
        ui.plate.style.opacity = '1'
        ui.watermark.style.transition = 'opacity ' + ms(1100) + 'ms ease'
        ui.watermark.style.opacity = '1'
        ui.wash.style.transition = 'opacity ' + ms(720) + 'ms cubic-bezier(.2,.9,.2,1)'
        ui.wash.style.opacity = '0'
        ui.black.style.transition = 'opacity ' + ms(720) + 'ms ease'
        ui.black.style.opacity = '0'
        return wait(760)
      })
      /* 第二幕：品牌块 / 页脚 / 进度条 */
      .then(function () {
        ui.brand.classList.add('dsu-in')
        ui.foot.classList.add('dsu-in')
        ui.stepcount.classList.add('dsu-in')
        ui.idline.classList.add('dsu-in')
        ui.frame.classList.add('dsu-in')
        ui.slats.classList.add('dsu-in')
        ui.meta.classList.add('dsu-in')
        ui.vignette.classList.add('dsu-in')
        ui.voice.classList.add('dsu-in')
        setProgress(0.12)
        setStepCount(0, 'BOOT')
        setSlats(0)
        setSubtitle('系统自检中…', 'SYSTEM SELF-CHECK')
        if (C.allowSkip) ui.skip.classList.add('dsu-in')
        return wait(700)
      })
      .then(function () { ui.black.style.display = 'none'; sweep() })
      /* 六个阶段 */
      .then(function () { return stepLoop() })
      /* 终幕 */
      .then(function () { return finale() })
      .catch(function (err) {
        try { console.warn('[mc-secret] 动画异常，直接揭幕：', err) } catch (e2) {}
        return finish()
      })
  }

  function stepLoop() {
    var chain = Promise.resolve()
    STEPS.forEach(function (step, i) {
      chain = chain.then(function () {
        if (finished) return
        var n = i + 1
        setStepCount(n, step.badge)
        MC.step(n, STEPS.length + 1, step.zh, step.progress)   /* mini_code 补丁 */
        setSlats(n)
        setProgress(step.progress)
        setSubtitle(step.log, step.logEn)
        audio.step()
        /* 离开「身份资料确认」那一步时把卡片收起来：
           自动播放档下卡片会一直留着，不清掉的话第三步以后还会挂着一块「身份资料」。 */
        if (step.action !== 'confirm' && ui.card) {
          ui.card.hidden = true
          if (C.autoPlay === 'full') {
            /* full 档容器一直保持可见，只需把卡片本身藏掉 */
            ui.card.hidden = true
          } else if (n > 2) {
            hideAction()
          }
        }
        /* 语音在这里起头，但**不阻塞**下面的文字渐显 —— 两者同时发生 */
        var spoke = voice.line(step.say, step.zh, step.audio)

        ui.status.classList.toggle('dsu-zhline', true)
        /* 先摘掉 dsu-in 并强制一次样式计算，新的逐字 span 才会重新走渐显动画 */
        ui.status.classList.remove('dsu-in')
        ui.subEn.classList.remove('dsu-in')
        void ui.status.offsetWidth
        typeIn(ui.statusZh, step.zh, 46)
        typeIn(ui.subEn, step.en, 13)
        ui.caret.classList.toggle('dsu-on', !!step.action && step.action !== 'auto')
        requestAnimationFrame(function () {
          if (finished) return
          ui.status.classList.add('dsu-in')
          ui.subEn.classList.add('dsu-in')
        })
        ui.rule.classList.add('dsu-in')

        if (step.assembleLogo) assembleLogo()
        if (step.reticle) {
          /* 照原片：准星出现时中央只留状态字，徽标和虚线收掉，别挤成一团 */
          ui.logo.classList.remove('dsu-in')
          ui.dots.hidden = true
          ui.reticle.classList.add('dsu-in')
          sweep()
        }
        if (step.hex) startHex()

        /* 这一步停多久 = max(视觉基准, 实际播报时长 + 收尾留白) —— 台词长就多停，
           台词短也不会干等。用户点得快时同样等这一句念完，不掐断。 */
        function holdFor(spoken) {
          var target = Math.max(ms(step.hold), (spoken || 0) + ms(240))
          return wait(Math.max(0, target - (spoken || 0)))
        }

        if (step.action === 'grant' || step.action === 'confirm') {
          /* 这一步要不要摆按钮，由三档自动播放决定：
             full = 不摆；once = 只在第一步摆；off = 第 1、2 步都摆。 */
          var wantsWait = C.autoPlay === 'off' ||
            (C.autoPlay === 'once' && step.action === 'grant')
          if (wantsWait) {
            showAction(step)
            return wait(520)
              .then(function () { return waitAction(step) })
              .then(function () {
                hideAction()
                audio.confirm()
                ui.caret.classList.remove('dsu-on')
                return spoke
              }).then(function () { return wait(ms(320)) })
          }
          /* 自动播放：立绘/身份卡照常出现，但不等任何操作，停顿按视觉基准走。
             注意：这里**不能**紧接着调 hideAction() —— 那会把刚加上的 dsu-in 又摘掉，
             .dsu-action 回到 opacity:0，住在里面的身份资料卡就整块看不见了
             （2026-10-19 用户两次反馈「看不到身份信息」的真正原因）。
             卡片保持可见直到这一步结束，进入下一步时由 showAction 重新决定内容。 */
          showAction(step)
          return spoke.then(holdFor)
        }
        if (step.hex) {
          return spoke.then(holdFor).then(function () { stopHex() })
        }
        return spoke.then(holdFor)
      })
    })
    return chain
  }

  function assembleLogo() {
    ui.logo.classList.add('dsu-in')
    ui.dots.hidden = false
    /* 徽标：柔和放大淡入（保持丝滑） */
    var img = ui.logo.querySelector('svg')
    if (img) {
      try {
        img.animate(
          [
            { opacity: 0, transform: 'scale(0.86)' },
            { opacity: 1, transform: 'scale(1)' }
          ],
          { duration: ms(900), easing: 'cubic-bezier(.2,.9,.3,1)', fill: 'backwards' }
        )
      } catch (err) { /* Web Animations 不可用时直接显示 */ }
    }
    return wait(300)
  }

  function showAction(step) {
    ui.btnZh.textContent = step.btnZh
    ui.btnEn.textContent = step.btnEn
    ui.card.hidden = step.action !== 'confirm'
    /* 第二步是否需要密码：只有设置了 identityPassword 才启用密码校验 */
    var needPwd = step.action === 'confirm' && C.identityPassword
    if (step.action === 'confirm') {
      ui.card.innerHTML = ''
      /* 纯中文标签 + 数字/名称，去掉英文双写与主机行，别堆信息 */
      var rows = [
        ['身份名称', C.identity, true],
        ['身份编号', C.identityId, false],
        ['权限等级', C.accessLevel, false]
      ]
      rows.forEach(function (r) {
        var row = el('div', 'dsu-card-row')
        row.appendChild(el('span', null, r[0]))
        row.appendChild(el('b', r[2] ? 'dsu-zhname' : null, r[1]))
        ui.card.appendChild(row)
      })
      /* 访问密码输入行：设置了 identityPassword 才出现 */
      ui.pwdInput = null
      ui.pwdErr = null
      if (needPwd) {
        var pwdRow = el('div', 'dsu-card-row dsu-pwd-row')
        pwdRow.appendChild(el('span', null, '访问密码'))
        var input = document.createElement('input')
        input.type = 'password'
        input.className = 'dsu-pwd-input'
        input.placeholder = '输入密码以继续'
        input.autocomplete = 'off'
        input.spellcheck = false
        pwdRow.appendChild(input)
        ui.card.appendChild(pwdRow)
        var err = el('div', 'dsu-pwd-error', '')
        ui.card.appendChild(err)
        ui.pwdInput = input
        ui.pwdErr = err
      }
    }
    ui.hint.innerHTML = needPwd
      ? '输入访问密码后按 <kbd>Enter</kbd>，或点击按钮确认'
      : '按 <kbd>Enter</kbd> / <kbd>Space</kbd>，或点击按钮继续'
    /* 完全自动播放：不需要用户点按钮，但**第二步的身份资料卡必须照常显示**。
       以前这里是整块 dsu-action 不加 dsu-in，而 .dsu-action 默认 opacity:0，
       卡片恰好住在它里面，于是「确认身份资料」下面的身份名称/编号/权限等级全看不见了
       （2026-10-19 用户反馈）。现在只隐藏按钮与按键提示，卡片照常淡入。 */
    if (C.autoPlay === 'full') {
      ui.action.classList.add('dsu-in')
      ui.btn.hidden = true
      ui.hint.hidden = true
      ui.btn.classList.remove('dsu-pulse')
    } else {
      ui.action.classList.add('dsu-in')
      ui.btn.hidden = false
      ui.hint.hidden = false
      ui.btn.classList.add('dsu-pulse')
    }
    /* 从第一页（授予访问权限）起：右下角亮出赛博风人物立绘，之后一直保持。
       mascot='none' 时整块保持隐藏。 */
    if (C.showMascot && (step.action === 'grant' || step.action === 'confirm')) {
      ui.mascot.hidden = false
      ui.mascot.classList.add('dsu-on')
    }
  }

  function hideAction() {
    ui.action.classList.remove('dsu-in')
    ui.btn.classList.remove('dsu-pulse')
  }

  function finale() {
    if (finished) return Promise.resolve()
    setStepCount(6, 'WELCOME')
    setSlats(6)
    setProgress(1)
    /* 底部日志和终幕里的「欢迎 xxx 访问」区分开，避免同一句出现两遍 */
    setSubtitle('身份验证完成，会话已建立', 'IDENTITY VERIFIED · SESSION ESTABLISHED')
    audio.chime()
    /* mini_code 补丁:上游终幕那句「欢迎语」语音素材本主题不携带 ——
       终幕只有画面与合成钟,不再等一句不存在的人声。 */
    var welcome = Promise.resolve(0)

    ui.status.classList.remove('dsu-in')
    ui.subEn.classList.remove('dsu-in')
    ui.rule.classList.remove('dsu-in')
    ui.reticle.classList.remove('dsu-in')
    stopHex()
    /* 中央区（状态行/分隔线/徽标/虚线）整体退场：不清掉会和 WELCOME 版式叠字 */
    ui.center.classList.add('dsu-off')
    ui.dots.hidden = true

    return wait(360)
      .then(function () {
        ui.welcome.classList.add('dsu-in')
        ui.idline.classList.remove('dsu-in')
        return wait(420)
      })
      .then(function () {
        /* 结尾色散故障：分片位移 + 0.5px 模糊 + 混合模式，读起来像镜头色散 */
        var targets = [ui.w1, ui.w2, ui.w4]
        targets.forEach(function (t) {
          t.classList.add('dsu-glitch')
          t.setAttribute('data-text', t.textContent)
        })
        ui.w2.classList.add('dsu-glitch-box')   /* 黑底白字那块换加色混合 */
        void ui.welcome.offsetWidth
        targets.forEach(function (t) { t.classList.add('dsu-on') })
        return wait(640)
      })
      /* 光晕从中心炸开 + 变形光条横扫 + 文字青色 halation */
      .then(function () {
        root.classList.add('dsu-peak')
        ui.bloom.classList.add('dsu-go')
        ui.streak.classList.add('dsu-go')
        return wait(430)
      })
      /* 光晕最亮那一下补一记极短高光（是"眨一下"，不是长时间糊白） */
      .then(function () {
        ui.flash.style.transition = 'opacity ' + ms(70) + 'ms linear'
        ui.flash.style.opacity = '0.72'
        return wait(90)
      })
      .then(function () {
        ui.flash.style.transition = 'opacity ' + ms(340) + 'ms cubic-bezier(0.4, 0, 0.2, 1)'
        ui.flash.style.opacity = '0'
        return wait(320)
      })
      /* 欢迎语没播完就不揭幕（素材缺失时这个 Promise 立刻 resolve，不影响节奏） */
      .then(function () { return welcome })
      /* 揭幕：整个机位后撤 + 轻微失焦，比单纯淡出更有镜头感 */
      .then(function () {
        root.classList.add('dsu-handoff')
        MC.handoff()   /* mini_code 补丁:淡出第一帧就交还界面 */
        return wait(780)
      })
      .then(function () { return finish() })
  }

  function finish() {
    if (finished) return
    finished = true
    MC.done()   /* mini_code 补丁:跳过 / 出错 / 播完都从这里交还 */
    releaseAll()
    stopHex()
    voice.stop()
    if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
    /* mini_code 补丁:「本次是否已播」由宿主记录,主题不读写任何浏览器存储 */
    /* 解锁：Host 注入的关键样式用 html.dsu-lock 锁滚动，这里必须一并摘掉，
       否则揭幕后主界面会永远滚不动。 */
    document.documentElement.classList.remove('dsu-lock')
    document.documentElement.style.overflow = ''
    if (document.body) document.body.style.overflow = ''
    root.classList.remove('dsu-boot')
    /* 退场：直接摘掉，不做长淡出。
       以前是「620ms 淡出 + 再等 900ms 才移除」，中间那段时间 root 仍是一块
       z-index 2147483000 的全屏层（只是越来越透明），视觉上就是
       「动画结束/按 Enter 之后还要黑一会儿」（2026-10-19 用户反馈）。
       揭幕那一帧 root 已经整体淡到接近全透明（dsu-handoff 的 780ms 过渡跑完才会走到这里），
       所以这里直接移除不会有突兀的跳变。 */
    root.classList.add('dsu-gone')
    if (root.parentNode) root.parentNode.removeChild(root)
  }

  function requestSkip() {
    if (skipped || finished) return
    skipped = true
    releaseAll()
    finish()
  }

  if (C.allowSkip && ui.skip) {
    ui.skip.hidden = false
    ui.skip.addEventListener('click', function (e) { e.stopPropagation(); requestSkip() })
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') requestSkip()
    })
  } else if (ui.skip) {
    ui.skip.hidden = true
  }


  /* 锁滚动，动画期间不露出下面的应用 */
  document.documentElement.classList.add('dsu-lock')
  document.documentElement.style.overflow = 'hidden'
  if (document.body) document.body.style.overflow = 'hidden'
  setProgress(0.05)
  root.classList.remove('dsu-boot')

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { run() })
  } else {
    run()
  }
})()
