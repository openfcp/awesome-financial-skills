#!/usr/bin/env python3
"""build.py — 校验清单，并把清单灌进静态站。

    python3 scripts/build.py            # 校验 + 生成 docs/catalog.js
    python3 scripts/build.py --check    # 只校验
    python3 scripts/build.py --urls     # 顺带打印每条引用的取回地址

本仓库只做一件事：维护一份**引用清单**。技能正文一律不进来 —— 16 条指向
SkillHub，1 条指向本仓 skills/ 目录（未上架 SkillHub 的唯一例外）。

所以构建产物只剩一个：`docs/catalog.js`（给 index.html 用的内嵌数据）。
以前那套 dsh 索引、WorkBuddy 整包 zip、每个技能一份 package.json/index.js/
cordis.patch.yml 全部删掉了，它们都要求正文在仓里存在。
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
SITE = ROOT / "docs"

SKILLHUB_ZIP = "https://api.skillhub.cn/api/v1/download?slug={slug}"
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}/SKILL.md"

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 校验


def validate(cat: dict) -> None:
    if cat.get("format") != 3:
        fail(f"format 必须是 3（引用式清单），当前 {cat.get('format')}")

    cat_ids = [c["id"] for c in cat["categories"]]
    if len(set(cat_ids)) != len(cat_ids):
        fail("categories 存在重复 id")

    seen: set[str] = set()
    vendored: set[str] = set()

    for s in cat["skills"]:
        sid = s["id"]
        if sid in seen:
            fail(f"{sid}: id 重复")
        seen.add(sid)

        if s["category"] not in cat_ids:
            fail(f"{sid}: category '{s['category']}' 不在 categories 中")

        for field in ("name", "summary"):
            for lang in ("zh", "en"):
                if not s.get(field, {}).get(lang):
                    fail(f"{sid}: {field}.{lang} 为空")

        if not s.get("version"):
            fail(f"{sid}: 缺少 version")

        src = s.get("source") or {}
        kind = src.get("type")
        if kind == "skillhub":
            for k in ("namespace", "slug"):
                if not src.get(k):
                    fail(f"{sid}: skillhub 源缺少 {k}")
            if not (s.get("install") or {}).get("skillhub"):
                fail(f"{sid}: 缺少 install.skillhub（站点要显示安装命令）")
        elif kind == "github":
            for k in ("repo", "path", "ref"):
                if not src.get(k):
                    fail(f"{sid}: github 源缺少 {k}")
            if src.get("vendored"):
                # 唯一允许自带正文的情形：显式声明，且目录真的在仓里
                p = (ROOT / src["path"]).resolve()
                if not p.is_dir():
                    fail(f"{sid}: vendored 目录不存在 {src['path']}")
                elif not (p / "SKILL.md").is_file():
                    fail(f"{sid}: vendored 目录缺少 SKILL.md（{src['path']}）")
                else:
                    vendored.add(src["path"].strip("/"))
                if not (s.get("install") or {}).get("plugin"):
                    fail(f"{sid}: vendored 技能缺少 install.plugin（站点要显示安装方式）")
            else:
                fail(f"{sid}: github 源必须是 vendored（本仓不自带正文，外部仓库另计）")
        else:
            fail(f"{sid}: 未知 source.type '{kind}'")

    # 核心守卫：仓库里不许再长出未声明的技能正文。
    # 以前 plugins/ 下堆了 17 份完整副本（10 MB），全是别处复制来的，会过期、
    # 也不归清单作者所有。这条检查让"再放一份副本"这件事直接构建失败。
    # 跳过 .gitignore 掉的产物目录（dist/ 等）——pack_market.py 的本地市场包
    # 就落在那里，正文运行时取回、永不进仓库，不该被当成"仓内副本"。
    ignore_dirs = gitignored_dirs()
    for md in ROOT.rglob("SKILL.md"):
        if any(part in ignore_dirs for part in md.parts):
            continue
        rel = md.parent.resolve().relative_to(ROOT).as_posix()
        if rel in vendored or rel.startswith(".git"):
            continue
        fail(f"仓库内出现未声明的技能正文：{rel}/SKILL.md（清单只存引用，正文请留在原作者仓库）")


def gitignored_dirs() -> set[str]:
    """解析 .gitignore 里的目录名（只认顶层 `name/` 写法，够用）。"""
    out = set()
    gi = ROOT / ".gitignore"
    if gi.is_file():
        for line in gi.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.endswith("/"):
                out.add(line.rstrip("/"))
    return out


def resolve_url(s: dict) -> str:
    src = s["source"]
    if src["type"] == "skillhub":
        return SKILLHUB_ZIP.format(slug=src["slug"])
    return RAW.format(repo=src["repo"], ref=src["ref"], path=src["path"].strip("/"))


# ------------------------------------------------------------------ 站点数据


def build_site_data(cat: dict) -> str:
    payload = json.dumps(cat, ensure_ascii=False, separators=(",", ":"))
    return (
        "// 自动生成，请勿手改。源：catalog.json（运行 python3 scripts/build.py 重新生成）\n"
        f"window.__CATALOG__ = {payload};\n"
    )


def stamp_catalog_ref(site_dir: Path, data_text: str) -> str | None:
    """给 index.html 里的 catalog.js 引用打内容指纹。

    GitHub Pages 对静态资源发 Cache-Control: max-age=600，浏览器自己还缓存一层，
    于是"改了清单 → 页面没变"几乎总是缓存，而不是构建没跑。URL 跟着内容变即可。

    负向断言 (?<!on) 是必要的：页脚里也有一个 catalog.json 链接，别一起改掉。
    """
    fingerprint = hashlib.sha256(data_text.encode("utf-8")).hexdigest()[:8]
    page = site_dir / "index.html"
    if not page.exists():
        return None
    html = page.read_text(encoding="utf-8")
    new = re.sub(r"catalog\.js(?!on)(?:\?v=[0-9a-f]+)?",
                 f"catalog.js?v={fingerprint}", html)
    if new != html:
        page.write_text(new, encoding="utf-8")
    return fingerprint


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    ap.add_argument("--urls", action="store_true", help="打印每条引用的取回地址")
    args = ap.parse_args()

    cat = load()
    validate(cat)

    if errors:
        print("[build] 校验失败：")
        for e in errors:
            print("  -", e)
        return 1

    n = len(cat["skills"])
    src_stat: dict[str, int] = {}
    for s in cat["skills"]:
        src_stat[s["source"]["type"]] = src_stat.get(s["source"]["type"], 0) + 1
    used = {s["category"] for s in cat["skills"]}
    empty = [c["id"] for c in cat["categories"] if c["id"] not in used]

    print(f"[build] 校验通过：{n} 条引用 / {len(cat['categories'])} 个分类 / 来源 {src_stat}")
    if empty:
        print(f"[build] 空分类：{', '.join(empty)}")

    if args.urls:
        for s in cat["skills"]:
            print(f"  {s['id']:<44}{resolve_url(s)}")

    if args.check:
        return 0

    SITE.mkdir(parents=True, exist_ok=True)
    data = build_site_data(cat)
    (SITE / "catalog.js").write_text(data, encoding="utf-8")
    print("[build] docs/catalog.js          已内嵌清单数据")
    fp = stamp_catalog_ref(SITE, data)
    if fp:
        print(f"[build] docs/index.html          catalog.js?v={fp}（内容指纹，绕开 600s 缓存）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
