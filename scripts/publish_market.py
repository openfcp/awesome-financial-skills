#!/usr/bin/env python3
"""publish_market.py — 把本地市场 zip 推到仓库的 marketplace 分支。

main 分支保持"只存引用、零正文"；正文压缩包是**构建产物**，住在专用分支上，
就像 Release 资产一样。在线市场源因此有两个都可达的地址（本机 github.com 直连
不通，但 raw 与 jsDelivr 都通，所以链接给这两个域名）：

    raw      https://raw.githubusercontent.com/openfcp/awesome-financial-skills/marketplace/awesome-financial-skills.zip
    jsDelivr https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@marketplace/awesome-financial-skills.zip

    python3 scripts/publish_market.py            # 需先跑过 pack_market.py --zip
    python3 scripts/publish_market.py --zip x.zip
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SLUG = "openfcp/awesome-financial-skills"
BRANCH = "marketplace"
ZIP_NAME = "awesome-financial-skills.zip"
DEFAULT_ZIP = REPO / "dist" / ZIP_NAME


def api(method: str, path: str, payload=None) -> dict:
    token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"https://api.github.com{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "afs-market-publisher")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {method} {path}\n{e.read().decode()[:400]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", default=str(DEFAULT_ZIP), help=f"市场 zip 路径（默认 {DEFAULT_ZIP}）")
    a = ap.parse_args()
    zpath = Path(a.zip).expanduser()
    if not zpath.is_file():
        raise SystemExit(f"[publish] 找不到 {zpath}，先跑 python3 scripts/pack_market.py --zip")
    blob_bytes = zpath.read_bytes()
    print(f"[publish] {zpath}（{len(blob_bytes)/1024/1024:.1f} MB）")

    # 分支现 HEAD：有就追加提交，没有就从零建
    try:
        head = api("GET", f"/repos/{SLUG}/git/ref/heads/{BRANCH}")["object"]["sha"]
        parent = [head]
    except SystemExit:
        parent = []
        print(f"[publish] 分支 {BRANCH} 不存在，将新建")

    blob = api("POST", f"/repos/{SLUG}/git/blobs",
               {"content": base64.b64encode(blob_bytes).decode(), "encoding": "base64"})
    tree = api("POST", f"/repos/{SLUG}/git/trees", {
        "tree": [{"path": ZIP_NAME, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
        **({"base_tree": api("GET", f"/repos/{SLUG}/git/commits/{head}")["tree"]["sha"]}
           if parent else {}),
    })
    import datetime
    commit = api("POST", f"/repos/{SLUG}/git/commits", {
        "message": f"chore: marketplace zip build {datetime.datetime.now():%Y-%m-%d %H:%M}",
        "tree": tree["sha"], "parents": parent,
    })
    if parent:
        api("PATCH", f"/repos/{SLUG}/git/refs/heads/{BRANCH}", {"sha": commit["sha"], "force": True})
    else:
        api("POST", f"/repos/{SLUG}/git/refs",
            {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
    print(f"[publish] {BRANCH} → {commit['sha'][:10]}")

    print("\n[publish] 在线市场源（添加市场 → 市场源，二选一）：")
    print(f"  raw      https://raw.githubusercontent.com/{SLUG}/{BRANCH}/{ZIP_NAME}")
    print(f"  jsDelivr https://fastly.jsdelivr.net/gh/{SLUG}@{BRANCH}/{ZIP_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
