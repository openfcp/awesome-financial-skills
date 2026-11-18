#!/usr/bin/env python3
"""changed_ids.py — 比对某个 git 版本与当前工作区的 catalog.json，列出被改动过的条目。

用途：PR 校验只想验证「这次动过的引用」，不必把 171 条全跑一遍网络请求。

    python3 scripts/changed_ids.py --base origin/main            # 人看：分组打印
    python3 scripts/changed_ids.py --base HEAD~1 --list          # 只输出逗号分隔的 id
    python3 scripts/changed_ids.py --base "$SHA" --github-output  # 写 GITHUB_OUTPUT，供 Actions 使用

判定口径：
- 新增：当前有、base 没有；
- 修改：两侧都有但整条记录不完全相同（含坐标、文案、许可、分类任一处变化）；
- 删除：base 有、当前没有。
`--list` / GITHUB_OUTPUT 的 ids 是「新增 + 修改」，正好是需要重新取回正文验证的集合。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AFS_REPO") or Path(__file__).resolve().parent.parent)
CATALOG = ROOT / "catalog.json"


def git_show(ref: str, path: str) -> str | None:
    """取某个版本里的文件内容；不在该版本里就返回 None。"""
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{ref}^{{commit}}"],
                      capture_output=True).returncode != 0:
        raise SystemExit(f"[changed] 找不到 commit：{ref}（CI 里可能是浅克隆，先 fetch 该提交）")
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def by_id(doc: dict) -> dict[str, dict]:
    return {s.get("id"): s for s in doc.get("skills", []) if s.get("id")}


def diff(base: dict, head: dict) -> dict[str, list[str]]:
    b, h = by_id(base), by_id(head)
    return {
        "added": sorted(set(h) - set(b)),
        "modified": sorted(i for i in set(h) & set(b) if h[i] != b[i]),
        "removed": sorted(set(b) - set(h)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="对比基准的 git ref / commit sha")
    ap.add_argument("--path", default="catalog.json", help="仓库内的清单路径")
    ap.add_argument("--list", action="store_true", help="只打印逗号分隔的 id（新增+修改）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--github-output", action="store_true",
                    help="把 ids/count 写到 $GITHUB_OUTPUT")
    ap.add_argument("--strict", action="store_true",
                    help="有删除条目时返回非 0（发布前自查用）")
    a = ap.parse_args()

    head_doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw = git_show(a.base, a.path)
    if raw is None:
        print(f"[changed] {a.base}:{a.path} 不存在，按「全部都是新增」处理", file=sys.stderr)
        base_doc = {"skills": []}
    else:
        base_doc = json.loads(raw)

    d = diff(base_doc, head_doc)
    touched = d["added"] + d["modified"]

    if a.github_output:
        out = os.environ.get("GITHUB_OUTPUT")
        if not out:
            print("[changed] 没有 GITHUB_OUTPUT，退化为打印", file=sys.stderr)
        else:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"ids={','.join(touched)}\n")
                f.write(f"count={len(touched)}\n")
                f.write(f"added={','.join(d['added'])}\n")
                f.write(f"removed={','.join(d['removed'])}\n")
    if a.json:
        print(json.dumps({**d, "touched": touched}, ensure_ascii=False, indent=2))
    elif a.list:
        print(",".join(touched))
    else:
        print(f"[changed] 基准 {a.base} → 工作区："
              f"新增 {len(d['added'])} · 修改 {len(d['modified'])} · 删除 {len(d['removed'])}")
        for key, label in (("added", "新增"), ("modified", "修改"), ("removed", "删除")):
            if d[key]:
                print(f"  {label}：" + ", ".join(d[key]))

    if a.strict and d["removed"]:
        print("[changed] ✗ 有删除条目；确认是有意下架再发", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
