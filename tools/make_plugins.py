# -*- coding: utf-8 -*-
"""重建 index.json，并把 boot-anim/<id>/theme.json 升级为插件。

两类插件在这个仓库里的写法不一样，这是有意为之：

  boot-anim/<id>/   theme.json 是**真源**，plugin.json 由它派生（本脚本生成）
  <bucket>/<id>/    plugin.json 就是**真源**（工具/皮肤/进程插件没有 theme.json 这个东西）

  boot-anim/<id>/plugin.json   <- 派生：kind=appearance + boot 块
  boot-anim/<id>/theme.json    <- 保留（宿主仍可读它补齐时长/options，老宿主也能用）
  tool/<id>/plugin.json        <- 手写：kind=tool + tools[]

为什么还要留 theme.json：它是"动画自己的清单"，里面有时长、options（品牌文案、
语音）这些纯动画数据；plugin.json 只声明"这个目录是个插件、开机动画入口是哪个"。
宿主优先用 plugin.json 的 boot 块，缺的字段再回落到 theme.json（见 web/bootanim.go）。

index.json 的桶：
  kinds["appearance"]  插件中心读的那一份（含 boot 块的外观插件）
  kinds["boot-anim"]   只认这个桶的老宿主的兼容别名（少一个 category 字段）
  kinds["tool"] / ["process"] / ["skin"] / ["wallpaper"]   其余各类（plugin.json 为源）

**所有校验都在写盘之前**：这里报红的每一条，都对应宿主安装时的一次失败。
"""
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "boot-anim")

# plugin.json 即真源的那些桶 -> 插件中心里的分类（宿主 plugin.Plugin.Category() 的口径）
PLAIN_BUCKETS = {
    "tool": "tool",
    "process": "process",
    "skin": "appearance",
    "wallpaper": "appearance",
}

# ---- 宿主的硬约束，抄自 mini_code，改那边要同步这里 -------------------------
# config.ValidBootAnimID：小写字母数字减号，首尾不能是减号，能当 URL 段和目录名
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# plugin.toolIDPattern
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
# 内置工具名：插件工具与它们重名会被宿主直接忽略（并记一条 WARN）
CORE_TOOLS = {
    "read_file", "write_file", "edit_file", "exec", "search_files", "list_dir",
    "glob", "copy_file", "move_file", "delete_file", "readimg", "skills",
    "task", "compact_context", "context_usage",
}
MAX_FILES = 40              # web/pluginCatalogueMaxFiles
MAX_FILE_BYTES = 8 << 20    # web/pluginMaxFileBytes
MAX_TOTAL_BYTES = 24 << 20  # web/pluginMaxTotalBytes
MAX_TIMEOUT = 600           # plugin.validate(): timeout_seconds 上限
# web/catalogueDownloadExtTypes：不在表里的文件类型，安装直接被拒
DOWNLOAD_EXT = {
    ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".woff", ".woff2", ".ttf", ".otf", ".html", ".htm",
    ".js", ".mjs", ".json", ".md", ".py", ".sh", ".mp3", ".ogg", ".wav", ".ico",
}
SKIP = {".ds_store", "thumbs.db", "desktop.ini"}

SEMVER = lambda s: all(c.isdigit() or c == "." for c in s) and s.count(".") == 2


def sha(b):
    return hashlib.sha256(b).hexdigest()


def file_list(path):
    """目录 -> [{path,size,sha256}]，path 相对仓库根目录。目录必须是扁平的。"""
    rel_dir = os.path.relpath(path, ROOT).replace("\\", "/")
    out = []
    for name in sorted(os.listdir(path)):
        p = os.path.join(path, name)
        if name.startswith(".") or name.lower() in SKIP:
            continue
        if not os.path.isfile(p):
            raise SystemExit("[FAIL] %s: 插件目录里只允许文件，发现子目录或链接" % p)
        blob = open(p, "rb").read()
        out.append({
            "path": rel_dir + "/" + name,
            "size": len(blob),
            "sha256": sha(blob),
        })
    return out


