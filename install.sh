#!/usr/bin/env bash
# install.sh — 一条命令把清单里的技能装到本地（给 WorkBuddy 用）。
#
#   curl -fsSL https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/install.sh | bash -s -- --all
#   ... | bash -s -- --only law-skills,smart-charts
#   ... | bash -s -- --list
#
# 它只做三件事：取 install.py、取 catalog.json、交给 python 跑。仓库里没有
# 技能正文，正文由 install.py 按清单里的引用从原件处取回。
set -euo pipefail

REF="${AFS_REF:-main}"
BASE="${AFS_BASE:-https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@${REF}}"

command -v python3 >/dev/null 2>&1 || {
  echo "✗ 需要 python3（macOS: brew install python3）" >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "✗ 需要 curl" >&2
  exit 1
}

# 没给参数时默认全装
[ $# -eq 0 ] && set -- --all

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ 取 install.py 与 catalog.json（$REF）"
curl -fsSL "$BASE/scripts/install.py" -o "$TMP/install.py"
curl -fsSL "$BASE/catalog.json" -o "$TMP/catalog.json"

exec python3 "$TMP/install.py" --catalog "$TMP/catalog.json" "$@"
