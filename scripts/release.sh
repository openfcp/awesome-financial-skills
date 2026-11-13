#!/usr/bin/env bash
# release.sh — 校验清单，生成站点数据，推到远程。
#
#   ./scripts/release.sh                    # 默认提交信息
#   ./scripts/release.sh "feat: 新增 xx"     # 指定
#   DRY=1 ./scripts/release.sh              # 只看会改什么，不推送
#   SKIP_VERIFY=1 ./scripts/release.sh      # 跳过引用连通性检查（离线时用）
#
# 仓库里没有插件包、没有 npm 发布、没有 dsh 索引 —— 只有一份清单和站点，
# 所以发布只有一步：build 出 docs/catalog.js，然后 sync 推上去。
set -euo pipefail
cd "$(dirname "$0")/.."

MSG="${1:-chore: 重新生成清单与站点数据}"
DRY_ARGS=()
[ "${DRY:-0}" = "1" ] && DRY_ARGS=(--dry-run)

echo "── 1/4 校验清单（含「仓内不得有正文」守卫）──"
python3 scripts/build.py --check

if [ "${SKIP_VERIFY:-0}" = "1" ]; then
  echo "── 2/4 跳过引用连通性检查（SKIP_VERIFY=1）──"
else
  echo "── 2/4 检查每条引用是否还能取回正文 ─────────"
  python3 scripts/install.py --verify || {
    echo "✗ 有引用取不回了。先修 catalog.json，或用 SKIP_VERIFY=1 强行发布。"
    exit 1
  }
fi

echo "── 3/4 生成站点数据 ────────────────────────"
python3 scripts/build.py

echo "── 4/4 推送 ────────────────────────────────"
python3 scripts/sync.py -m "$MSG" "${DRY_ARGS[@]+"${DRY_ARGS[@]}"}"

echo
echo "✓ 完成。"
echo "  站点  https://openfcp.github.io/awesome-financial-skills/"
echo "  清单  https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"