def plugin_json(theme):
    """由 theme.json 生成 plugin.json。

    boot 块里只放"宿主需要用来播"的东西(入口 + 时长),其余(品牌文案、语音语言)
    留在 theme.json 的 options 里 —— 它们是动画自己的事。
    """
    m = {
        "id": theme["id"],
        "name": theme["name"],
        "version": theme.get("version", "1.0.0"),
        "kind": "appearance",
        "author": theme.get("author", ""),
        "description": theme.get("description", ""),
        "boot": {
            "entry": theme.get("entry", "index.html"),
            "preview": theme.get("preview", ""),
            "durationMs": int(theme.get("durationMs", 0)),
            "maxMs": int(theme.get("maxMs", 0)),
            "interactive": bool(theme.get("interactive", False)),
            "minViewport": int(theme.get("minViewport", 480)),
            "tags": theme.get("tags", []),
        },
    }
    return m


def rel_ok(rel):
    """manifest 里引用的文件必须是插件目录内的相对路径（宿主 FilePath 的口径）。"""
    if not rel or rel.startswith(("/", "\\")) or os.path.isabs(rel):
        return False
    parts = rel.replace("\\", "/").split("/")
    return ".." not in parts and "" not in parts


# --------------------------------------------------------------------------
# 非派生插件（tool / process / skin / wallpaper）：plugin.json 就是真源
# --------------------------------------------------------------------------

def check_manifest(bucket, tid, m, d):
    """按宿主的 validate() + 安装器的约束查一遍，返回问题列表（空 = 干净）。"""
    bad = []
    pid = m.get("id", "")
    if pid != tid:
        bad.append("id(%s) 与目录名(%s) 不一致 —— 宿主装完会校验失败并回滚" % (pid, tid))
    if not PLUGIN_ID_RE.match(pid or ""):
        bad.append("id %r 不合法：只许小写字母/数字/减号，且以字母数字开头" % pid)
    if m.get("enabled") is False:
        bad.append("enabled:false 的插件在插件中心里【点不亮】—— 状态文件只往「关」的集合里加，"
                   "从不覆盖 manifest；要么删掉这个键，要么写 true")
    ver = str(m.get("version", ""))
    if not SEMVER(ver):
        bad.append("version %r 要写成 x.y.z（市场的「有新版本」按它判断）" % ver)
    if not str(m.get("name", "")).strip():
        bad.append("缺 name（卡片标题会是空的）")
    if not str(m.get("description", "")).strip():
        bad.append("缺 description")

    kind = str(m.get("kind", "")).lower()
    if kind != bucket and bucket == "tool":
        bad.append("kind=%r 与它所在的桶 %s/ 不一致" % (m.get("kind"), bucket))

    names = []
    for i, t in enumerate(m.get("tools") or []):
        nm = t.get("name", "")
        tag = "tools[%d](%s)" % (i, nm or "?")
        if not TOOL_NAME_RE.match(nm or ""):
            bad.append("%s name 不匹配 ^[a-z][a-z0-9_]{1,63}$" % tag)
        if nm in CORE_TOOLS:
            bad.append("%s 与内置工具重名，宿主会直接忽略这个工具" % tag)
        if nm in names:
            bad.append("%s 名字重复" % tag)
        names.append(nm)
        if not str(t.get("command", "")).strip():
            bad.append("%s 没有 command（必填，直接 exec，不经 shell）" % tag)
        ts = t.get("timeout_seconds")
        if ts is not None and not (0 < int(ts) <= MAX_TIMEOUT):
            bad.append("%s timeout_seconds=%r 要在 1..%d" % (tag, ts, MAX_TIMEOUT))
        if not str(t.get("description", "")).strip():
            bad.append("%s 没有 description（模型靠它决定什么时候调）" % tag)
        par = t.get("parameters") or {}
        if par.get("type") != "object" or not (par.get("properties") or {}):
            bad.append("%s parameters 要写成 {type:object, properties:{…}}" % tag)

    # manifest 引用的文件必须存在且在本目录内
    refs = list(m.get("styles") or [])
    for key in ("wallpaper", "memory"):
        if m.get(key):
            refs.append(m[key])
    boot = m.get("boot") or {}
    for key in ("entry", "preview"):
        if boot.get(key):
            refs.append(boot[key])
    for slot in (m.get("ui") or {}).get("slots") or []:
        if slot.get("html"):
            refs.append(slot["html"])
    for rel in refs:
        if not rel_ok(rel):
            bad.append("引用的路径 %r 必须是插件目录内的相对路径" % rel)
        elif not os.path.isfile(os.path.join(d, rel)):
            bad.append("引用的文件不存在：%s" % rel)

    # 工具插件的 args 只是子命令/脚本名，参数走 stdin —— 别在这里拼用户输入
    for t in m.get("tools") or []:
        for a in t.get("args") or []:
            if "%s" in a or "{query}" in a or "$" in a:
                bad.append("tools(%s) 的 args 里像是有占位符：参数只能走 stdin" % t.get("name"))
    return bad


