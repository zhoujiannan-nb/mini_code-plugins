#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 boot-anim/*/theme.json,校验并生成仓库根目录的 index.json。

新增主题只需要:建目录 → 放 theme.json + index.html + preview.svg → 跑本脚本 → 提交。
宿主(或下载器)只读 index.json,不猜目录结构,所以这一步不能省。
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ["boot-anim"]

REQUIRED = ["id", "name", "version", "entry", "durationMs", "maxMs"]
SEMVER = lambda s: all(c.isdigit() or c == "." for c in s) and s.count(".") == 2


SKIP = {".ds_store", "thumbs.db", "desktop.ini"}


def file_list(kind, tid):
    """主题目录下所有文件 → [{path,size,sha256}],path 相对仓库根目录。"""
    base = os.path.join(ROOT, kind, tid)
    out = []
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if name.startswith(".") or name.lower() in SKIP:
            continue
        if not os.path.isfile(p):
            # 主题目录必须是扁平的:子目录/软链接让 raw 下载和落盘两边都可能出错
            raise SystemExit("[FAIL] %s: 主题目录里只允许文件,发现 %s" % (p, "子目录或链接"))
        with io.open(p, "rb") as f:
            blob = f.read()
        out.append({
            "path": ("%s/%s/%s" % (kind, tid, name)).replace("\\", "/"),
            "size": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
        })
    return out


def load(kind, tid):
    d = os.path.join(ROOT, kind, tid)
    p = os.path.join(d, "theme.json")
    if not os.path.isfile(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f), d, p


def _flat_files(data):
    """index.json -> {文件路径: sha256},给 --check 做比对用。"""
    m = {}
    for items in (data.get("kinds") or {}).values():
        for it in items:
            for f in it.get("files", []):
                m[f["path"]] = f["sha256"]
    return m


def main():
    problems, out = [], {}
    for kind in KINDS:
        items = []
        base = os.path.join(ROOT, kind)
        if not os.path.isdir(base):
            continue
        for tid in sorted(os.listdir(base)):
            loaded = load(kind, tid)
            if not loaded:
                continue
            cfg, d, p = loaded
            for k in REQUIRED:
                if k not in cfg:
                    problems.append(u"%s: 缺字段 %s" % (p, k))
            if cfg.get("id") != tid:
                problems.append(u"%s: id(%s) 与目录名(%s) 不一致" % (p, cfg.get("id"), tid))
            if not SEMVER(str(cfg.get("version", ""))):
                problems.append(u"%s: version 要写成 x.y.z" % p)
            entry = cfg.get("entry", "index.html")
            if not os.path.isfile(os.path.join(d, entry)):
                problems.append(u"%s: entry 文件不存在 %s" % (p, entry))
            if "/" in entry or ".." in entry or "\\" in entry:
                problems.append(u"%s: entry 必须是主题目录内的相对路径" % p)
            prev = cfg.get("preview")
            if prev and not os.path.isfile(os.path.join(d, prev)):
                problems.append(u"%s: preview 不存在 %s" % (p, prev))
            if not (500 <= int(cfg.get("durationMs", 0)) <= 60000):
                problems.append(u"%s: durationMs 要在 500~60000 之间" % p)
            if int(cfg.get("maxMs", 0)) < int(cfg.get("durationMs", 0)):
                problems.append(u"%s: maxMs 必须 >= durationMs" % p)
            items.append({
                "id": cfg["id"],
                "name": cfg["name"],
                "nameEn": cfg.get("nameEn", ""),
                "author": cfg.get("author", ""),
                "version": cfg["version"],
                "license": cfg.get("license", "MIT"),
                "description": cfg.get("description", ""),
                "path": "%s/%s" % (kind, cfg["id"]),
                "entry": entry,
                "preview": prev or "",
                "durationMs": int(cfg["durationMs"]),
                "maxMs": int(cfg["maxMs"]),
                "colors": cfg.get("colors", ["dark"]),
                "interactive": bool(cfg.get("interactive", False)),
                "minViewport": int(cfg.get("minViewport", 320)),
                "tags": cfg.get("tags", []),
                "options": cfg.get("options", {}),
                # 宿主按这张表逐个 raw 下载,sha256 校验后原子落盘。
                # 路径相对仓库根目录,所以 raw URL = raw.githubusercontent.com/<repo>/<ref>/<path>。
                "files": file_list(kind, tid),
            })
        out[kind] = items

    data = {
        "schema": 1,
        "repo": "https://github.com/zhoujiannan-nb/mini_code-plugins",
        "ref": "main",
        "kinds": out,
    }
    if problems:
        for x in problems:
            print(u"[FAIL] " + x)
        return 1
    target = os.path.join(ROOT, "index.json")

    if "--check" in sys.argv:
        # 只比对不写盘:改过插件文件却忘了重新生成 index.json 时,这里就会红。
        # (宿主安装是按 index.json 里的 sha256 校验的,索引过期 = 装不上。)
        # 比对的是 make_plugins.build_index() 的**全量**结果 —— 只扫 boot-anim 会把
        # tool/ 这些别的桶误判成"索引里多出来了"。
        try:
            import make_plugins
        except ImportError:
            _s = sys
            _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import make_plugins
        try:
            cur = json.loads(io.open(target, encoding="utf-8").read())
        except Exception as e:
            print(u"[FAIL] 读不到 index.json: %s" % e)
            return 1
        try:
            fresh = make_plugins.build_index()
        except SystemExit as e:
            print(u"[FAIL] 校验没过,退出码 %s" % e)
            return 1
        old, new = _flat_files(cur), _flat_files(fresh)
        bad = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
        if bad:
            for p in bad:
                print(u"[FAIL] index.json 与插件文件不一致: %s" % p)
            print(u"       跑一次 python tools/make_plugins.py 再提交。")
            return 1
        buckets = sorted(fresh["kinds"])
        print(u"[OK] index.json 与插件文件一致(%d 个文件, %d 个桶: %s)"
              % (len(new), len(buckets), ", ".join(buckets)))
        return 0

    # 写盘这条路委托给 make_plugins.py:它除了 index.json 还要派生 plugin.json,
    # 而且 index.json 里必须有 kinds.appearance(插件中心读的那一桶)。这里再写一遍
    # 会把那一桶写丢 —— 所以只有一个写入口。
    try:
        import make_plugins
    except ImportError:
        import sys as _s
        _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import make_plugins
    print(u"[提示] 写 index.json 由 tools/make_plugins.py 负责(顺带生成 plugin.json)。")
    return make_plugins.main()


if __name__ == "__main__":
    sys.exit(main())
