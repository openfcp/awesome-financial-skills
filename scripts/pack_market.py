#!/usr/bin/env python3
"""生成「清单型市场」：市场只看清单，点哪个装哪个，仓里不存未授权正文。

两条硬约束：
  1. 添加市场只下载 marketplace.json（几 KB），不预下载任何技能；
  2. 不在本仓保存其他作者的技能正文。

据此把 16 条分成两类：

  镜像包（license 允许再分发，如 MIT）
      从 SkillHub 取回正文 + 补 .codebuddy-plugin/plugin.json + NOTICE，
      点装后即可离线使用。NOTICE 里写清作者、原页面、许可证。

  取件包（license 为 proprietary 或未声明）
      包里只有我们自己的 plugin.json / SKILL.md / fetch.py（几 KB），
      不含任何他人正文；首次使用时由 fetch.py 现从 SkillHub 取。

产物：
  dist/pkgs/<id>.zip      每个技能一个包
  marketplace.json        市场清单（16 条，全部 archive 源，指向 marketplace 分支）

用法：
    python3 scripts/pack_market.py              # 全部
    python3 scripts/pack_market.py --only law-skills,smart-charts
    python3 scripts/pack_market.py --force      # 忽略缓存重新取回
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PKGS = DIST / "pkgs"
INDEX = ROOT / "marketplace.json"
RAW_MAIN = "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main"
RAW_MKT = "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/marketplace"
SKILLHUB_ZIP = "https://api.skillhub.cn/api/v1/download?slug={slug}"
UA = {"User-Agent": "afs-market-pack"}
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

# 允许再分发的许可证（其余一律按「未授权」处理，只出取件包）
REDISTRIBUTABLE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "mpl-2.0", "cc0-1.0", "unlicense"}


def get(url: str, timeout: int = 90) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def write_zip(root: Path, out: Path) -> bytes:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_dir() or "__pycache__" in p.parts or p.name == ".DS_Store":
                continue
            info = zipfile.ZipInfo(p.relative_to(root).as_posix(), date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            z.writestr(info, p.read_bytes())
    return out.read_bytes()


def plugin_json(name: str, desc: str, version: str) -> str:
    return json.dumps({"name": name, "description": desc, "version": version},
                      ensure_ascii=False, indent=2) + "\n"


def notice_md(s: dict) -> str:
    src = s["source"]
    return f"""# 来源与许可

这个技能包由 **awesome-financial-skills** 清单整理，仅做分发搬运，不修改原作者内容。

| 项 | 值 |
|---|---|
| 技能 | {s['name']['zh']}（`{s['id']}`） |
| 作者 | {s.get('author', '未署名')} |
| 原页面 | https://skillhub.cn/skills/{src['slug']} |
| 原始来源 | SkillHub（namespace `{src.get('namespace', '-')}`） |
| 许可证 | {s.get('license', '未声明')} |
| 清单版本 | {s.get('version', '-')} |

正文版权归原作者所有。若你是作者并要求下架，请到
https://github.com/openfcp/awesome-financial-skills/issues 提一个 issue，
我们会在确认后 24 小时内移除对应包与清单条目。
"""


SHIM_SKILL = """---
name: {name}
description: {desc}（首次使用时自动从 {where} 取回正文）
---

# {name}

这是一张**取件卡**：本插件不包含技能正文，正文在原作者处（{where}）。

## 首次使用：先取件

```bash
python3 scripts/fetch.py
```

脚本位于本插件目录下的 `scripts/fetch.py`。它会去 {where} 取回「{id}」的当前版本，
安装到 `~/.workbuddy/skills`。取件成功后再继续。

## 取件之后

读取刚装好的技能目录里的 `SKILL.md`（`~/.workbuddy/skills/{dirname}/SKILL.md`），
按其中的说明执行用户的请求。若用户已经装过该技能，`fetch.py` 会提示已存在，直接读即可。

## 说明

- 这个包只有我们自己的取件代码（几 KB），没有任何他人正文
- 每次取的都是原作者当前发布的最新版
- 取件失败：`404 / Version not found` 多为作者新版本仍在扫描，稍后重试；网络不通时换用
  `https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json`
