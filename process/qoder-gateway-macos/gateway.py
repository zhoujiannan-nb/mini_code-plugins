#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qoder 网关启动器（macOS 版，mini_code process 插件）.

拉下来就能用：二进制就在插件目录里（`qoder-gw-macos-<arch>.bin.json`，
zlib+base64 的 stripped Mach-O，单文件约 3.5~3.8MB —— 宿主安装器不收可执行
文件、单文件上限 8MB）。首次运行时按本机 CPU 选对架构，解到
`~/Library/Application Support/QoderAPI/QoderAPI`，按清单里的 sha256 校验，
chmod 755，再核一遍 Mach-O 头，然后带起来。

Apple Silicon 上额外小心一件事：arm64 的 Mach-O 必须带代码签名（Go 交叉编译
默认会打 ad-hoc 签名）。万一某个中间环节把签名搞掉了，进程会被内核直接杀
（`killed: 9`，连输出都没有），所以这里除了开机前检查，还在子进程异常死亡时
尝试 `codesign --force -s -` 补一个 ad-hoc 签名再重试一次。

刻意不做的事：
  * 不携带任何凭据。PAT 与客户端 key 由网关自己从 ~/.qoder-api/ 读，
    绝不写进 plugin.json、命令行或本仓库。
  * 不静默替换正在跑的实例：目标文件被占用且它就是健康的网关时，先用它跑起来，
    把更新留到下次重启，而不是让服务当场消失。
   * 不在非 macOS 上硬跑：这本就是苹果版插件，认不出平台就直接说清楚该装哪个。

用量显示：启动器每 60 秒问一次本机网关的 /qoder/usage，把一行摘要写进**已安装**
那份 `plugin.json` 的 description 首行 —— 插件中心里这个插件的卡片就直接显示
"额度 1,907 / 2,610 credits（已用 703，27%）· 正常 · 附加包 100/100 · Teams"。
明细另外渲染成 `quota.html`（浏览器里直接打开）。
终端里想直接看：`sh run.sh --quota`。


二进制选择顺序：
  1. qoder-gw.json 的 "bin" 或环境变量 QODER_GW_BIN（用户显式指定，原样使用）
  2. 本机已有副本（~/Library/Application Support/QoderAPI/、~/Applications、
     /usr/local/bin、/opt/homebrew/bin、PATH）里 sha256 与插件清单一致的
  3. 从插件目录的载荷解出来（新装 / 版本不一致）
  4. 实在没有清单一致的副本，就用本机最新副本并告警（离线或手工换过二进制的场景）
