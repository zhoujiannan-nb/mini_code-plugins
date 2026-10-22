# -*- coding: utf-8 -*-
"""重新生成技术档案主题的语音/音效素材(全部离线,不联网)。

  python tools/gen_audio.py            # 生成到 boot-anim/mc-tech-archive/
  python tools/gen_audio.py --voice Huihui

语音用 Windows 自带 TTS(System.Speech,zh-CN 的 Microsoft Huihui),音效是纯
python 合成的正弦 + 噪声包络。素材是随仓库分发的,正常情况不用重跑;想换台词
改 LINES 再跑一次即可(主题按文件名读取)。
"""
import argparse
import math
import os
import random
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEME = os.path.join(ROOT, "boot-anim", "mc-tech-archive")
PS1 = r"""
param([string]$Text, [string]$Out, [int]$Rate, [string]$Voice)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) { $s.SelectVoice($Voice) }
$s.Rate = $Rate
$s.Volume = 100
$s.SetOutputToWaveFile($Out)
$s.Speak($Text) | Out-Null
$s.Dispose()
"""

# (文件名, 台词, 语速)。想换声音/台词改这里,然后重跑本脚本。
# 台词点:hello 盖住"睁眼 + 字标展开",welcome 跟小标题「欢迎来到人类联盟」同步。
# Huihui 会把 "Mini Code" 当英文词读(不是拼字母),所以品牌名直接写英文。
LINES = [
    ("voice-hello.wav", "你好,我是 Mini Code。", 2),
    ("voice-welcome.wav", "欢迎来到人类联盟。", 2),
]


def tts(text, out, rate, voice):
    tmp_ps = os.path.join(tempfile.gettempdir(), "mc_gen_tts.ps1")
    with open(tmp_ps, "w", encoding="utf-8-sig") as f:   # BOM:PS 5.1 才认中文
        f.write(PS1)
    tmp_wav = os.path.join(tempfile.gettempdir(), "mc_gen_tts.wav")
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp_ps,
           "-Text", text, "-Out", tmp_wav, "-Rate", str(rate), "-Voice", voice]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.isfile(tmp_wav):
        raise SystemExit("[FAIL] TTS 没产出文件: %s" % (r.stderr or r.stdout).strip()[:400])
    return tmp_wav


def read_wav(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, "期望 16bit 单声道"
        return w.getframerate(), w.readframes(w.getnframes())


def write_wav(path, rate, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def trim(pcm, thresh=180, head=0.09, tail=0.28):
    """掐掉首尾静音,再留一点呼吸(单位:秒)。"""
    n = len(pcm) // 2
    if n == 0:
        return pcm
    frames = struct.unpack("<%dh" % n, pcm)
    lo, hi = 0, n - 1
    while lo < n and abs(frames[lo]) < thresh:
        lo += 1
    while hi > lo and abs(frames[hi]) < thresh:
        hi -= 1
    if lo >= hi:
        return pcm
    rate_guess = 22050
    a = max(0, lo - int(head * rate_guess))
    b = min(n, hi + int(tail * rate_guess))
    return pcm[2 * a:2 * b]


def gen_sfx(path, secs=0.85, rate=22050):
    """开机那一下:低频下潜 + 一层噪声擦过 + 收尾一个高音 ping。"""
    random.seed(7)
    n = int(secs * rate)
    out = bytearray()
    f_ping = 2076.0                                   # 大约 C#7,冷冽一点
    for i in range(n):
        t = i / rate
        p = t / secs
        sweep = math.sin(2 * math.pi * (240.0 * math.exp(-4.2 * t) + 48.0) * t) * math.exp(-3.0 * t)
        hiss = (random.random() * 2 - 1) * math.exp(-9.0 * t) * 0.55
        ping = math.sin(2 * math.pi * f_ping * t) * math.exp(-5.5 * max(0.0, t - 0.10)) * (0.0 if t < 0.10 else 1.0)
        v = sweep * 0.55 + hiss * 0.35 + ping * 0.42
        v = max(-1.0, min(1.0, v)) * 0.62
        out += struct.pack("<h", int(v * 32767))
    write_wav(path, rate, bytes(out))
    return n / rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="Microsoft Huihui Desktop", help="TTS 音色,空串=系统默认")
    args = ap.parse_args()
    if not os.path.isdir(THEME):
        raise SystemExit("[FAIL] 找不到主题目录 " + THEME)
    print("生成语音(TTS = %s):" % (args.voice or "默认"))
    for name, text, rate in LINES:
        src = tts(text, None, rate, args.voice)
        rate_, pcm = read_wav(src)
        pcm = trim(pcm, head=0.12, tail=0.20)
        dst = os.path.join(THEME, name)
        write_wav(dst, rate_, pcm)
        print("  %-18s %5.2fs  %6d B  %s" % (name, len(pcm) / 2.0 / rate_, os.path.getsize(dst), text))
    d = gen_sfx(os.path.join(THEME, "sfx-flash.wav"))
    print("  %-18s %5.2fs  %6d B  (合成音效)" % ("sfx-flash.wav", d, os.path.getsize(os.path.join(THEME, "sfx-flash.wav"))))
    print("\n完成。记得跑 python tools/make_index.py 更新索引 + --check。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
