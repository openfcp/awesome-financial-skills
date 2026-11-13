#!/usr/bin/env bash
# release.sh — 校验清单，生成站点数据，推到远程。
#
#   ./scripts/release.sh                    # 默认提交信息
#   ./scripts/release.sh "feat: 新增 xx"     # 指定
#   DRY=1 ./scripts/release.sh              # 只看会改什么，不推送
#   SKIP_VERIFY=1 ./scripts/release.sh      # 跳过引用连通性检查（离线时用）
#
#   WITH_MARKET=1 ./scripts/release.sh "feat: 新增 xx"
#       同时重出市场包、更新 marketplace.json、推到 marketplace 分支，末尾自动验收。
#       **加了新技能就要带这个**，否则站点有新卡片、WorkBuddy 市场里没有。
#   WITH_MARKET=1 MARKET_ONLY=xx,yy ./scripts/release.sh   # 只重打这几个包
#   WITH_MARKET=1 MARKET_FORCE=1   ./scripts/release.sh   # 重新从 SkillHub 取正文
#
# 两条链路由两套脚本负责，互不触发：站点 ← build.py；市场 ← pack_market.py +
# publish_market.py。默认只走站点链路。
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

# 加了新技能、或想让市场里的包跟上最新正文时，用 WITH_MARKET=1。
# 市场清单（marketplace.json）和技能包（marketplace 分支）都不由 build.py 生成，
# 只跑 build + sync 会让「站点有新技能、市场里没有」——两条链路必须分别更新。
if [ "${WITH_MARKET:-0}" = "1" ]; then
  echo "── 3b/4 出市场包并发布到 marketplace 分支 ───"
  PACK_ARGS=()
  # MARKET_FORCE=1：忽略已缓存的镜像包，重新从 SkillHub 取正文（作者更新后用）
  [ "${MARKET_FORCE:-0}" = "1" ] && PACK_ARGS=(--force)
  if [ -n "${MARKET_ONLY:-}" ]; then
    python3 scripts/pack_market.py --only "${MARKET_ONLY}" "${PACK_ARGS[@]+"${PACK_ARGS[@]}"}"
  else
    python3 scripts/pack_market.py "${PACK_ARGS[@]+"${PACK_ARGS[@]}"}"
  fi
  python3 scripts/publish_market.py
fi

echo "── 4/4 推送 ────────────────────────────────"
python3 scripts/sync.py -m "$MSG" "${DRY_ARGS[@]+"${DRY_ARGS[@]}"}"

if [ "${WITH_MARKET:-0}" = "1" ] && [ "${DRY:-0}" != "1" ]; then
  echo "── 4b/4 验收：清单 / 分支 / 包 / sha256 ─────"
  # 只提醒不中断：验收失败说明要修，但此时改动已经推出去了，别让脚本在这里把上下文丢掉
  python3 scripts/check_market.py -q || echo "⚠ 验收未通过，见上面的问题清单；修完重跑本脚本即可"
fi

echo
echo "✓ 完成。"
echo "  站点  https://openfcp.github.io/awesome-financial-skills/"
echo "  清单  https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json"
