#!/usr/bin/env python3
"""pack_market.py — 把清单打包成本地市场目录，供 WorkBuddy「添加市场」用。

仓库本身只存引用（这是 refactor 后的底线），但 WorkBuddy 的市场机制只认
「装着完整技能的市场包」。折中：正文在**运行时**取回原件，落到本地产物目录
`dist/marketplace/`（.gitignore 掉，永不进仓库），市场源填这个目录的本地路径。

    python3 scripts/pack_market.py                 # 全量打包
    python3 scripts/pack_market.py --only law-skills
    python3 scripts/pack_market.py --fresh         # 忽略已有目录，全部重取
    python3 scripts/pack_market.py --zip           # 额外产出 dist/awesome-financial-skills.zip

打完它会打印一行「市场源」——把那行绝对路径粘进 技能 → 套件 → 添加市场。
--zip 的产物用 scripts/publish_market.py 推到仓库 marketplace 分支，供在线链接。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install as inst  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "dist" / "marketplace"


def build(out: Path, only: set[str] | None, fresh: bool) -> int:
    cat = inst.load_catalog(None)
    if cat.get("format") != 3:
        raise SystemExit(f"[pack] 清单 format={cat.get('format')}，只认 3")

    cat_titles = {c["id"]: c["title"] for c in cat["categories"]}
    plugins_dir = out / "plugins"
    if fresh and out.is_dir():
        shutil.rmtree(out)

    entries, ok, fail = [], 0, []
    for s in cat["skills"]:
        if only and s["id"] not in only:
            continue
        target = None
        try:
            files = inst.fetch(s)
            name = (inst.frontmatter_name(files.get("SKILL.md", b"").decode("utf-8", "replace"))
                    or inst.safe_dirname(s["id"]))
            target = plugins_dir / name
            (target / ".codebuddy-plugin").mkdir(parents=True, exist_ok=True)
            for rel, data in files.items():
                p = target / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            (target / ".codebuddy-plugin" / "plugin.json").write_text(
                json.dumps({
                    "name": name,
                    "description": s.get("summary", {}).get("zh", s["name"]["zh"]),
                    "version": str(s.get("version", "1.0.0")),
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            entries.append({
                "name": name,
                "description": s.get("summary", {}).get("zh", s["name"]["zh"]),
                "version": str(s.get("version", "1.0.0")),
                "source": f"./plugins/{name}",
                "category": cat_titles.get(s["category"], {}).get("zh", s["category"]),
                **({"author": {"name": s["author"]}} if s.get("author") else {}),
            })
            ok += 1
            print(f"  ✓ {s['id']:<40} → plugins/{name}（{len(files)} 文件）")
        except Exception as e:                                   # noqa: BLE001
            fail.append(s["id"])
            print(f"  ✗ {s['id']:<40} {e}")
            if target and target.is_dir():
                shutil.rmtree(target, ignore_errors=True)  # 失败不留半成品

    if not entries:
        print("[pack] 一条都没打上，不写清单", file=sys.stderr)
        return 1

    market = {
        "name": cat["id"],
        "description": cat["description"]["zh"],
        "owner": {"name": "OpenFCP"},
        "plugins": entries,
    }
    (out / ".codebuddy-plugin").mkdir(parents=True, exist_ok=True)
    (out / ".codebuddy-plugin" / "marketplace.json").write_text(
        json.dumps(market, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n[pack] 成功 {ok} · 失败 {len(fail)}"
          + (f"（{', '.join(fail)}）" if fail else ""))
    print(f"[pack] 市场目录 {out}")
    print(f"[pack] 添加市场 → 市场源填：{out}")
    return 0 if not fail else 2


def make_zip(out: Path, zip_path: Path) -> None:
    """把市场目录压成 zip，zip 根即市场根（.codebuddy-plugin/ 在顶层）。"""
    import zipfile
    entries = sorted(p for p in out.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in entries:
            z.write(p, p.relative_to(out).as_posix())
    print(f"[pack] zip {zip_path}（{zip_path.stat().st_size/1024/1024:.1f} MB，{len(entries)} 文件）")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出目录（默认 {DEFAULT_OUT}）")
    ap.add_argument("--only", help="只打这些 id，逗号分隔")
    ap.add_argument("--fresh", action="store_true", help="清掉输出目录全部重取")
    ap.add_argument("--zip", action="store_true",
                    help="额外产出 dist/awesome-financial-skills.zip（在线市场源用）")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    rc = build(out, {x.strip() for x in a.only.split(",")} if a.only else None, a.fresh)
    if a.zip and (rc == 0 or out.is_dir()):
        make_zip(out, out.parent / "awesome-financial-skills.zip")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
