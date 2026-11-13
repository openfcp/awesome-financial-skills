#!/usr/bin/env bash
# install.sh — 一条命令把清单里的技能装到本地（给 WorkBuddy 用）。
#
#   curl -fsSL https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/install.sh | bash -s -- --all
#   ... | bash -s -- --only law-skills,smart-charts
#   ... | bash -s -- --list
#
# 它只做三件事：取 install.py、取 catalog.json、交给 python 跑。仓库里没有
# 技能正文，正文由 install.py 按清单里的引用从原件处取回。
#
# 注意：这是**终端命令**，不是「添加市场」输入框里能填的市场源。
set -euo pipefail

REF="${AFS_REF:-main}"

# 按顺序试镜像。raw 放前面：jsDelivr 会把 @main 的解析结果缓存十几小时，
# 仓库刚改完它还在发旧清单（曾用旧清单去装已删除的 ./plugins/*，全失败）。
MIRRORS=(
  "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/${REF}"
  "https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@${REF}"
)

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
trap 'rm -rf "${TMP}"' EXIT

# fetch <仓库内相对路径> <落地文件>：逐个镜像试，带上时间戳绕开 CDN 旧副本
fetch() {
  local rel="$1" out="$2" base
  for base in "${MIRRORS[@]}"; do
    if curl -fsSL --max-time 40 "${base}/${rel}?t=$(date +%s)" -o "${out}"; then
      return 0
    fi
  done
  echo "✗ 取不到 ${rel}（所有镜像都失败）" >&2
  return 1
}

echo "→ 取 install.py 与 catalog.json（${REF}）"
fetch "scripts/install.py" "${TMP}/install.py"
fetch "catalog.json" "${TMP}/catalog.json"

# 不用 exec：exec 之后 EXIT trap 不跑，临时目录会漏在 /tmp 里
python3 "${TMP}/install.py" --catalog "${TMP}/catalog.json" "$@"
