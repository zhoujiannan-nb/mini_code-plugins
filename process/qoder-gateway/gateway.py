#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qoder 网关启动器（mini_code process 插件）.

拉下来就能用：二进制就在插件目录里（`qoder-gw.bin.json`，zlib+base64 的
stripped exe，约 3.8MB —— 宿主安装器不收 .exe，且单文件上限 8MB），首次运行时
解到 `%LOCALAPPDATA%\\Programs\\QoderAPI\\QoderAPI.exe` 并按清单里的 sha256 校验，
校验不过就拒绝执行。

刻意不做的事：
  * 不携带任何凭据。PAT 与客户端 key 由网关自己从 ~/.qoder-api/ 读，
    绝不写进 plugin.json、命令行或本仓库。
  * 不静默替换正在跑的实例：目标文件被占用且它就是健康的网关时，先用它跑起来，
    把更新留到下次重启，而不是让服务当场消失。

二进制选择顺序：
  1. qoder-gw.json 的 "bin" 或环境变量 QODER_GW_BIN（用户显式指定，原样使用）
  2. 本机已有副本（%LOCALAPPDATA%\\Programs\\QoderAPI\\、桌面、PATH）里 sha256
     与插件清单一致的那个
  3. 从插件目录的 payload 解出来（新装 / 版本不一致）
  4. 实在没有清单一致的副本，就用本机最新副本并告警（离线或手工换过二进制的场景）
"""
import base64
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "qoder-gw.json")
PAYLOAD = os.path.join(HERE, "qoder-gw.bin.json")
DEFAULT_ADDR = "127.0.0.1:32999"
EXE_NAME = "QoderAPI.exe"


def log(msg):
    print("[qoder-gateway] " + msg, flush=True)


def read_conf():
    if not os.path.exists(CONF):
        return {}
    try:
        with open(CONF, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # a broken local config must not be fatal
        log("qoder-gw.json 读不了（忽略，用默认值）：%s" % exc)
        return {}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_payload():
    """Return the manifest dict, or None when the plugin ships no payload."""
    if not os.path.isfile(PAYLOAD):
        return None
    try:
        with open(PAYLOAD, encoding="utf-8") as f:
            p = json.load(f)
    except Exception as exc:
        log("[payload] 清单读不了：%s" % exc)
        return None
    if p.get("algo") != "zlib+base64" or not p.get("data") or not p.get("sha256"):
        log("[payload] 清单字段不完整（algo/data/sha256）")
        return None
    return p


def install_target():
    """Where an extracted binary lives: outside the plugin dir, so a plugin
    reinstall does not delete a running program's image, and stable across
    catalogue updates."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return os.path.join(local, "Programs", "QoderAPI", EXE_NAME)
    return os.path.join(HERE, EXE_NAME)


def local_candidates():
    out = [install_target()]
    home = os.path.expanduser("~")
    out.append(os.path.join(home, "Desktop", EXE_NAME))
    which = shutil.which("QoderAPI") or shutil.which(EXE_NAME)
    if which:
        out.append(which)
    return out


def extract(payload, dst):
    """Decode, decompress, verify, and write atomically. Returns the path."""
    blob = zlib.decompress(base64.b64decode(payload["data"]))
    digest = hashlib.sha256(blob).hexdigest()
    if digest != payload["sha256"]:
        raise ValueError("sha256 不匹配：算出 %s，清单要 %s" % (digest, payload["sha256"]))
    want = int(payload.get("raw_size") or 0)
    if want and len(blob) != want:
        raise ValueError("长度不对：%d，清单要 %d" % (len(blob), want))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".new"
    with open(tmp, "wb") as f:
        f.write(blob)
    try:
        os.replace(tmp, dst)
    except OSError as exc:
        # A running instance locks the image on Windows.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("无法写入 %s（进程可能正在使用它）：%s" % (dst, exc))
    log("[payload] 已解出 %s（%.2f MB, sha256=%s…）"
        % (dst, len(blob) / 1048576.0, digest[:16]))
    return dst