"""
import base64
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "qoder-gw.json")
DEFAULT_ADDR = "127.0.0.1:32999"
BIN_NAME = "QoderAPI"
ROSETTA_HINT = "arch -arm64 /usr/bin/python3"

# 别在插件目录里留 __pycache__：宿主的插件安装器要求目录扁平（见到子目录直接报错），
# 而 `import quota_render` 默认会在 HERE 下建 __pycache__ —— 那会挡住今后从插件中心
# 升级。这里只关掉字节码落盘（import 照常工作）。
sys.dont_write_bytecode = True

# ---- 用量显示 ----
# 插件卡片上唯一能动态变的字段就是 manifest 的 description（宿主会实时重读，
# 与 Windows 版同一份结论）。所以启动器定时问一次本机网关的 /qoder/usage，把一行
# 摘要写进**已安装那份** plugin.json 的 description 首行 —— 用户就在插件自己那张
# 卡上看到用量，不占界面、不挡内容。
# 全局 overlay（ui.slots）那套已废弃：宿主给的是无脚本、跨源隔离的 sandbox iframe，
# <meta refresh> 不触发、同源资源拉不到，只能显示静态内容，还浮在界面右上角挡东西。
PAGE_FILE = "quota.html"          # 完整明细页（浏览器里直接打开）
QUOTA_INTERVAL = 60               # 秒；启动器多久重算一次

LC_CODE_SIGNATURE = 0x1D
CPU_ARM64 = 0x0100000C
CPU_X86_64 = 0x01000007
ARCH_PAYLOAD = {
    "arm64": "qoder-gw-macos-arm64.bin.json",
    "amd64": "qoder-gw-macos-amd64.bin.json",
}


def log(msg):
    print("[qoder-gateway-macos] " + msg, flush=True)


def die(code, *lines):
    for line in lines:
        log(line)
    return code


# --------------------------------------------------------------------------
# 平台与架构
# --------------------------------------------------------------------------

def this_arch():
    """本机原生架构：arm64 / amd64。认不出返回 None。"""
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64", "i386", "i686"):
        return "amd64"
    return None


def running_under_rosetta():
    """x86_64 的 python 跑在 Apple Silicon 上（Rosetta）时为 True。

    这种情况该给 arm64 载荷还是 amd64 载荷？给 amd64：那是当前 python 能直接
    拉起、也不用关心签名的那个（x86_64 在 Intel 与本机 Rosetta 下都能跑）。
    """
    if sys.platform != "darwin" or this_arch() != "amd64":
        return False
    try:
        out = subprocess.run(["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


def macho_arch(path):
    """读 Mach-O 头，返回 (架构名, 有没有 LC_CODE_SIGNATURE)。不是 Mach-O 返回 (None, False)。"""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
            if head == b"\xcf\xfa\xed\xfe":
                endian = "<"
            elif head == b"\xfe\xed\xfa\xcf":
                endian = ">"
            else:
                return None, False
            rest = f.read(28)
            # cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved
            cputype, _sub, _ft, ncmds, _sz, _flags, _rsv = struct.unpack(endian + "iiIIIII", rest)
            signed = False
            for _ in range(ncmds):
                raw = f.read(8)
                if len(raw) < 8:
                    break
                cmd, cmdsize = struct.unpack(endian + "II", raw)
                if cmd == LC_CODE_SIGNATURE:
                    signed = True
                if cmdsize < 8:
                    break
                f.seek(cmdsize - 8, os.SEEK_CUR)
    except OSError:
        return None, False
    cpu = cputype & 0xFFFFFFFF
    name = "arm64" if cpu == CPU_ARM64 else "amd64" if cpu == CPU_X86_64 else hex(cpu)
    return name, signed


# --------------------------------------------------------------------------
# 配置、载荷、安装位置
# --------------------------------------------------------------------------

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


def payload_path(arch):
    return os.path.join(HERE, ARCH_PAYLOAD.get(arch, ARCH_PAYLOAD["arm64"]))


def load_payload(arch):
    """返回 (清单 dict, 实际用的文件名)。没有可用载荷时 (None, None)。"""
    order = [arch] + [a for a in ("arm64", "amd64") if a != arch]
    seen = []
    for a in order:
        p = payload_path(a)
        if not os.path.isfile(p):
            seen.append(os.path.basename(p))
            continue
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
        except Exception as exc:
            log("[payload] %s 读不了：%s" % (os.path.basename(p), exc))
            continue
        if m.get("algo") != "zlib+base64" or not m.get("data") or not m.get("sha256"):
            log("[payload] %s 字段不完整（algo/data/sha256）" % os.path.basename(p))
            continue
        if a != arch:
            log("[payload] 本机是 %s，但只找到 %s 的载荷（%s）—— 会用这个，可能跑不起来；"
                "两个都装上，或者用 qoder-gw.json 指定 bin" % (arch, a, os.path.basename(p)))
        return m, os.path.basename(p)
    log("[payload] 没找到可用载荷（找过 %s）" % ", ".join(seen))
    return None, None


def install_dir():
    """解出来的二进制放这儿。

    放在插件目录之外有两个原因：插件重装会整目录替换（会把正在跑的映像删掉），
    而且这个位置跨市场更新是稳定的。
    """
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "QoderAPI")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "QoderAPI")


def install_target():
    return os.path.join(install_dir(), BIN_NAME)


def local_candidates():
    home = os.path.expanduser("~")
    out = [install_target(),
           os.path.join(home, "Applications", BIN_NAME),
           os.path.join(home, "Applications", "QoderAPI.app", "Contents", "MacOS", "QoderAPI"),
           "/usr/local/bin/" + BIN_NAME,
           "/opt/homebrew/bin/" + BIN_NAME,
           os.path.join(HERE, BIN_NAME)]
    for name in ("QoderAPI", BIN_NAME):
        which = shutil.which(name)
        if which:
            out.append(which)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def strip_quarantine(path):
    """从浏览器/下载器过来的文件可能带 com.apple.quarantine，会被 Gatekeeper 拦。

    我们自己写出来的字节一般没有这个属性，但清一下几乎不花钱（失败就算了）。
    """
    try:
        subprocess.run(["/usr/bin/xattr", "-c", path],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def extract(payload, payload_name, dst):
    """解码 → 解压 → 校验 sha256/长度/Mach-O 架构 → 原子落盘 + chmod。返回路径。"""
    blob = zlib.decompress(base64.b64decode(payload["data"]))
    digest = hashlib.sha256(blob).hexdigest()
    if digest != payload["sha256"]:
        raise ValueError("sha256 不匹配：算出 %s，清单要 %s" % (digest, payload["sha256"]))
    want = int(payload.get("raw_size") or 0)
    if want and len(blob) != want:
        raise ValueError("长度不对：%d，清单要 %d" % (len(blob), want))

    os.makedirs(os.path.dirname(dst), mode=0o755, exist_ok=True)
    tmp = dst + ".new"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.chmod(tmp, 0o755)
    arch_in_payload = (payload.get("arch") or "").strip()
    got_arch, signed = macho_arch(tmp)
    if arch_in_payload and got_arch and got_arch != arch_in_payload:
        os.remove(tmp)
        raise ValueError("载荷里 %s 的架构是 %s，清单写的是 %s"
                         % (payload_name, got_arch, arch_in_payload))
    try:
        os.replace(tmp, dst)
    except OSError as exc:
        # 正在运行的映像可以被替换（Unix 是按 inode 的），但只读目录不行。
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("无法写入 %s：%s" % (dst, exc))
    os.chmod(dst, 0o755)
    strip_quarantine(dst)
    log("[payload] 已解出 %s（%.2f MB, %s, sha256=%s…%s）"
        % (dst, len(blob) / 1048576.0, got_arch or arch_in_payload or "?",
           digest[:16], "，带代码签名" if signed else "，无代码签名"))
    if not signed and (got_arch or arch_in_payload) == "arm64":
        log("[payload] 警告：arm64 产物没有 LC_CODE_SIGNATURE，运行前会用 codesign 补一个 ad-hoc 签名")
    return dst


def adhoc_sign(path):
    """给 arm64 Mach-O 补一个 ad-hoc 签名（Apple Silicon 上被内核杀掉时的唯一解）。"""
    codesign = shutil.which("codesign") or "/usr/bin/codesign"
    log("[sign] %s --force -s - %s" % (codesign, path))
    try:
        r = subprocess.run([codesign, "--force", "--sign", "-", path],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        log("[sign] 调不起 codesign：%s" % exc)
        return False
    if r.returncode != 0:
        log("[sign] 失败：%s" % (r.stderr.strip() or r.stdout.strip()))
        return False
    log("[sign] 已打 ad-hoc 签名")
    return True


def ensure_binary(conf, payload, payload_name):
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
            return path, "本机副本（插件未带载荷）"
        try:
            if sha256_file(path) == payload["sha256"]:
                return path, "本机副本与插件版本一致"
        except OSError:
            continue

    if payload is not None:
        target = install_target()
        try:
            return extract(payload, payload_name, target), "从插件解出（%s）" % payload_name
        except Exception as exc:
            log("[payload] 解出失败：%s" % exc)
            if os.path.isfile(target):
                return target, "解出失败，沿用本机已有副本"

    for path in local_candidates():
        if os.path.isfile(path):
            log("本机副本与插件清单版本不一致，仍使用 %s（想强制更新就删掉它）" % path)
            return path, "本机旧副本"
    return None, "找不到也解不出 QoderAPI"


# --------------------------------------------------------------------------
# 健康检查与进程托管
# --------------------------------------------------------------------------

current_addr = DEFAULT_ADDR


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


def supervise(proc):
    """等子进程退出，顺便把宿主的停止信号转给它；返回它的退出码。"""
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

    for sig in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGHUP", signal.SIGTERM)):
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
    """端口上已经有一个健康的网关：不重复绑定，转为看守。

    被看守的实例死了就返回 False，意思是"立刻接管"——等宿主的重启退避会把服务
    白停几十秒。
    """
    h = health(addr) or {}
    log("[watch] 端口 %s 上已有一个健康的网关（provider=%s models=%s），转为看守而不是重复绑定"
        % (addr, h.get("provider"), h.get("models")))
    while health(addr) is not None:
        time.sleep(3)
    log("[watch] 被看守的网关停了")
    return False


def wait_port_free(addr, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_open(addr):
            return True
        time.sleep(1)
    return not port_open(addr)


def start_gateway(binary, addr, region, extra):
    args = [binary, "-addr", addr, "-region", region, "-parent-pid", str(os.getpid())] + extra
    log("[start] %s" % " ".join(args))
    return subprocess.Popen(args, cwd=os.path.dirname(binary))


# --------------------------------------------------------------------------
# 用量显示：写卡片摘要（主）+ 渲染明细页（辅）
# --------------------------------------------------------------------------

def fetch_usage(addr=None, timeout=8.0):
    """拿一次额度数据；拿不到返回 None（面板会显示"网关没运行/暂无数据"）。"""
    addr = addr or current_addr
    try:
        with urllib.request.urlopen("http://%s/qoder/usage" % addr, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def write_if_changed(path, text):
    """内容没变就不碰文件（少一次磁盘写，也避免无意义地改 mtime）。"""
    data = text.encode("utf-8")
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return True


def refresh_quota(addr=None, log_change=True, write_page=True):
    """重算用量并落到该落的地方；返回 (是否有更新, 状态文字)。

    主输出是**已装 plugin.json 的卡片摘要**（用户就在插件自己那张卡上看到用量）。
    write_page=True 时另外渲染一份 quota.html 给人用浏览器看明细
    （写不出来也不影响摘要，摘要才是主路径）。
    """
    try:
        import quota_render
    except ImportError:
        return False, "缺少 quota_render.py"
    addr = addr or current_addr
    usage = fetch_usage(addr)
    ok = usage is not None
    changed = update_manifest_summary(usage, ok)
    if write_page:
        page = quota_render.render_page(usage, gateway_ok=ok)
        changed = write_if_changed(os.path.join(HERE, PAGE_FILE), page) or changed
    state = quota_render.state_of(usage, ok)[0]
    if changed and log_change:
        acct = (usage or {}).get("account") or {}
        uq = acct.get("user_quota") or {}
        log("[quota] 已更新用量摘要：%s（剩余 %s/%s）"
            % (state, quota_render._num(uq.get("remaining")), quota_render._num(uq.get("total"))))
    return changed, state



def quota_loop(stop_event, addr=None):
    """后台线程：刚起来先算一次（此时网关可能还没就绪，会退避重试），之后每 60 秒一次。"""
    for delay in (1, 2, 3, 5, 8):
        if stop_event.wait(delay):
            return
        if refresh_quota(addr):
            break
    while not stop_event.wait(QUOTA_INTERVAL):
        try:
            refresh_quota(addr)
        except Exception as exc:  # noqa: BLE001 - 用量显示绝不能把网关带崩
            log("[quota] 更新失败（忽略）：%r" % exc)


def update_manifest_summary(usage, gateway_ok=True):
    """把用量摘要写进**已安装**那份 plugin.json 的 description 首行。

    为什么这么做：插件中心那张卡只显示 manifest 的 description（宿主会实时重读），
    没有别的动态字段；而全局 overlay 浮在界面右上角会挡内容、也丑。
    仓库里那份 plugin.json 是模板，**不含**用量；只有本机安装副本会被写。
    摘要行以固定前缀开头，重写时先把旧的第一行摘掉，避免越堆越长。

    拿不到数据时**不覆盖**已有摘要：网关刚启动那几秒必然拿不到，覆盖了就只剩
    "网关未运行"，反而把上一次的好数字冲掉了。
    """
    try:
        import quota_render
    except ImportError:
        return False
    if usage is None:
        return False          # 没数据就不动，保留上一次的摘要
    path = os.path.join(HERE, "plugin.json")
    try:
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        return False
    line = quota_render.summary_line(usage, gateway_ok)
    desc = (man.get("description") or "").strip()
    # 去掉旧的摘要行（可能有多行残留）
    body = "\n".join(
        l for l in desc.splitlines()
        if not l.strip().startswith(("额度 ", "额度：", "额度:", "摘要 "))
    ).strip()
    new_desc = line if not body else line + "\n" + body
    if man.get("description") == new_desc:
        return False
    man["description"] = new_desc
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(man, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError as exc:
        log("[quota] 写 plugin.json 失败（忽略）：%r" % exc)
        return False
    return True


def print_quota(addr=None):
    """--quota：在终端里直接看一眼当前额度（不写文件）。"""
    try:
        import quota_render
    except ImportError:
        print("缺少 quota_render.py（它必须和 gateway.py 在同一个目录里）")
        return 2
    usage = fetch_usage(addr)
    if usage is None:
        print("拿不到额度：网关没在 %s 上跑，或者 PAT 失效。" % (addr or current_addr))
        return 1
    acct = usage.get("account") or {}
    uq = acct.get("user_quota") or {}
    proc = usage.get("process") or {}
    state, _ = quota_render.state_of(usage)
    print("状态      %s" % state)
    print("剩余      %s / %s %s" % (quota_render._num(uq.get("remaining")),
                                  quota_render._num(uq.get("total")),
                                  uq.get("unit") or "credits"))
    print("已用      %s（%.1f%%）" % (quota_render._num(uq.get("used")),
                                    quota_render._pct(uq.get("used"), uq.get("total"))))
    addon = acct.get("addon_quota") or {}
    try:
        if float(addon.get("total") or 0) > 0:
            print("附加包    %s / %s" % (quota_render._num(addon.get("remaining")),
                                        quota_render._num(addon.get("total"))))
    except (TypeError, ValueError):
        pass
    if acct.get("plan") or acct.get("tag"):
        print("套餐      %s" % (acct.get("tag") or acct.get("plan")))
    if acct.get("next_reset_at_ms"):
        try:
            print("重置      %s" % time.strftime("%Y-%m-%d %H:%M",
                                                time.localtime(float(acct["next_reset_at_ms"]) / 1000.0)))
        except (TypeError, ValueError):
            pass
    ptok = proc.get("prompt_tokens") or 0
    cached = proc.get("cached_tokens") or 0
    print("本机      %s 次请求 · prompt %s · cached %s（%.1f%% 命中）"
          % (quota_render._num(proc.get("requests")), quota_render._num(ptok),
             quota_render._num(cached), (cached / ptok * 100.0) if ptok else 0.0))
    return 0


def selftest():
    """在自己机器上验一遍：载荷 → 解出 → 架构/签名 → 二进制能不能起来（--version）。

    不碰宿主、不占端口，装完想确认就在插件目录里跑
        python3 gateway.py --selftest
    """
    arch = this_arch() or "?"
    log("[selftest] macOS %s / %s / python %s%s"
        % (platform.mac_ver()[0] or "?", arch, platform.python_version(),
           "（Rosetta）" if running_under_rosetta() else ""))
    payload, payload_name = load_payload(arch)
    if not payload:
        return die(2, "[selftest] 插件目录里没有可用载荷：%s" % HERE)
    path = payload_path(payload.get("arch") or arch)
    log("[selftest] 载荷 %s  %.2f MB  sha256=%s…"
        % (payload_name, os.path.getsize(path) / 1048576.0, payload["sha256"][:16]))
    target = install_target()
    try:
        binary = extract(payload, payload_name, target)
    except Exception as exc:
        return die(1, "[selftest] 解出失败：%s" % exc)
    got_arch, signed = macho_arch(binary)
    log("[selftest] 二进制 %s  架构=%s  代码签名=%s" % (binary, got_arch, "有" if signed else "无"))
    if got_arch == "arm64" and not signed:
        log("[selftest] arm64 没签名，补 ad-hoc 签名")
        adhoc_sign(binary)
        got_arch, signed = macho_arch(binary)
    try:
        r = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=60)
        out = (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return die(1, "[selftest] 起不来：%s（如果是 killed: 9，就是签名/架构问题）" % exc)
    log("[selftest] %s -version -> rc=%d  %s" % (binary, r.returncode, out.replace("\n", " ")[:200]))
    if r.returncode != 0:
        return die(1, "[selftest] 二进制自己报了错，先看上面那行输出")
    log("[selftest] PASS —— 二进制能跑。接着：把 PAT 放进 ~/.qoder-api/pat.txt，"
        "然后在插件中心启动它；key 会在 ~/.qoder-api/key.txt 里生成")
    return 0


def main():
    global current_addr
    if "--selftest" in sys.argv:
        return selftest()
    if "--quota" in sys.argv:
        return print_quota(os.environ.get("QODER_GW_ADDR") or read_conf().get("addr") or DEFAULT_ADDR)
    if sys.platform != "darwin":
        return die(4,
                   "这个插件是给 macOS 用的（%s/%s）。" % (sys.platform, platform.machine()),
                   "Windows 请装插件市场里的「Qoder 网关」qoder-gateway；",
                   "Linux 请用同一份源码自己 go build（源码在 qoderapi-gw 仓库）。")

    arch = this_arch() or "arm64"
    conf = read_conf()
    addr = os.environ.get("QODER_GW_ADDR") or conf.get("addr") or DEFAULT_ADDR
    current_addr = addr
    region = os.environ.get("QODER_GW_REGION") or conf.get("region") or "global"
    extra = list(conf.get("args") or [])

    log("[env] macOS %s / %s（python %s）%s"
        % (platform.mac_ver()[0] or "?", arch, platform.python_version(),
           "，Rosetta" if running_under_rosetta() else ""))

    payload, payload_name = load_payload(arch)
    if payload:
        log("[payload] 插件自带二进制：%s sha256=%s… %.2fMB 压缩载荷"
            % (payload_name, payload["sha256"][:16],
               os.path.getsize(payload_path(payload.get("arch") or arch)) / 1048576.0))

    # 用量显示：线程必须在分支**之前**起。端口上已有网关时（启动器被杀过、网关成了
    # 孤儿；或先手起过一次），下面走的是"只监督"那条路，永远不会执行到启动网关的代码，
    # 用量就再也没人写 —— 而这条线程只依赖 /qoder/usage，端口上是哪个实例起的网关
    # 都无所谓，所以提到前面来，两条分支共用。
    quota_stop = threading.Event()
    threading.Thread(target=quota_loop, args=(quota_stop, addr), daemon=True).start()

    if health(addr) is not None:
        if not watch_existing(addr):
            log("[takeover] 被看守的网关已退出，立即由本插件拉起新实例")

    binary, why = ensure_binary(conf, payload, payload_name)
    if not binary:
        return die(2,
                   "找不到 %s（%s）。可以：" % (BIN_NAME, why),
                   "  1) 保持插件自带的 qoder-gw-macos-<arch>.bin.json（默认就能用）",
                   "  2) 在 qoder-gw.json 里写 {\"bin\": \"/usr/local/bin/QoderAPI\"}",
                   "  3) 或设环境变量 QODER_GW_BIN=/usr/local/bin/QoderAPI",
                   "  找过的位置：%s" % ", ".join(local_candidates()))

    got_arch, signed = macho_arch(binary)
    log("[binary] %s（%s，%s%s）"
        % (binary, why, got_arch or "未知架构", "，有签名" if signed else "，无签名"))
    if got_arch and got_arch != arch:
        log("[warn] 这个二进制是 %s，本机是 %s —— Rosetta 能跑但要慢一截；"
            "想用原生版就删掉它让插件重新解" % (got_arch, arch))

    if port_open(addr) and not wait_port_free(addr, 15):
        return die(3,
                   "%s 被别的进程占着，而且它不是 Qoder 网关（/health 没应答）。" % addr,
                   "换个端口：qoder-gw.json 里写 {\"addr\": \"127.0.0.1:33001\"}，"
                   "或设 QODER_GW_ADDR。")

    proc = start_gateway(binary, addr, region, extra)

    code = supervise(proc)
    quota_stop.set()
    if got_arch == "arm64" and not signed and code not in (0, None):
        # 最可能的原因：arm64 没有代码签名，内核把它杀了（killed: 9，无输出）。
        log("网关异常退出（code=%s），可能是缺少代码签名；补 ad-hoc 签名后重试一次" % code)
        if adhoc_sign(binary):
            proc = start_gateway(binary, addr, region, extra)
            code = supervise(proc)
    log("网关退出，code=%s" % code)
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
