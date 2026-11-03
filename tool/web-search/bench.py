#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web-search 插件的回归基准 —— 改完引擎层，跑一下就知道有没有变差。

    python bench.py                     # 10 条查询，算可用率 / P50 / P95
    python bench.py --durability 12     # 同一条查询连打 12 次，看引擎被限流衰减
    python bench.py --read              # 顺带测 6 个网页的正文抽取
    python bench.py --mode fast --json out.json

"可用"的口径和插件的判定一致：有结果、relevance >= gate、且 degraded=false。
宿主那边只看 stdout，所以这里也照宿主的姿势调用：参数走 stdin，计时包住整个子进程。
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

QUERIES = [
    "sglang 0.5 发布时间",
    "vllm speculative decoding 原理",
    "python 3.14 release date",
    "rust 1.90 release notes",
    "pytorch 2.8 cuda 12.8 support",
    "小龙虾 养殖 技术 要点",
    "上海 地铁 运营时间 最新",
    "numpy 2.0 migration guide",
    "kubernetes 1.33 新特性",
    "openclaw 插件 机制",
]

READ_URLS = [
    "https://docs.python.org/3/whatsnew/3.14",
    "https://blog.rust-lang.org/2025/09/18/Rust-1.90.0.html",
    "https://en.wikipedia.org/wiki/Speculative_decoding",
    "https://www.runoob.com/rust/rust-tutorial.html",
    "https://zhuanlan.zhihu.com/p/1952470308438692875",      # 登录墙：预期拿不到正文
    "https://this-domain-really-does-not-exist-42.invalid/",  # 坏域名：预期快速失败
]


def call(sub, params, timeout=180):
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "adapter.py"), sub],
                           input=json.dumps(params, ensure_ascii=False).encode("utf-8"),
                           capture_output=True, timeout=timeout)
        out, err, rc = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), p.returncode
    except subprocess.TimeoutExpired:
        return {"ok": False, "wall_ms": int((time.time() - t0) * 1000), "err": "子进程超时"}
    wall = int((time.time() - t0) * 1000)
    data = None
    try:
        data = json.loads(out)
    except ValueError:
        pass
    return {"wall_ms": wall, "rc": rc, "data": data, "out": out, "err": err.strip()}


def pct(xs, q):
    if not xs:
        return 0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def bench_search(args):
    rows = []
    for q in QUERIES:
        params = {"query": q, "max": args.max}
        if args.mode:
            params["mode"] = args.mode
        r = call("search", params)
        d = r.get("data") or {}
        usable = bool(d.get("ok")) and not d.get("degraded") and \
            float(d.get("relevance") or 0) >= args.gate
        rows.append({"query": q, "usable": usable, "ok": d.get("ok"),
                     "rel": d.get("relevance"), "degraded": d.get("degraded"),
                     "engine": d.get("engine"), "channel": d.get("channel"),
                     "count": d.get("count"), "elapsed_ms": d.get("elapsed_ms"),
                     "wall_ms": r["wall_ms"], "warning": d.get("warning") or r.get("err")})
        print("  %-34s %s %-8s rel=%-4s %5dms (%5dms) %s"
              % (q[:34], "OK " if usable else "DEG", d.get("engine"), d.get("relevance"),
                 d.get("elapsed_ms") or 0, r["wall_ms"], str(rows[-1]["warning"])[:50]))
    return rows


def bench_durability(args):
    rows = []
    for i in range(1, args.durability + 1):
        r = call("search", {"query": args.query, "mode": args.mode or "fast", "max": 5})
        d = r.get("data") or {}
        usable = bool(d.get("ok")) and not d.get("degraded")
        rows.append({"i": i, "usable": usable, "engine": d.get("engine"),
                     "rel": d.get("relevance"), "elapsed_ms": d.get("elapsed_ms"),
                     "wall_ms": r["wall_ms"]})
        print("  #%02d %s %-8s rel=%-4s %5dms" % (i, "OK " if usable else "DEG",
                                                  d.get("engine"), d.get("relevance"),
                                                  r["wall_ms"]))
        time.sleep(args.sleep)
    return rows


def bench_read(args):
    rows = []
    for url in READ_URLS:
        r = call("read", {"url": url, "max_chars": 2000})
        head = (r.get("out") or "").strip().splitlines()
        meta = head[-1] if head else ""
        chars = len(r.get("out") or "")
        rows.append({"url": url, "rc": r.get("rc"), "chars": chars, "wall_ms": r["wall_ms"],
                     "meta": meta[:160]})
        print("  %-52s rc=%s %6d chars %6dms %s"
              % (url[:52], r.get("rc"), chars, r["wall_ms"], meta[:60]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--gate", type=float, default=0.5)
    ap.add_argument("--mode", default=None, choices=["auto", "fast", "browser"])
    ap.add_argument("--durability", type=int, default=0)
    ap.add_argument("--query", default="vllm speculative decoding 原理")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args()

    report = {"gate": a.gate, "mode": a.mode or "auto"}
    print("== search ==")
    rows = bench_search(a)
    report["search"] = rows
    walls = [r["wall_ms"] for r in rows]
    inner = [r["elapsed_ms"] for r in rows if r["elapsed_ms"]]
    good = sum(1 for r in rows if r["usable"])
    report["summary"] = {
        "usable": "%d/%d" % (good, len(rows)),
        "rate": round(good / float(len(rows)), 3) if rows else 0,
        "p50_ms": pct(inner, 0.5), "p95_ms": pct(inner, 0.95),
        "max_ms": max(inner) if inner else 0,
        "p50_wall_ms": pct(walls, 0.5), "p95_wall_ms": pct(walls, 0.95),
        "engines": {e: sum(1 for r in rows if r["engine"] == e)
                    for e in set(r["engine"] for r in rows)},
    }
    print("\n可用率 %s  P50 %dms  P95 %dms  最差 %dms  引擎分布 %s"
          % (report["summary"]["usable"], report["summary"]["p50_ms"],
             report["summary"]["p95_ms"], report["summary"]["max_ms"],
             report["summary"]["engines"]))

    if a.durability:
        print("\n== durability (%s) ==" % a.query)
        report["durability"] = bench_durability(a)
    if a.read:
        print("\n== read ==")
        report["read"] = bench_read(a)

    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("\n[写出] %s" % a.json_out)
    return 0 if report["summary"]["rate"] >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