def collect_plain():
    """扫 tool/ process/ skin/ wallpaper/，返回 {bucket: [index 条目]}。"""
    buckets = {}
    for bucket, category in sorted(PLAIN_BUCKETS.items()):
        base = os.path.join(ROOT, bucket)
        items = []
        if not os.path.isdir(base):
            buckets[bucket] = items
            continue
        for tid in sorted(os.listdir(base)):
            d = os.path.join(base, tid)
            pj = os.path.join(d, "plugin.json")
            if not os.path.isdir(d) or not os.path.isfile(pj):
                continue
            with io.open(pj, encoding="utf-8") as f:
                m = json.load(f)
            bad = check_manifest(bucket, tid, m, d)
            if bad:
                for x in bad:
                    print(u"[FAIL] %s/%s: %s" % (bucket, tid, x))
                raise SystemExit(1)
            files = file_list(d)
            total = sum(f["size"] for f in files)
            if len(files) > MAX_FILES:
                raise SystemExit("[FAIL] %s/%s: %d 个文件，超过宿主上限 %d"
                                 % (bucket, tid, len(files), MAX_FILES))
            if total > MAX_TOTAL_BYTES:
                raise SystemExit("[FAIL] %s/%s: 共 %.1fMB，超过宿主上限 %dMB"
                                 % (bucket, tid, total / 1048576.0, MAX_TOTAL_BYTES >> 20))
            for f in files:
                ext = os.path.splitext(f["path"])[1].lower()
                if ext not in DOWNLOAD_EXT:
                    raise SystemExit("[FAIL] %s: 宿主的下载白名单里没有 %s，装不上"
                                     % (f["path"], ext or "（无扩展名）"))
                if f["size"] > MAX_FILE_BYTES:
                    raise SystemExit("[FAIL] %s: 单文件超过 %dMB"
                                     % (f["path"], MAX_FILE_BYTES >> 20))
            item = {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "nameEn": m.get("nameEn", ""),
                "author": m.get("author", ""),
                "version": m.get("version", ""),
                "license": m.get("license", "MIT"),
                "description": m.get("description", ""),
                "path": "%s/%s" % (bucket, tid),
                "category": category,
                "tags": m.get("tags") or (m.get("boot") or {}).get("tags") or [],
                "tools": [t["name"] for t in (m.get("tools") or [])],
                # 外部依赖写在卡片描述里也看得见，这个字段是给"详情"留的余地
                "requires": m.get("requires", ""),
                # 宿主按这张表逐个 raw 下载，sha256 校验后原子落盘
                "files": files,
            }
            items.append(item)
        buckets[bucket] = items
    return buckets


# --------------------------------------------------------------------------

