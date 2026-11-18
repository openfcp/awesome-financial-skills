#!/usr/bin/env python3
"""check_schema.py — 按 schema.json 校验 catalog.json 的结构。

build.py --check 管的是业务规则（id 唯一、分类命中、零正文守卫等）；
这里只回答一件事：这份 JSON 是否符合对外声明的格式契约，别人照着写会不会写歪。

    python3 scripts/check_schema.py
    python3 scripts/check_schema.py --catalog other.json --schema schema.json

依赖 jsonschema（CI 里会装）：pip install "jsonschema>=4,<5"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AFS_REPO") or Path(__file__).resolve().parent.parent)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="catalog.json")
    ap.add_argument("--schema", default="schema.json")
    a = ap.parse_args()

    cat_p = Path(a.catalog) if Path(a.catalog).is_absolute() else ROOT / a.catalog
    sch_p = Path(a.schema) if Path(a.schema).is_absolute() else ROOT / a.schema

    try:
        import jsonschema
    except ImportError:
        print("[schema] 缺 jsonschema：pip install \"jsonschema>=4,<5\"", file=sys.stderr)
        return 2

    doc = json.loads(cat_p.read_text(encoding="utf-8"))
    schema = json.loads(sch_p.read_text(encoding="utf-8"))

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if not errors:
        print(f"[schema] ✓ {cat_p.name} 符合 {sch_p.name}（{len(doc.get('skills', []))} 条）")
        return 0

    print(f"[schema] ✗ {len(errors)} 处不符合：", file=sys.stderr)
    for e in errors[:40]:
        where = "/".join(str(x) for x in e.absolute_path) or "(根)"
        print(f"  - {where}: {e.message}", file=sys.stderr)
    if len(errors) > 40:
        print(f"  … 另有 {len(errors) - 40} 处", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
