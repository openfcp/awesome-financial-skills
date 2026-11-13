#!/usr/bin/env python3
"""add_skill.py — 收录一条技能：先看清原件，再写进 catalog.json。

配套 skill 用（`awesome-skill-curator`），也可以手动跑：

    # 1. 先看原件长什么样（不写任何文件）
    python3 scripts/add_skill.py inspect --slug law-skills
    python3 scripts/add_skill.py inspect --repo owner/repo --path skills/xxx

    # 2. 写进清单
    python3 scripts/add_skill.py add --id xxx --category consumer-protection \
        --name-zh 消保审查 --name-en Consumer Protection Review \
        --summary-zh "…" --summary-en "…" \
        --slug xxx --namespace user_xxxx --license proprietary --author 八大权益

    # 3. 改已有条目（只改给出的字段）
    python3 scripts/add_skill.py update --id xxx --category data-tech

    python3 scripts/add_skill.py list            # 现有 id / 分类，方便查重

设计约束：
- **只写 catalog.json**，不碰 marketplace.json（那是构建产物，由 pack_market.py 生成）。
- **不猜许可**。`--license` 必须显式给；原件未声明就填 `proprietary`，这是安全默认值。
- **不做正文搬运**。inspect 只读 SKILL.md 的元信息用于填表，正文留在原处。
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__import__("os").environ.get("AFS_REPO") or
            Path(__file__).resolve().parent.parent)
CATALOG = ROOT / "catalog.json"
UA = {"User-Agent": "afs-add-skill"}
SKILLHUB_ZIP = "https://api.skillhub.cn/api/v1/download?slug={slug}"
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
GH_TREE = "https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def save(cat: dict) -> None:
    cat["updated"] = __import__("datetime").date.today().isoformat()
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get(url: str, timeout: int = 90) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


# ------------------------------------------------------------------ 读原件

def frontmatter(text: str) -> dict:
    """取 SKILL.md 的 frontmatter。只认简单 key: value 与 | / > 折行，够用。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        if re.match(r"^\s+\S", line) and key:          # 折行续写
            meta[key] = (meta[key] + " " + line.strip()).strip()
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip().strip("|>").strip()
        meta[key] = val.strip('"').strip("'")
    return meta


def inspect_skillhub(slug: str) -> dict:
    data = get(SKILLHUB_ZIP.format(slug=urllib.parse.quote(slug)), timeout=180)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SystemExit(f"[inspect] {slug}: 下载到的不是 zip（{len(data)} 字节）")
    names = [n for n in z.namelist() if not n.endswith("/")]
    prefix = ""
    if "SKILL.md" not in names:
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        if len(roots) == 1 and f"{next(iter(roots))}/SKILL.md" in names:
            prefix = f"{next(iter(roots))}/"
    md = z.read(f"{prefix}SKILL.md").decode("utf-8", "replace") if f"{prefix}SKILL.md" in names else ""
    return {"kind": "skillhub", "slug": slug, "files": len(names),
            "size_kb": round(len(data) / 1024, 1), "meta": frontmatter(md), "md": md}


def inspect_github(repo: str, path: str, ref: str) -> dict:
    path = path.strip("/")
    tree = json.loads(get(GH_TREE.format(repo=repo, ref=urllib.parse.quote(ref))))
    files = [n["path"] for n in tree.get("tree", [])
             if n.get("type") == "blob" and (not path or n["path"].startswith(path + "/"))]
    md_path = f"{path}/SKILL.md" if path else "SKILL.md"
    if md_path not in files:
        raise SystemExit(f"[inspect] {repo}@{ref}/{path} 下没有 SKILL.md")
    md = get(RAW.format(repo=repo, ref=ref, path=urllib.parse.quote(md_path))).decode("utf-8", "replace")
    return {"kind": "github", "repo": repo, "path": path, "ref": ref,
            "files": len(files), "size_kb": None, "meta": frontmatter(md), "md": md}


def cmd_inspect(a) -> int:
    if a.slug:
        info = inspect_skillhub(a.slug)
    elif a.repo:
        if not a.path:
            raise SystemExit("[inspect] GitHub 源必须给 --path（技能目录）")
        info = inspect_github(a.repo, a.path, a.ref)
    else:
        raise SystemExit("[inspect] 给 --slug（SkillHub）或 --repo + --path（GitHub）")

    m = info["meta"]
    print(json.dumps({
        "来源": "SkillHub" if info["kind"] == "skillhub" else f"GitHub {info['repo']}@{info['ref']}",
        "文件数": info["files"],
        "体积KB": info["size_kb"],
        "SKILL.md name": m.get("name", ""),
        "SKILL.md description": m.get("description", "")[:400],
        "SKILL.md version": m.get("version", ""),
        "SKILL.md author": m.get("author", ""),
        "SKILL.md license": m.get("license", "（原件未声明，按 proprietary 处理）"),
    }, ensure_ascii=False, indent=2))
    if a.show_body:
        print("\n--- SKILL.md 正文（前 3000 字，用于写 summary）---")
        print(info["md"][:3000])
    return 0


# ------------------------------------------------------------------ 写清单

CANON_ORDER = ["id", "name", "summary", "category", "tags", "version",
               "author", "license", "source", "install"]


def build_entry(a, cat: dict) -> dict:
    src = ({"type": "skillhub", "namespace": a.namespace, "slug": a.slug}
           if a.slug else
           {"type": "github", "repo": a.repo, "path": a.path.strip("/"),
            "ref": a.ref, "vendored": False})
    install = ({"skillhub": f"skillhub install {a.slug} --namespace {a.namespace}"}
               if a.slug else {"plugin": f"./{a.path.strip('/')}"})
    entry = {
        "id": a.id,
        "name": {"zh": a.name_zh, "en": a.name_en},
        "summary": {"zh": a.summary_zh, "en": a.summary_en},
        "category": a.category,
        "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
        "version": a.version,
        "author": a.author,
        "license": a.license,
        "source": src,
        "install": install,
    }
    return {k: entry[k] for k in CANON_ORDER if k in entry}


