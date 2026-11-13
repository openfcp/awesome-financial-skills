#!/usr/bin/env python3
"""install.py — 读清单，按引用把技能装进本地目录。给 WorkBuddy 用。

这个仓库**不存技能正文**，只存一份引用清单 `catalog.json`。本脚本负责把清单
里的每一条解析回它的原件（SkillHub 的 zip，或 GitHub 仓库里的一个目录），再落到
本机技能目录：

    python3 scripts/install.py --list                 # 看清单里有什么、装没装
    python3 scripts/install.py --all                  # 全装到 ~/.workbuddy/skills
    python3 scripts/install.py --only law-skills      # 只装一个
    python3 scripts/install.py --only a,b --dir /tmp/skills
    python3 scripts/install.py --verify               # 只验证引用还通不通，不落盘
    python3 scripts/install.py --all --dry-run        # 只说到做到哪一步

设计约束（踩过的坑，别改回去）：

1. **不复制正文进仓库**。原作者更新后，本脚本每次装的都是最新原件；仓库里那份
   副本一旦存在就必然过期，而且版权不属于清单作者。想要 WorkBuddy「添加市场」
   界面的，用 scripts/pack_market.py 在本地打市场目录（gitignore 掉，不进仓库）。
2. **token 只发给 api.github.com**。以前把 GitHub token 加到所有请求头上，连
   jsDelivr 这类第三方 CDN 也带上，被平台判成凭证泄漏而拒收。见 auth_headers()。
3. **下载失败就是失败，不做"装个空壳"的降级**。空壳技能在 WorkBuddy 里能列出
   来但一调用就错，比装不上更难排查。
4. **目录名取 SKILL.md 的 `name`**。WorkBuddy 按 `name` 触发技能（`Skill(skill=
   "…")`），目录名与它不一致时，列表里能看到但调用不到。清单的 `id` 只是本仓库
   的索引键，两者不一定相等（例如 id `ai-ppt-skill` → name `ppt-master`）。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO_SLUG = "openfcp/awesome-financial-skills"
# 按顺序试。raw 优先：jsDelivr 会把 @main 解析结果缓存十几小时，仓库改完它还在发
# 旧清单（曾用一份 format 2 的旧清单去装已经不存在的 ./plugins/*，全部失败）。
CATALOG_MIRRORS = (
    f"https://raw.githubusercontent.com/{REPO_SLUG}/main/catalog.json",
    f"https://fastly.jsdelivr.net/gh/{REPO_SLUG}@main/catalog.json",
)
LOCAL_CATALOG = Path(__file__).resolve().parent.parent / "catalog.json"

SKILLHUB_ZIP = "https://api.skillhub.cn/api/v1/download?slug={slug}"
# 注意 {path} 是"目录 + 文件名"的完整路径，模板里不要再拼 {file}
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
GH_API = "https://api.github.com/repos/{repo}/contents/{path}"
JSDELIVR = "https://fastly.jsdelivr.net/gh/{repo}@{ref}/{path}"

# 只有这些主机才允许带 token
AUTH_HOSTS = {"api.github.com"}
UA = "awesome-financial-skills/install"
IGNORE = {"_meta.json", ".DS_Store"}


def default_dir() -> Path:
    return Path(os.environ.get("WB_SKILLS_DIR") or (Path.home() / ".workbuddy" / "skills"))


# ------------------------------------------------------------------ HTTP


def gh_token() -> str | None:
    """优先环境变量，其次 `gh auth token`；都没有就匿名跑。"""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    try:
        return subprocess.check_output(
            ["gh", "auth", "token"], stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def auth_headers(url: str) -> dict:
    """按主机决定是否带 token —— 白名单外的地址一律匿名。

    这是上一轮的教训：token 被发到了 jsDelivr，扫描直接判凭证泄漏。
    """
    h = {"User-Agent": UA}
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in AUTH_HOSTS:
        tok = gh_token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
            h["Accept"] = "application/vnd.github+json"
    return h


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=auth_headers(url))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_first(urls: list[str], timeout: int = 60) -> tuple[bytes, str]:
    """按顺序试多个地址，返回第一个成功的（内容, 实际地址）。"""
    errs = []
    for u in urls:
        try:
            return get(u, timeout=timeout), u
        except urllib.error.HTTPError as e:
            errs.append(f"{u} -> HTTP {e.code}")
        except Exception as e:  # 网络层：超时、DNS、代理 502…
            errs.append(f"{u} -> {type(e).__name__}: {e}")
    raise RuntimeError("全部通道都失败：\n    " + "\n    ".join(errs))


# ------------------------------------------------------------------ 清单


def load_catalog(spec: str | None) -> dict:
    """spec 可以是 http(s) 地址、本地路径，或 None（有本地清单就用本地）。

    None 且没有本地清单时，按 CATALOG_MIRRORS 逐个试，只接受 format 3 的那份：
    镜像发旧副本时宁可报错，也不要拿旧清单去解析已经删掉的路径。
    """
    if spec:
        if re.match(r"^https?://", spec):
            return json.loads(get(spec).decode("utf-8"))
        return json.loads(Path(spec).expanduser().read_text(encoding="utf-8"))
    if LOCAL_CATALOG.is_file():
        return json.loads(LOCAL_CATALOG.read_text(encoding="utf-8"))
    errs = []
    for url in CATALOG_MIRRORS:
        try:
            # 加时间戳，绕开 CDN 上那份旧副本
            data = json.loads(get(f"{url}?t={int(time.time())}").decode("utf-8"))
        except Exception as e:                                   # noqa: BLE001
            errs.append(f"{url} → {e}")
            continue
        if data.get("format") == 3:
            return data
        errs.append(f"{url} → 还在发旧清单 format={data.get('format')}")
    raise SystemExit("[install] 取不到 format 3 的清单：\n  " + "\n  ".join(errs) +
                     "\n  用 --catalog 直接指向仓库里的 catalog.json 再试。")


def frontmatter_name(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        m = re.match(r"^name:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'") or None
    return None


def safe_dirname(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip(". ") or "skill"


# ------------------------------------------------------------------ 解析


def resolve_skillhub(spec: dict) -> dict[str, bytes]:
    """SkillHub：一个 zip，SKILL.md 在根上；剥掉可能多出的一层同名目录。"""
    slug = spec["source"]["slug"]
    data, used = get_first([SKILLHUB_ZIP.format(slug=urllib.parse.quote(slug))], timeout=90)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError(f"{slug}: 下载到的不是 zip（{len(data)} 字节，来自 {used}）")

    names = [n for n in z.namelist() if not n.endswith("/")]
    names = [n for n in names if n.split("/")[-1] not in IGNORE]
    prefix = ""
    if "SKILL.md" not in names:
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        if len(roots) == 1 and f"{next(iter(roots))}/SKILL.md" in names:
            prefix = f"{next(iter(roots))}/"

    out = {}
    for n in names:
        if not n.startswith(prefix):
            continue
        rel = n[len(prefix):]
        parts = Path(rel).parts
        if rel.startswith("/") or ".." in parts or not rel:
            continue
        out[rel] = z.read(n)
    return out


def resolve_github(spec: dict) -> dict[str, bytes]:
    """GitHub：取 path 目录下的全部文件。

    三通道：raw → api（可带 token）→ jsDelivr。国内网络里 raw 常常不通，api 通；
    反过来在别的环境 raw 更省额度，所以两个都试。
    """
    src = spec["source"]
    repo, path, ref = src["repo"], src.get("path", "").strip("/"), src.get("ref", "main")

    # 先列文件。api 的 tree 接口一次拿到整棵树，比逐个 contents 省得多。
    files: list[str] = []
    try:
        tree_url = f"https://api.github.com/repos/{repo}/git/trees/{urllib.parse.quote(ref)}?recursive=1"
        tree = json.loads(get(tree_url).decode("utf-8"))
        for node in tree.get("tree", []):
            if node.get("type") != "blob":
                continue
            p = node["path"]
            if path and not p.startswith(path + "/"):
                continue
            if p.split("/")[-1] in IGNORE:
                continue
            files.append(p[len(path) + 1:] if path else p)
    except Exception as e:
        raise RuntimeError(f"列目录失败（{repo}@{ref}/{path}）：{e}")

    if not files:
        raise RuntimeError(f"{repo}@{ref}/{path} 下没有文件")
    if "SKILL.md" not in files:
        raise RuntimeError(f"{repo}@{ref}/{path} 下没有 SKILL.md")

    out = {}
    for rel in sorted(files):
        full = f"{path}/{rel}" if path else rel
        urls = [
            RAW.format(repo=repo, ref=ref, path=urllib.parse.quote(full)),
            GH_API.format(repo=repo, path=urllib.parse.quote(full)) + f"?ref={ref}",
            JSDELIVR.format(repo=repo, ref=ref, path=urllib.parse.quote(full)),
        ]
        try:
            data, used = get_first(urls)
            if "/contents/" in used:  # contents API 返回 JSON+base64
                import base64

                obj = json.loads(data.decode("utf-8"))
                data = base64.b64decode(obj["content"])
        except RuntimeError as e:
            raise RuntimeError(f"{rel}: {e}")
        out[rel] = data
    return out


RESOLVERS = {"skillhub": resolve_skillhub, "github": resolve_github}


def fetch(spec: dict) -> dict[str, bytes]:
    kind = spec["source"]["type"]
    fn = RESOLVERS.get(kind)
    if not fn:
        raise RuntimeError(f"未知 source.type: {kind}")
    return fn(spec)


# ------------------------------------------------------------------ 落盘


def skill_name(spec: dict, files: dict[str, bytes]) -> str:
    """目录名取 SKILL.md 的 name（WorkBuddy 按它触发），退化到清单 id。"""
    md = files.get("SKILL.md")
    if md:
        n = frontmatter_name(md.decode("utf-8", "replace"))
        if n:
            return safe_dirname(n)
    return safe_dirname(spec["id"])


def digest(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8") + b"\0" + files[rel] + b"\0")
    return h.hexdigest()[:12]


def write_skill(files: dict[str, bytes], target: Path, force: bool) -> str:
    """写入 target 目录。已存在同名技能时：内容一致跳过，否则需要 --force。"""
    disk = {}
    if target.is_dir():
        for p in sorted(target.rglob("*")):
            if p.is_file():
                disk[p.relative_to(target).as_posix()] = p.read_bytes()

    if disk:
        if digest(disk) == digest(files):
            return "same"
        if not force:
            return "conflict"
        shutil.move(str(target), str(target.with_name(target.name + ".bak-" + digest(disk))))

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".installing-", dir=str(target.parent)))
    try:
        for rel, data in files.items():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(tmp), str(target))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return "installed"


def installed_version(target: Path) -> str:
    for cand in (target / "SKILL.md",):
        if cand.is_file():
            txt = cand.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^version:\s*(.+?)\s*$", txt[:2000], re.M)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return ""


# ------------------------------------------------------------------ 命令


def scan_installed(dest: Path) -> dict[str, Path]:
    """本地已装技能：{SKILL.md 里的 name 或目录名: 目录}。

    必须读 frontmatter：目录名不一定等于 name（id `ai-ppt-skill` 装出来是
    `ppt-master`），只按 id 猜目录会漏判成「没装」。
    """
    found: dict[str, Path] = {}
    if not dest.is_dir():
        return found
    for d in sorted(dest.iterdir()):
        if not d.is_dir():
            continue
        md = d / "SKILL.md"
        key = None
        if md.is_file():
            key = frontmatter_name(md.read_text(encoding="utf-8", errors="replace"))
        found[d.name] = d
        if key and key != d.name:
            found.setdefault(key, d)
    return found


def cmd_list(cat: dict, dest: Path, as_json: bool) -> int:
    have = scan_installed(dest)
    rows = []
    for s in cat["skills"]:
        hit = have.get(s["id"]) or have.get(safe_dirname(s["name"]["zh"]))
        rows.append({
            "id": s["id"],
            "name": s["name"]["zh"],
            "source": s["source"]["type"],
            "version": s["version"],
            "installed": bool(hit),
            "dir": str(hit or dest / s["id"]),
        })
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    n_ok = sum(1 for r in rows if r["installed"])
    print(f"清单 {len(rows)} 条 · 已装 {n_ok} · 目标目录 {dest}\n")
    print(f"{'id':<44}{'来源':<10}{'版本':<9}状态")
    for r in rows:
        mark = "已装" if r["installed"] else "—"
        print(f"{r['id']:<44}{r['source']:<10}{r['version']:<9}{mark}")
    return 0


def cmd_verify(cat: dict) -> int:
    """只验证每条引用还能取到 SKILL.md，不写本地。"""
    bad = 0
    for s in cat["skills"]:
        label = f"{s['id']:<44}"
        try:
            files = fetch(s)
            md = files.get("SKILL.md")
            if not md:
                print(f"{label}✗ 没有 SKILL.md")
                bad += 1
                continue
            nm = frontmatter_name(md.decode("utf-8", "replace")) or "?"
            print(f"{label}✓ {len(files)} 文件 · name={nm}")
        except Exception as e:
            print(f"{label}✗ {e}")
            bad += 1
    print(f"\n{len(cat['skills']) - bad}/{len(cat['skills'])} 条引用可用")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="按 catalog.json 的引用把技能装到本地（默认 ~/.workbuddy/skills）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("targets", nargs="*", help="要装的 id（等价于 --only）")
    ap.add_argument("--all", action="store_true", help="清单里的全部安装")
    ap.add_argument("--only", help="只装这些 id，逗号分隔")
    ap.add_argument("--dir", help=f"安装目录（默认 {default_dir()}）")
    ap.add_argument("--catalog", help="清单地址或路径（默认仓库内 catalog.json，其次远程）")
    ap.add_argument("--list", action="store_true", help="列出清单与安装状态，不下载")
    ap.add_argument("--verify", action="store_true", help="只验证引用是否可达")
    ap.add_argument("--dry-run", action="store_true", help="不落盘，只打印将要做什么")
    ap.add_argument("--force", action="store_true", help="已存在且内容不同时覆盖（旧的留 .bak）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    cat = load_catalog(args.catalog)
    if cat.get("format") != 3:
        raise SystemExit(
            f"[install] 清单 format={cat.get('format')}，本脚本只认 3。\n"
            "         多半是某处还留着旧副本：用 --catalog 指向仓库里的 catalog.json 再试。")

    dest = Path(args.dir).expanduser() if args.dir else default_dir()

    if args.list:
        return cmd_list(cat, dest, args.json)
    if args.verify:
        return cmd_verify(cat)

    wanted = [t.strip() for t in (args.only.split(",") if args.only else args.targets) if t.strip()]
    by_id = {s["id"]: s for s in cat["skills"]}
    unknown = [w for w in wanted if w not in by_id]
    if unknown:
        print(f"[install] 清单里没有：{', '.join(unknown)}", file=sys.stderr)
        print(f"[install] 可用：{', '.join(sorted(by_id))}", file=sys.stderr)
        return 2

    todo = [by_id[w] for w in wanted] if wanted else list(cat["skills"])
    if not (wanted or args.all) and not sys.stdin.isatty():
        print("[install] 没指定要装哪个，也没 --all；用 --list 看看再说。", file=sys.stderr)
        return 2

    print(f"[install] 清单 {len(cat['skills'])} 条 · 本次处理 {len(todo)} 条 · 目标 {dest}\n")
    results, failed = [], 0
    for s in todo:
        sid = s["id"]
        try:
            files = fetch(s)
            name = skill_name(s, files)
            target = dest / name
            if args.dry_run:
                print(f"  · {sid:<44}→ {target}  ({len(files)} 文件，dry-run 未写)")
                results.append({"id": sid, "dir": name, "status": "planned"})
                continue
            state = write_skill(files, target, args.force)
            if state == "conflict":
                failed += 1
                print(f"  ✗ {sid:<44}已存在且内容不同：{target}（加 --force 覆盖）")
            elif state == "same":
                print(f"  = {sid:<44}已是最新：{target}")
            else:
                ver = s["version"]
                print(f"  ✓ {sid:<44}{ver:>8} → {target}（{len(files)} 文件）")
            results.append({"id": sid, "dir": name, "status": state})
        except Exception as e:
            failed += 1
            print(f"  ✗ {sid:<44}{e}")
            results.append({"id": sid, "dir": "", "status": "error", "error": str(e)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    n_ok = sum(1 for r in results if r["status"] in ("installed", "same", "planned"))
    print(f"\n[install] 成功 {n_ok} · 失败 {failed}")
    if failed:
        print("[install] 失败的条目没装：宁可缺一个，也不要在技能目录里放空壳。")
        return 1
    if not args.dry_run:
        print("[install] 重启或刷新 WorkBuddy 的技能列表即可看到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