def build_index():
    """扫全仓库 -> index.json 的那份 dict（不写盘）。

    写盘（make_plugins.main）和自查（make_index.py --check）都走这里，
    否则 --check 只看得见 boot-anim，新加的 tool/ 会被判成"索引里多出来了"。
    """
    idx_path = os.path.join(ROOT, "index.json")
    old = json.load(io.open(idx_path, encoding="utf-8")) if os.path.isfile(idx_path) else {}

    appearance = []
    for tid in sorted(os.listdir(SRC)):
        d = os.path.join(SRC, tid)
        tj = os.path.join(d, "theme.json")
        if not os.path.isdir(d) or not os.path.isfile(tj):
            continue
        theme = json.load(io.open(tj, encoding="utf-8"))
        item = {
            "id": theme["id"],
            "name": theme["name"],
            "nameEn": theme.get("nameEn", ""),
            "author": theme.get("author", ""),
            "version": theme["version"],
            "license": theme.get("license", "MIT"),
            "description": theme.get("description", ""),
            "path": "boot-anim/" + tid,
            "entry": theme.get("entry", "index.html"),
            "preview": theme.get("preview", ""),
            "durationMs": int(theme.get("durationMs", 0)),
            "maxMs": int(theme.get("maxMs", 0)),
            "colors": theme.get("colors", ["dark"]),
            "interactive": bool(theme.get("interactive", False)),
            "minViewport": int(theme.get("minViewport", 480)),
            "tags": theme.get("tags", []),
            "options": theme.get("options", {}),
            "category": "appearance",
            # 宿主按这张表逐个 raw 下载,sha256 校验后原子落盘。
            "files": file_list(d),
        }
        appearance.append(item)

    kinds = {}
    kinds["appearance"] = appearance
    # boot-anim 桶留着:老宿主(只认这个桶)仍能装;新宿主从 appearance 读。
    kinds["boot-anim"] = [
        {k: v for k, v in it.items() if k != "category"} for it in appearance
    ]
    # 其余各类（tool/process/skin/wallpaper）：plugin.json 即真源，扫一遍收进来。
    # 空的桶不写：省得市场里出现一类"点进去什么都没有"的分组。
    plain = collect_plain()
    for bucket in sorted(plain):
        if plain[bucket]:
            kinds[bucket] = plain[bucket]
    # 其余未知的桶原样保留(将来加了别的 kind 不至于被这个脚本抹掉),
    # 排序后再拼,保证同样的输入永远生成逐字节相同的 index.json。
    for k in sorted((old.get("kinds") or {}).keys()):
        if k not in kinds and old["kinds"][k]:
            kinds[k] = old["kinds"][k]

    return {
        "schema": 1,
        "repo": "https://github.com/zhoujiannan-nb/mini_code-plugins",
        "ref": "main",
        "kinds": kinds,
    }


def main():
    wrote = []
    for tid in sorted(os.listdir(SRC)):
        d = os.path.join(SRC, tid)
        tj = os.path.join(d, "theme.json")
        if not os.path.isdir(d) or not os.path.isfile(tj):
            continue
        theme = json.load(io.open(tj, encoding="utf-8"))
        if theme.get("id") != tid:
            sys.exit("[FAIL] %s: id(%s) 与目录名不一致" % (tj, theme.get("id")))
        pj = plugin_json(theme)
        target = os.path.join(d, "plugin.json")
        with io.open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(pj, ensure_ascii=False, indent=2) + "\n")
        wrote.append(tid)
        print("[OK] %-12s -> plugin.json (boot.entry=%s, %dms)"
              % (tid, pj["boot"]["entry"], pj["boot"]["durationMs"]))

    if not wrote:
        sys.exit("[FAIL] boot-anim/ 下没有 theme.json,没东西可升级")

    data = build_index()
    kinds = data["kinds"]
    idx_path = os.path.join(ROOT, "index.json")
    with io.open(idx_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("[OK] index.json: appearance=%d, boot-anim=%d"
          % (len(kinds["appearance"]), len(kinds["boot-anim"])))
    for bucket in sorted(PLAIN_BUCKETS):
        if kinds.get(bucket):
            print("[OK] index.json: %-10s %d 个" % (bucket, len(kinds[bucket])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