"""

FETCH_PY = '''#!/usr/bin/env python3
"""取件器：从 SkillHub 取回本插件对应的技能，装到 ~/.workbuddy/skills。

只有十几行 —— 真正的下载逻辑复用仓库里的 install.py（单一实现，避免两处漂移）。
"""
import subprocess
import sys
import tempfile
import urllib.request

ID = "{id}"
MIRRORS = (
    "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main",
    "https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main",
)


def fetch(path):
    last = None
    for base in MIRRORS:
        try:
            return urllib.request.urlopen(f"{{base}}{{path}}", timeout=40).read()
        except Exception as e:  # noqa: BLE001
            last = e
    raise SystemExit(f"取件失败，两个镜像都不可达：{{last}}")


tmp = tempfile.mkdtemp()
script = f"{{tmp}}/install.py"
open(script, "wb").write(fetch("/scripts/install.py"))
open(f"{{tmp}}/catalog.json", "wb").write(fetch("/catalog.json"))
sys.exit(subprocess.call([sys.executable, script,
                          "--catalog", f"{{tmp}}/catalog.json", "--only", ID]))
'''


def homepage(s: dict) -> str:
    """市场卡片上的「原页面」。两种源各自的落地页。"""
    src = s["source"]
    if src["type"] == "skillhub":
        return f"https://skillhub.cn/skills/{src['slug']}"
    return f"https://github.com/{src['repo']}"


def build_mirror(s: dict, force: bool) -> bytes:
    """镜像包：仅用于许可允许再分发、且来自 SkillHub 的条目。

    GitHub 源一律走取件器：一个仓库里可能混着多种许可，整体搬运等于替作者
    做再分发决定，不做。
    """
    if s["source"]["type"] != "skillhub":
        raise SystemExit(f"[pack] {s['id']}: 镜像包只支持 skillhub 源（GitHub 源请走取件器）")
    sid = s["id"]
    dst = PKGS / f"{sid}.zip"
    if dst.is_file() and not force:
        return dst.read_bytes()
    raw = get(SKILLHUB_ZIP.format(slug=s["source"]["slug"]), timeout=180)
    stage = DIST / "_stage" / sid
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for n in z.namelist():
            if n.startswith("__MACOSX/") or n.endswith("/"):
                continue
            z.extract(n, stage)
    # SkillHub 包若整体套了一层目录，摊平
    entries = [p for p in stage.iterdir() if p.name not in {".DS_Store"}]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for p in inner.iterdir():
            shutil.move(str(p), str(stage / p.name))
        inner.rmdir()
    meta_dir = stage / ".codebuddy-plugin"
    if not meta_dir.is_dir():
        meta_dir.mkdir(parents=True)
    (stage / ".codebuddy-plugin" / "plugin.json").write_text(
        plugin_json(sid, s["summary"]["zh"], s.get("version", "1.0.0")), encoding="utf-8")
    (stage / "NOTICE.md").write_text(notice_md(s), encoding="utf-8")
    data = write_zip(stage, dst)
    shutil.rmtree(stage)
    return data


def where_from(s: dict) -> str:
    """取件说明里的「去哪儿取」——按来源说人话。"""
    return "SkillHub" if s["source"]["type"] == "skillhub" else "作者的 GitHub 仓库"


def build_shim(s: dict, dirname: str) -> bytes:
    sid = s["id"]
    stage = DIST / "_stage" / sid
    if stage.exists():
        shutil.rmtree(stage)
    (stage / ".codebuddy-plugin").mkdir(parents=True)
    (stage / "scripts").mkdir()
    (stage / ".codebuddy-plugin" / "plugin.json").write_text(
        plugin_json(sid, s["summary"]["zh"], s.get("version", "1.0.0")), encoding="utf-8")
    (stage / "SKILL.md").write_text(
        SHIM_SKILL.format(name=s["name"]["zh"], desc=s["summary"]["zh"], id=sid,
                          dirname=dirname, where=where_from(s)), encoding="utf-8")
    (stage / "scripts" / "fetch.py").write_text(FETCH_PY.format(id=sid), encoding="utf-8")
    data = write_zip(stage, PKGS / f"{sid}.zip")
    shutil.rmtree(stage)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="只打这些 id，逗号分隔")
    ap.add_argument("--force", action="store_true", help="忽略已有包，重新取回")
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",")} if a.only else None

    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    cat["skills"] = [s for s in cat["skills"] if not only or s["id"] in only]

    PKGS.mkdir(parents=True, exist_ok=True)
    entries, mirrored, shimmed = [], [], []
    for s in cat["skills"]:
        sid = s["id"]
        lic = str(s.get("license", "")).lower()
        # 镜像只在「许可允许 + 来源是 SkillHub（单包、单一许可）」时才做。
        # GitHub 源一律取件：一个仓库可能混着多种许可，整体搬运等于替作者做决定。
        if lic in REDISTRIBUTABLE and s["source"]["type"] == "skillhub":
            data = build_mirror(s, a.force)
            mirrored.append(sid)
            kind = "镜像"
        else:
            # 目录名沿用 install.py 的规则：SKILL.md 的 name，取不到就用 id
            data = build_shim(s, sid)
            shimmed.append(sid)
            kind = "取件"
        entries.append({
            "name": sid,
            "description": s["summary"]["zh"],
            "version": s.get("version", "1.0.0"),
            "category": s.get("category", ""),
            "author": {"name": s.get("author", "未署名")},
            "homepage": homepage(s),
            "license": s.get("license", "未声明"),
            "source": {
                "source": "archive",
                "url": f"{RAW_MKT}/pkgs/{sid}.zip",
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        })
        print(f"[pack] {sid:<44} {kind}  {len(data)/1024:>7.1f} KB")

    index = {
        "name": "awesome-financial-skills",
        "description": "为金融从业者策展的技能清单：清单只存坐标，技能按需取回",
        "owner": {"name": "OpenFCP"},
        "plugins": entries,
    }
    if only:
        # --only 只重打选中的包，清单必须与既有内容合并。
        # 否则会把 16 条写成 1 条，已发布的市场里其余 15 张卡直接从用户眼前消失。
        prev = {}
        if INDEX.is_file():
            try:
                old = json.loads(INDEX.read_text(encoding="utf-8"))
                prev = {p.get("name"): p for p in old.get("plugins", []) if p.get("name")}
            except (json.JSONDecodeError, OSError):
                prev = {}
        order = [s["id"] for s in json.loads(
            (ROOT / "catalog.json").read_text(encoding="utf-8"))["skills"]]
        fresh = {p["name"]: p for p in entries}
        merged, missing = [], []
        for sid in order:                       # 只认 catalog 里的条目，顺序也照它
            if sid in fresh:
                merged.append(fresh.pop(sid))
            elif sid in prev:
                merged.append(prev[sid])
            else:
                # catalog 里有、但既没重打也没旧清单 —— 缺卡，必须报出来
                missing.append(sid)
        index["plugins"] = merged
        dropped = [n for n in prev if n not in set(order)]
        print(f"\n[pack] --only 模式：清单合并后 {len(merged)} 条"
              f"（本次重打 {len(entries)} 条，沿用 {len(merged) - len(entries)} 条）")
        if missing:
            print(f"[pack] ⚠ 这些条目在 catalog 里但没有包、也没有旧清单，市场里会缺卡："
                  f"{', '.join(missing)}")
        if dropped:
            print(f"[pack] 已从 catalog 移除、本次一并从清单删除：{', '.join(dropped)}")
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 清单是唯一真相：不在清单里的本地包一律清掉，避免已下架的正文被 publish 重新上传
    keep = {p["name"] for p in index["plugins"]}
    pruned = []
    for z in sorted(PKGS.glob("*.zip")):
        if z.stem not in keep:
            z.unlink()
            pruned.append(z.stem)
    if pruned:
        print(f"[pack] 清理孤儿包（不在清单里，已下架或改名）：{', '.join(pruned)}")

    total = sum(p.stat().st_size for p in PKGS.glob("*.zip")
                if p.stem in keep)
    print(f"\n[pack] 镜像 {len(mirrored)} 条（许可允许再分发）：{', '.join(mirrored) or '-'}")
    print(f"[pack] 取件 {len(shimmed)} 条（未授权，只放取件器）：{len(shimmed)} 个包")
    print(f"[pack] 分支总体积 {total/1024/1024:.2f} MB · 清单 {INDEX.name} {INDEX.stat().st_size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
