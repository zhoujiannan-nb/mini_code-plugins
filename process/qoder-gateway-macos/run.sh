#!/bin/sh
# Qoder 网关（苹果版）的入口脚本。
#
# 为什么不直接在 plugin.json 里写 command="python3"：macOS 上的 python3 来自
# 「Xcode 命令行工具」，没装过的机器上根本没有这个命令（Apple 从 12.3 起就不再
# 自带 python2，也没有预装 python3）。用一个 sh 包装，可以在缺 python 的时候给出
# 一句人能照做的话，而不是让插件中心里只显示 "exec: python3: not found"。
#
# 另一个存在感更强的理由：Apple Silicon 上系统自带的 /usr/bin/python3 在
# 12.3~14 之间是 arm64 的；如果你装的是 Homebrew 的 intel python（Rosetta），
# gateway.py 会自己认出 Rosetta 并选 amd64 载荷，这一层不用管。

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

pick_python() {
  # 1) 用户自己的 venv / pyenv 优先（PATH 上的第一个）
  for c in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
        command -v "$c"
        return 0
      fi
    fi
  done
  return 1
}

PY=$(pick_python) || {
  echo "[qoder-gateway-macos] 找不到 Python 3.8+。"
  echo "[qoder-gateway-macos] macOS 自带的 python3 属于「Xcode 命令行工具」，一条命令就能装好："
  echo "[qoder-gateway-macos]     xcode-select --install"
  echo "[qoder-gateway-macos] 或者用 Homebrew：brew install python@3.12"
  echo "[qoder-gateway-macos] 装完在插件中心重启这个插件就行（不用重装）。"
  exit 2
}

# 让 python 的 stdout/stderr 立刻可见（宿主按行抓日志），并用 UTF-8 输出。
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export LC_ALL=${LC_ALL:-en_US.UTF-8}
export LANG=${LANG:-en_US.UTF-8}

echo "[qoder-gateway-macos] python = $PY ($("$PY" -V 2>&1))"
exec "$PY" "$HERE/gateway.py" "$@"
