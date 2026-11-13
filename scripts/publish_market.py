#!/usr/bin/env python3
"""把 dist/pkgs 下的技能包发布到 marketplace 分支，并整体替换该分支内容。

该分支只放构建产物：3 个许可允许再分发的技能镜像 + 13 个取件器（我们自己的代码）。
早期版本曾在这里放过「全量市场 zip」，那等于把全部正文副本塞进本仓，已废弃；
整体替换会把这类历史产物一并清掉。

用法：
    python3 scripts/pack_market.py     # 先出包，会同时写好 marketplace.json
    python3 scripts/publish_market.py  # 再发布
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = "openfcp/awesome-financial-skills"
BRANCH = "marketplace"
PKG_DIR = ROOT / "dist" / "pkgs"


def api(method: str, path: str, payload=None, tries: int = 5) -> dict:
    """调 GitHub API，带退避重试：本机出口代理偶发 502。"""
    token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
    data = json.dumps(payload).encode() if payload is not None else None
    last = ""
    for i in range(tries):
        req = urllib.request.Request(f"https://api.github.com{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "afs-market-publisher")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            if e.code in (502, 503, 504) and i < tries - 1:
                last = f"HTTP {e.code}"
                time.sleep(5 * (i + 1))
                continue
            raise SystemExit(f"HTTP {e.code} {method} {path}\n{detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
            if i < tries - 1:
                time.sleep(5 * (i + 1))
                continue
            raise SystemExit(f"网络失败 {method} {path}: {e}")
    raise SystemExit(f"重试 {tries} 次仍失败：{last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(PKG_DIR), help=f"技能包目录（默认 {PKG_DIR}）")
    a = ap.parse_args()

    pkg_dir = Path(a.dir).expanduser()
    # 只上传清单里点名的包：清单是唯一真相，多余的 zip 不该被推上分支
    index = json.loads((ROOT / "marketplace.json").read_text(encoding="utf-8"))
    wanted = [p["name"] for p in index.get("plugins", [])]
    all_zips = {p.stem: p for p in sorted(pkg_dir.glob("*.zip"))}
    zips = [all_zips[n] for n in wanted if n in all_zips]
    absent = [n for n in wanted if n not in all_zips]
    extra = sorted(set(all_zips) - set(wanted))
    if absent:
        raise SystemExit(f"[publish] 清单里有 {len(absent)} 条没有对应的包：{', '.join(absent)}\n"
                         f"          先跑 python3 scripts/pack_market.py 补齐，或把它们从 catalog 删掉。")
    if extra:
        print(f"[publish] 跳过 {len(extra)} 个不在清单里的包：{', '.join(extra)}")
    if not zips:
        raise SystemExit(f"[publish] {pkg_dir} 里没有 zip，先跑 python3 scripts/pack_market.py")
    print(f"[publish] {len(zips)} 个包，合计 {sum(p.stat().st_size for p in zips)/1024/1024:.2f} MB")

    head = None
    try:
        head = api("GET", f"/repos/{SLUG}/git/ref/heads/{BRANCH}")["object"]["sha"]
    except SystemExit:
        print(f"[publish] 分支 {BRANCH} 不存在，将新建")

    tree_entries = []
    for p in zips:
        data = p.read_bytes()
        blob = api("POST", f"/repos/{SLUG}/git/blobs",
                   {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        tree_entries.append({"path": f"pkgs/{p.name}", "mode": "100644",
                             "type": "blob", "sha": blob["sha"]})
        print(f"  ↑ pkgs/{p.name}  {len(data)/1024:.1f} KB")

    # 不带 base_tree ⇒ 新树只含这些包，分支上的历史产物被清掉
    tree = api("POST", f"/repos/{SLUG}/git/trees", {"tree": tree_entries})
    commit = api("POST", f"/repos/{SLUG}/git/commits", {
        "message": f"chore: 市场包 {datetime.now():%Y-%m-%d %H:%M}\n\n"
                   "许可允许再分发的技能出镜像包；未授权的只出取件器（不含他人正文）。",
        "tree": tree["sha"],
        "parents": [head] if head else [],
    })
    if head:
        api("PATCH", f"/repos/{SLUG}/git/refs/heads/{BRANCH}", {"sha": commit["sha"], "force": True})
    else:
        api("POST", f"/repos/{SLUG}/git/refs", {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
    print(f"[publish] {BRANCH} → {commit['sha'][:10]}（{len(tree_entries)} 个包）")

    print("\n[publish] 添加市场 → 市场源，填这一条：")
    print(f"  https://raw.githubusercontent.com/{SLUG}/main/marketplace.json")
    print(f"  （清单 {len(index['plugins'])} 条，均为 archive 源）")
    print("\n[publish] 注意：分支已换新包，main 上的 marketplace.json 还是旧的 sha256。")
    print("          紧接着跑 ./scripts/release.sh 推 main，否则这段时间点装会校验失败。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