def ensure_binary(conf, payload):
    """Resolve which QoderAPI.exe to run, extracting the shipped one if needed."""
    explicit = conf.get("bin") or os.environ.get("QODER_GW_BIN")
    if explicit:
        path = os.path.expandvars(os.path.expanduser(explicit))
        if os.path.isfile(path):
            return path, "用户指定"
        log("指定的 bin 不存在：%s（改在本机查找）" % path)

    for path in local_candidates():
        if not os.path.isfile(path):
            continue
        if payload is None:
            return path, "本机副本（插件未带清单）"
        try:
            if sha256_file(path) == payload["sha256"]:
                return path, "本机副本与插件版本一致"
        except OSError:
            continue

    if payload is not None:
        target = install_target()
        try:
            return extract(payload, target), "从插件解出"
        except Exception as exc:
            log("[payload] 解出失败：%s" % exc)
            if os.path.isfile(target) and health_of(target):
                return target, "解出失败，沿用正在运行的旧版"

    for path in local_candidates():
        if os.path.isfile(path):
            log("本机副本与插件清单版本不一致，仍使用 %s（想强制更新就删掉它）" % path)
            return path, "本机旧副本"
    return None, "找不到也解不出 QoderAPI.exe"


def health_of(_path):
    return health() is not None


def health(addr=None, timeout=2.0):
    addr = addr or current_addr
    try:
        with urllib.request.urlopen("http://%s/health" % addr, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "ok":
            return data
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return None


def port_open(addr):
    host, _, port = addr.partition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=1.0):
            return True
    except OSError:
        return False


current_addr = DEFAULT_ADDR


def supervise(proc):
    """Wait for the child, forwarding a stop request; return its exit code."""
    stopping = {"v": False}

    def stop(_signum, _frame):
        if stopping["v"]:
            return
        stopping["v"] = True
        log("收到停止请求，正在结束网关…")
        try:
            proc.send_signal(signal.SIGTERM)
        except Exception:
            proc.terminate()

    for sig in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGBREAK", signal.SIGTERM)):
        try:
            signal.signal(sig, stop)
        except (ValueError, OSError):
            pass

    while True:
        code = proc.poll()
        if code is not None:
            return code
        if stopping["v"]:
            try:
                return proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                return proc.wait()
        time.sleep(0.5)


def watch_existing(addr):
    """Another gateway already owns the port: stay alive while it does.

    Returns False when that gateway dies, meaning "take over right now" —
    waiting for the host's restart backoff would leave the service down for no
    reason.
    """
    h = health(addr) or {}
    log("[watch] port %s already served by a healthy gateway "
        "(provider=%s models=%s); supervising instead of double-binding"
        % (addr, h.get("provider"), h.get("models")))
    while health(addr) is not None:
        time.sleep(3)
    log("[watch] the supervised gateway stopped")
    return False


def wait_port_free(addr, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_open(addr):
            return True
        time.sleep(1)
    return not port_open(addr)


def main():
    global current_addr
    conf = read_conf()
    addr = os.environ.get("QODER_GW_ADDR") or conf.get("addr") or DEFAULT_ADDR
    current_addr = addr
    region = os.environ.get("QODER_GW_REGION") or conf.get("region") or "global"
    extra = list(conf.get("args") or [])

    payload = load_payload()
    if payload:
        log("[payload] 插件自带二进制：sha256=%s… %.2fMB 压缩载荷"
            % (payload["sha256"][:16], os.path.getsize(PAYLOAD) / 1048576.0))

    if health(addr) is not None:
        if not watch_existing(addr):
            log("[takeover] 被看守的网关已退出，立即由本插件拉起新实例")

    binary, why = ensure_binary(conf, payload)
    if not binary:
        log("找不到 QoderAPI.exe（%s）。可以：" % why)
        log("  1) 保持插件自带的 qoder-gw.bin.json（默认就能用）")
        log("  2) 在 qoder-gw.json 里写 {\"bin\": \"C:\\\\path\\\\QoderAPI.exe\"}")
        log("  3) 或设环境变量 QODER_GW_BIN=C:\\path\\QoderAPI.exe")
        log("  找过的位置：%s" % ", ".join(local_candidates()))
        return 2

    log("[binary] %s（%s）" % (binary, why))

    if port_open(addr) and not wait_port_free(addr, 15):
        log("%s 被别的进程占着，而且它不是 Qoder 网关（/health 没应答）。" % addr)
        log("换个端口：qoder-gw.json 里写 {\"addr\": \"127.0.0.1:33001\"}，或设 QODER_GW_ADDR。")
        return 3

    args = [binary, "-addr", addr, "-region", region, "-parent-pid", str(os.getpid())] + extra
    log("[start] %s" % " ".join(args))
    proc = subprocess.Popen(args, cwd=os.path.dirname(binary))
    code = supervise(proc)
    log("网关退出，code=%s" % code)
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
