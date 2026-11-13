#!/usr/bin/env python3
"""发布后核对「客户端刷新能看到什么」。

回答一个问题：我刚发完版，用户点刷新，会不会看到旧清单？

核对四处：
  1. 本地 catalog.json 条数与 updated
  2. 线上 main 的 catalog.json（raw）
  3. 三个 jsDelivr 镜像（dsh 插件的降级链，分支缓存最长 12 小时 → 可能拿到旧版）
  4. 本机 dsh 缓存文件（~/.dsh/storages/financial-skills/catalog.cache.json）

dsh 插件的取数逻辑是「按镜像链顺序，第一个成功就用」，不比较新旧。所以只要
raw 一时不通、fastly 又是旧缓存，刷新后就会静默显示旧清单——这个脚本就是用来
发现这种情况的。

用法：
    python3 scripts/check_clients.py
    python3 scripts/check_clients.py --purge    # 先请求 jsDelivr 清缓存再测
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"

RAW = "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/catalog.json"
MIRRORS = [
    ("raw   ", RAW),
    ("fastly", "https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"),
    ("gcore ", "https://gcore.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"),
    ("cdn   ", "https://cdn.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"),
]
PURGE = "https://purge.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"

DSH_CACHE = Path.home() / ".dsh" / "storages" / "financial-skills" / "catalog.cache.json"


def get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "afs-check-clients",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def brief(doc: dict):
    skills = doc.get("skills") or []
    return len(skills), str(doc.get("updated", "?")), {s.get("id") for s in skills}


def ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().strftime("%m-%d %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--purge", action="store_true", help="先请求 jsDelivr 清缓存")
    a = ap.parse_args()

    if not CATALOG.is_file():
        print(f"[clients] 找不到 {CATALOG}")
        return 2

    local_n, local_up, local_ids = brief(json.loads(CATALOG.read_text(encoding="utf-8")))
    print(f"[clients] 本地 catalog.json ：{local_n} 条，updated={local_up}\n")

    if a.purge:
        try:
            r = get(PURGE)
            print(f"[clients] 已请求 jsDelivr 清缓存：{r.get('status')}"
                  f"（清的是 CDN 边缘缓存，不代表立即生效）\n")
        except Exception as e:                                  # noqa: BLE001
            print(f"[clients] 清缓存请求失败：{e}（不影响后续检测）\n")

    print("[clients] 镜像链（dsh 插件按此顺序取，第一个成功即用，不比较新旧）")
    stale = []
    raw_ok = False
    for name, url in MIRRORS:
        try:
            n, up, ids = brief(get(url))
            mark = "✓ 与本地一致" if ids == local_ids else f"✗ 落后/超前 {local_n - n:+d} 条"
            print(f"  {name}  {n:>3} 条  updated={up}  {mark}")
            if name.strip() == "raw":
                raw_ok = True
            if ids != local_ids:
                stale.append((name.strip(), up))
        except urllib.error.HTTPError as e:
            print(f"  {name}  HTTP {e.code}")
        except Exception as e:                                  # noqa: BLE001
            print(f"  {name}  失败：{type(e).__name__}")

    print()
    if DSH_CACHE.is_file():
        try:
            c = json.loads(DSH_CACHE.read_text(encoding="utf-8"))
            n, up, ids = brief(c.get("data", {}))
            lag = [i for i in local_ids - ids]
            extra = [i for i in ids - local_ids]
            print(f"[clients] dsh 缓存：{n} 条，updated={up}，"
                  f"抓取于 {ts(c.get('fetchedAt', 0))}")
            if extra:
                print(f"          多出（本地已无）：{', '.join(sorted(extra))}")
            if lag:
                print(f"          缺少（本地已有）：{', '.join(sorted(lag))}")
            if ids == local_ids:
                print("          ✓ 与本地一致")
        except Exception as e:                                  # noqa: BLE001
            print(f"[clients] dsh 缓存读不出来：{e}")
    else:
        print(f"[clients] 未发现 dsh 缓存（{DSH_CACHE}），说明 dsh 插件没在这个 HOME 下跑过")

    print()
    if not stale:
        print("[clients] ✓ 全部镜像与本地一致，刷新即可看到最新清单")
        return 0

    print("[clients] ! 有镜像落后：")
    for name, up in stale:
        print(f"          {name} → updated={up}")
    if not raw_ok:
        print("          raw 不通是关键：dsh 会落到 jsDelivr 的旧缓存上。")
    print("          处理：① 稍等 10–12 小时让分支缓存过期，或再跑一次 --purge；")
    print("                ② 让用户多点几次「刷新」，raw 恢复即会拿到新版；")
    print("                ③ 想立刻生效只能等 CDN，别为此改清单内容。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
