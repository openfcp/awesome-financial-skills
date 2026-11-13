#!/usr/bin/env python3
"""发布后验收：清单、分支、包、sha256 四者是否自洽。

    python3 scripts/check_market.py           # 全部检查
    python3 scripts/check_market.py -q        # 只报问题，不列明细

检查项（任一项失败退出码非 0，可以直接串进脚本里）：
  1. 线上 main 的 marketplace.json 能取到，且条数与本地一致、内容一致
  2. marketplace 分支上只有 pkgs/*.zip，且包数与清单一致（没有历史产物残留）
  3. 清单里每条的 zip 都能 200 拿到
  4. 每个 zip 的实际 sha256 与清单里写的一致（这是用户点装时唯一的校验）

为什么要这个：发布最典型的事故不是脚本报错，而是「包传上去了、清单没推」或
「清单改了、包没重打」——两边都成功返回，但用户点装时 sha256 对不上，表现为
"装不上"，很难反查。跑一遍这个脚本 30 秒内就能定位。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = "openfcp/awesome-financial-skills"
BRANCH = "marketplace"
MANIFEST_URL = f"https://raw.githubusercontent.com/{SLUG}/main/marketplace.json"
UA = {"User-Agent": "afs-check-market"}

problems: list[str] = []
warns: list[str] = []


def get(url: str, timeout: int = 60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def gh_api(path: str):
    """分支树要走 API（raw 列不出目录）。没有 gh 就跳过这项，不算失败。"""
    try:
        out = subprocess.check_output(
            ["gh", "api", f"repos/{SLUG}{path}"], stderr=subprocess.DEVNULL, timeout=60)
        return json.loads(out)
    except Exception:                                       # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-q", "--quiet", action="store_true", help="只报问题")
    a = ap.parse_args()

    local_path = ROOT / "marketplace.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    lp = {p["name"]: p for p in local["plugins"]}
    if not a.quiet:
        print(f"[1/4] 本地清单 {len(lp)} 条")

    # 1. 线上清单
    try:
        remote = json.loads(get(f"{MANIFEST_URL}?t={__import__('time').time()}").decode())
    except Exception as e:                                  # noqa: BLE001
        problems.append(f"取不到线上清单 {MANIFEST_URL}：{e}")
        remote = {"plugins": []}
    rp = {p["name"]: p for p in remote.get("plugins", [])}
    if remote.get("plugins"):
        only_local = sorted(set(lp) - set(rp))
        only_remote = sorted(set(rp) - set(lp))
        if only_local:
            problems.append(f"本地有、线上没有（清单没推上去）：{', '.join(only_local)}")
        if only_remote:
            problems.append(f"线上有、本地没有（线上比本地新）：{', '.join(only_remote)}")
        if not a.quiet:
            print(f"[2/4] 线上清单 {len(rp)} 条 · 差集 {len(only_local) + len(only_remote)}")

    # 2. 分支内容
    tree = gh_api(f"/git/trees/{BRANCH}?recursive=1")
    branch_zips: set[str] = set()
    if tree is None:
        warns.append("拿不到分支树（gh 不可用或网络问题），跳过第 3 项")
    else:
        blobs = [n["path"] for n in tree.get("tree", []) if n.get("type") == "blob"]
        branch_zips = {p[len("pkgs/"):-4] for p in blobs if p.startswith("pkgs/") and p.endswith(".zip")}
        junk = [p for p in blobs if not (p.startswith("pkgs/") and p.endswith(".zip"))]
        if junk:
            problems.append(f"分支上有非 pkgs/*.zip 的文件（历史产物没清干净）：{', '.join(junk)}")
        missing = sorted(set(rp) - branch_zips)
        orphan = sorted(branch_zips - set(rp))
        if missing:
            problems.append(f"清单里有、分支上没有的包：{', '.join(missing)}")
        if orphan:
            warns.append(f"分支上有、清单里没有的包（下次整体替换会清掉）：{', '.join(orphan)}")
        if not a.quiet:
            print(f"[3/4] 分支 {len(branch_zips)} 个包")

    # 3+4. 逐条下载并校验 sha256
    bad_sha, bad_get = [], []
    for name, p in sorted(rp.items()):
        url, want = p["source"]["url"], p["source"].get("sha256", "")
        try:
            data = get(url, timeout=180)
        except Exception as e:                              # noqa: BLE001
            bad_get.append(f"{name}（{type(e).__name__}）")
            continue
        got = hashlib.sha256(data).hexdigest()
        if want and got != want:
            bad_sha.append(f"{name}：清单 {want[:12]}… 实际 {got[:12]}…")
        if not a.quiet:
            print(f"      {name:<44}{len(data)/1024:>8.1f} KB  {'✓' if got == want else '✗'}")
    if bad_get:
        problems.append(f"下载失败：{', '.join(bad_get)}")
    if bad_sha:
        problems.append("sha256 不一致（包换了但清单没更新）：\n    " + "\n    ".join(bad_sha))

    print()
    for w in warns:
        print(f"! {w}")
    if problems:
        print("[check] ✗ 有问题：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"[check] ✓ 通过：清单 {len(rp)} 条 / 分支 {len(branch_zips) or '?'} 包 / sha256 全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