def check_entry(e: dict, cat: dict) -> list[str]:
    errs = []
    if not ID_RE.match(e["id"]):
        errs.append(f"id '{e['id']}' 不合法：小写字母/数字开头，只含小写字母、数字、连字符")
    cats = [c["id"] for c in cat["categories"]]
    if e["category"] not in cats:
        errs.append(f"category '{e['category']}' 不存在；可用：{', '.join(cats)}")
    for f in ("name", "summary"):
        for lang in ("zh", "en"):
            if not (e[f].get(lang) or "").strip():
                errs.append(f"{f}.{lang} 为空")
    if not (e.get("license") or "").strip():
        errs.append("license 必须显式给（原件未声明就填 proprietary）")
    src = e["source"]
    if src["type"] == "skillhub":
        for k in ("namespace", "slug"):
            if not src.get(k):
                errs.append(f"skillhub 源缺 {k}")
    else:
        for k in ("repo", "path", "ref"):
            if not src.get(k):
                errs.append(f"github 源缺 {k}")
    return errs


def cmd_add(a) -> int:
    cat = load()
    if any(s["id"] == a.id for s in cat["skills"]):
        raise SystemExit(f"[add] id '{a.id}' 已存在。改已有条目用 update，别重复加。")
    entry = build_entry(a, cat)
    errs = check_entry(entry, cat)
    if errs:
        print("[add] ✗ 有以下问题：", file=sys.stderr)
        for e in errs:
            print("  -", e, file=sys.stderr)
        return 2
    if a.dry_run:
        print("[add] dry-run，未写入。将要追加：")
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0
    cat["skills"].append(entry)
    save(cat)
    n = len(cat["skills"])
    print(f"[add] ✓ {a.id} 已写入 catalog.json（现 {n} 条）")
    print("\n接着跑：")
    print("  python3 scripts/build.py --check")
    print(f'  WITH_MARKET=1 MARKET_ONLY={a.id} ./scripts/release.sh "feat: 新增 {a.name_zh}"')
    print("  python3 scripts/check_market.py")
    return 0


def cmd_update(a) -> int:
    cat = load()
    hit = next((s for s in cat["skills"] if s["id"] == a.id), None)
    if not hit:
        raise SystemExit(f"[update] 没有 id '{a.id}'")
    changed = []
    for attr, path in (("category", ("category",)), ("version", ("version",)),
                       ("author", ("author",)), ("license", ("license",)),
                       ("name_zh", ("name", "zh")), ("name_en", ("name", "en")),
                       ("summary_zh", ("summary", "zh")), ("summary_en", ("summary", "en"))):
        val = getattr(a, attr, None)
        if val:
            node = hit
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = val
            changed.append(path[-1] if len(path) == 1 else ".".join(path))
    if a.tags is not None:
        hit["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
        changed.append("tags")
    if not changed:
        raise SystemExit("[update] 没给任何要改的字段")
    if a.dry_run:
        print(f"[update] dry-run，将改 {', '.join(changed)}：")
        print(json.dumps(hit, ensure_ascii=False, indent=2))
        return 0
    save(cat)
    print(f"[update] ✓ {a.id} 已更新：{', '.join(changed)}")
    print(f'重发：WITH_MARKET=1 MARKET_ONLY={a.id} ./scripts/release.sh "chore: 更新 {a.id}"')
    return 0


def cmd_list(a) -> int:
    cat = load()
    print(f"{len(cat['skills'])} 条 · {len(cat['categories'])} 个分类\n")
    print(f"{'id':<44}{'分类':<24}{'许可':<14}来源")
    for s in cat["skills"]:
        print(f"{s['id']:<44}{s['category']:<24}{s.get('license', '-'):<14}{s['source']['type']}")
    print("\n分类：" + ", ".join(c["id"] for c in cat["categories"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="看原件的元信息，不写文件")
    p.add_argument("--slug", help="SkillHub 的 slug")
    p.add_argument("--repo", help="GitHub owner/repo")
    p.add_argument("--path", help="GitHub 技能目录")
    p.add_argument("--ref", default="main")
    p.add_argument("--show-body", action="store_true", help="附带打印 SKILL.md 正文前 3000 字")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("add", help="追加一条到 catalog.json")
    p.add_argument("--id", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--name-zh", required=True)
    p.add_argument("--name-en", required=True)
    p.add_argument("--summary-zh", required=True)
    p.add_argument("--summary-en", required=True)
    p.add_argument("--slug", help="SkillHub slug（与 --repo 二选一）")
    p.add_argument("--namespace", help="SkillHub namespace")
    p.add_argument("--repo", help="GitHub owner/repo")
    p.add_argument("--path", default="", help="GitHub 技能目录")
    p.add_argument("--ref", default="main")
    p.add_argument("--license", required=True, help="proprietary / MIT / …（不猜）")
    p.add_argument("--author", default="未署名")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--tags", default="")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("update", help="改已有条目（只改给出的字段）")
    p.add_argument("--id", required=True)
    for opt in ("--category", "--name-zh", "--name-en", "--summary-zh", "--summary-en",
                "--license", "--author", "--version", "--tags"):
        p.add_argument(opt, dest=opt.lstrip("-").replace("-", "_"))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("list", help="看现有条目与分类")
    p.set_defaults(fn=cmd_list)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
