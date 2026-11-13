# 维护手册 · 收录与发版

> 照着做就行。为什么这么设计、市场机制怎么运作，看 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。
> 这份文档只讲**动作**：改哪儿、跑什么、看到什么才算成功。

---

## 0. 一分钟版

| 我要做什么 | 命令 |
|---|---|
| **新增一条技能** | `WITH_MARKET=1 MARKET_ONLY=<新id> ./scripts/release.sh "feat: 新增 xx"` |
| **作者更新了正文**（镜像包） | `WITH_MARKET=1 MARKET_FORCE=1 MARKET_ONLY=<id> ./scripts/release.sh "chore: 刷新 xx"` |
| **下架一条技能** | 删 `catalog.json` 条目 → `WITH_MARKET=1 ./scripts/release.sh "chore: 下架 xx"` |
| **只改文案 / 分类 / 排序** | `./scripts/release.sh "docs: …"`（带 `WITH_MARKET=1` 才会刷新市场卡片描述） |
| **发布后验收** | `python3 scripts/check_market.py` |
| **只看不动** | `DRY=1 ./scripts/release.sh` |

---

## 1. 先记住这张图

`catalog.json` 是唯一源头，但它**不会自动改动任何东西**。所有产物都要靠命令生成：

```
catalog.json
  ├─ build.py ─────────────▶ docs/catalog.js ──▶ 静态站（GitHub Pages）
  ├─ pack_market.py ───────▶ marketplace.json（市场清单，16 条卡片）
  │                    └────▶ dist/pkgs/*.zip
  └─ publish_market.py ────▶ marketplace 分支（用户点装时真正下载的包）
```

由此得到两条铁律：

1. **市场清单不由 `build.py` 生成**。只跑 `release.sh`（不带 `WITH_MARKET=1`），站点会有新卡片，WorkBuddy 市场里没有。
2. **包和清单必须一起变**。清单里写着每个包的 sha256，包换了而清单没推，用户点装会「校验失败」，看起来像装不上。

`WITH_MARKET=1 ./scripts/release.sh` 一次做完：校验 → 验证引用 → 生成站点 → 出包 → 更新清单 → 推分支 → 推 main → 自动验收。

---

## 2. 环境（一次性）

```bash
python3 --version      # 需要 3.9+，脚本只用标准库，无第三方依赖
gh auth status         # 需要已登录：sync.py 和 publish_market.py 都从 gh 取 token
```

- 不需要 `npm install`，不需要 `pip install`。
- 本机网络走代理，`api.github.com` 偶发 502——三个脚本都内置了退避重试，**看到 502 先重跑一次**，不要改代码。
- 可选：`export GITHUB_TOKEN=…` 优先于 `gh auth token`，只发给 `api.github.com`。

---

## 3. 场景 A：新增一条技能

> 也可以交给 skill：把「来源 + 名称 + 地址 + 类别」发给 AI，`awesome-skill-curator` 会走完下面全部步骤（读原件 → 写清单 → 发版 → 验收 → 告诉你刷新两个客户端）。
> 手动做的话，机械部分用 `python3 scripts/add_skill.py`，别手改 JSON。

### A1 · 确认来源

**首选 SkillHub。** 同一个技能两处都有时，记 SkillHub 的坐标——正文由它托管，且有签名校验。

只有在 SkillHub 上找不到时，才用 GitHub 源（`repo` + `path` + `ref`）。

### A2 · 写进 `catalog.json`

在 `skills` 数组末尾加一条。**SkillHub 源**：

```json
{
  "id": "new-skill-id",
  "name":    { "zh": "中文名", "en": "English Name" },
  "summary": { "zh": "一句话说清：解决什么岗位的什么任务，边界在哪。", "en": "One line." },
  "category": "consumer-protection",
  "tags": ["审查", "营销材料"],
  "version": "1.0.0",
  "author": "作者署名",
  "license": "proprietary",
  "source": { "type": "skillhub", "namespace": "user_xxxxxxxx", "slug": "new-skill-id" },
  "install": { "skillhub": "skillhub install new-skill-id --namespace user_xxxxxxxx" }
}
```

**GitHub 源**（把后两行换成）：

```json
"source": { "type": "github", "repo": "owner/repo", "path": "skills/new-skill-id", "ref": "main", "vendored": false },
"install": { "plugin": "./skills/new-skill-id" }
```

四个字段容易写错，逐条对：

| 字段 | 规则 |
|---|---|
| `id` | 小写 + 连字符，仓内唯一。它是市场卡片的 `name`，也是包的 zip 名，**定了别改**（改了等于下架+新增） |
| `category` | 必须是 `categories[].id` 里已有的；新增分类要先加分类 |
| `license` | **照实填**。它决定出镜像包还是取件器，填错就是侵权或白折腾 |
| `summary.zh` | 会直接变成市场卡片的描述，写成给人看的一句话，不是关键词堆砌 |

### A3 · 本地校验

```bash
python3 scripts/build.py --check
```

期望输出：

```
[build] 校验通过：17 条引用 / 9 个分类 / 来源 {'skillhub': 17}
[build] 空分类：research-analysis, risk-management, …
```

看到 `仓库内出现未声明的技能正文：xx/SKILL.md` 就是踩了红线——把正文复制进仓了，删掉。

### A4 · 发版

```bash
WITH_MARKET=1 MARKET_ONLY=new-skill-id ./scripts/release.sh "feat: 新增 中文名"
```

`MARKET_ONLY` 只重打这一条，其余 16 个包沿用现有文件，快很多。不带它则全量重打（有缓存，也就慢几秒）。

期望输出（关键几行）：

```
[build] 校验通过：17 条引用 …
[install] 17/17 条引用可用
[pack] new-skill-id                          取件      2.0 KB
[pack] --only 模式：清单合并后 17 条（本次重打 1 条，沿用 16 条）
[publish] 17 个包，合计 2.00 MB
[publish] marketplace → 1a2b3c4d5e（17 个包）
[sync] 完成 9f8e7d6c5b  https://github.com/…/commit/…
[check] ✓ 通过：清单 17 条 / 分支 17 包 / sha256 全部一致
```

`[check] ✓` 是最后一道闸。**没有它就别当成完事**。

> 网络慢、`install.py --verify` 卡在逐条回源时，可以 `SKIP_VERIFY=1` 跳过——但那一步是唯一能提前发现「作者把技能删了」的检查，非必要别跳。

### A5 · 在 WorkBuddy 里确认

市场卡片来自 `marketplace.json`，重新添加一次市场（或刷新市场源）就能看到新卡；点装后按卡片类型决定体验：

- **镜像包**（`license` 是 MIT 等）：点装即可用，离线可用。
- **取件器**（其余）：点装后第一次调用时，按 `SKILL.md` 的指引跑一次 `python3 scripts/fetch.py` 取回正文。

---

## 4. 场景 B：作者更新了正文

两种包的处理完全不同，先看是哪一类：

```bash
python3 -c "
import json
for p in json.load(open('marketplace.json'))['plugins']:
    print(f\"{p['name']:<44}{p['license']}\")
"
```

| 类型 | 要不要重打 | 命令 |
|---|---|---|
| 取件器（`proprietary`） | **不用**。每次用都从原作者处现取最新版 | —— |
| 镜像包（MIT 等） | **要**，而且必须 `MARKET_FORCE=1` 才会重新下载正文 | 见下 |

```bash
WITH_MARKET=1 MARKET_FORCE=1 MARKET_ONLY=law-skills ./scripts/release.sh "chore: 刷新 law-skills"
```

不加 `MARKET_FORCE=1` 时，`pack_market.py` 会直接复用 `dist/pkgs/` 里的旧包（这是为了不让每次发版都重下 3 个镜像），于是"刷新"其实什么都没做。

---

## 5. 场景 C：下架一条技能（含作者要求下架）

1. 从 `catalog.json` 删掉该条目；
2. 跑全量（不要带 `MARKET_ONLY`）：

```bash
WITH_MARKET=1 ./scripts/release.sh "chore: 下架 xxx"
```

期望在输出里看到两行，说明清单和本地包都跟着收敛了：

```
[pack] 已从 catalog 移除、本次一并从清单删除：xxx
[pack] 清理孤儿包（不在清单里，已下架或改名）：xxx
```

`publish_market.py` 是**整体替换**分支内容，所以分支上那个 zip 会一并消失。验收时 `check_market.py` 会核对「分支包集合 == 清单集合」，多一个少一个都会报。

> 作者本人要求下架：删条目 + 发版，并在 issue 里回复一句已处理。24 小时内完成是我们的承诺。

---

## 6. 场景 D：只改文案 / 分类 / 排序

```bash
./scripts/release.sh "docs: 修正 xx 的描述"
```

站点会更新。**但市场卡片的描述不会变**——它来自 `marketplace.json` 的 `description`，只有 `pack_market.py` 会写这个文件。在意的话带上 `WITH_MARKET=1`（会重打全部包，13 个取件器的 sha 都会变，属正常）。

---

## 7. 场景 E：换机器 / 新克隆

```bash
gh auth login                 # 必需：推 main 和推分支都靠它
git clone https://github.com/openfcp/awesome-financial-skills.git
cd awesome-financial-skills
python3 scripts/build.py --check          # 确认环境 OK
python3 scripts/install.py --verify       # 确认 16 条引用都还取得到
```

`dist/` 是 gitignore 的本地产物，新克隆里没有。第一次 `pack_market.py` 会从 SkillHub 下载 3 个镜像包（约 2 MB），之后走缓存。

> 本仓**不要用 `git commit` / `git push`**：本机直连 github.com 会被代理拒。所有推送走 `scripts/sync.py`（GitHub API）。本地 `.git` 历史与远程不一致是正常现象。

---

## 8. 发布后验收

```bash
python3 scripts/check_market.py        # 加 -q 只看问题
```

它查四件事，30 秒内给结论：

| 检查 | 失败含义 |
|---|---|
| 线上 `marketplace.json` 与本地一致 | 清单没推上去（只跑了 pack，没跑 sync） |
| `marketplace` 分支只有 `pkgs/*.zip`，且包集合 == 清单集合 | 有历史产物残留 / 有包没传 |
| 每个 zip 都能 200 拿到 | 包没传到分支，或名字对不上 |
| 每个 zip 的实际 sha256 == 清单里写的 | 包换了而清单没更新——**这是用户点装失败最常见的原因** |

期望最后一行：

```
[check] ✓ 通过：清单 17 条 / 分支 17 包 / sha256 全部一致
```

手工核对版（不想跑脚本时）：

```bash
# 线上清单条数
curl -fsSL "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/marketplace.json?t=$(date +%s)" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d['plugins']),'条')"

# 分支上的包
gh api "repos/openfcp/awesome-financial-skills/git/trees/marketplace?recursive=1" \
  --jq '[.tree[]|select(.type=="blob")|.path]|length'
```

---

## 9. 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 市场里点了装，报 sha256 / 校验失败 | 包传上去了，`marketplace.json` 还没推 | `./scripts/release.sh "chore: 同步清单"`（或重跑 `WITH_MARKET=1`） |
| 市场里少了几张卡 | 清单被写残（旧版 `--only` 的 bug），或 `pack_market.py` 中断 | `python3 scripts/pack_market.py` 全量重打 → `check_market.py` |
| 站点有卡片、市场没有 | 只跑了站点链路 | 带 `WITH_MARKET=1` 重跑 |
| 站点改了页面没变 | Pages 的 600s 缓存 | `build.py` 已给 `catalog.js` 打了内容指纹，强刷即可 |
| `502 Bad Gateway` / `Tunnel connection failed` | 本机代理抖 | 重跑；脚本已重试 5 次 |
| `gh: command not found` / `not logged in` | 环境没配 | `brew install gh && gh auth login` |
| `仓库内出现未声明的技能正文` | 把技能正文复制进仓了 | 删掉；正文只留在原作者处 |
| 取件器第一次用提示「已存在」 | 该技能之前装过 | 直接读 `~/.workbuddy/skills/<name>/SKILL.md`，不用再取 |
| `[publish] 清单里有 N 条没有对应的包` | 只 `pack` 了部分，或包被删了 | `python3 scripts/pack_market.py` 补齐再发 |
| 加了技能但 `[pack]` 报 `镜像包只支持 skillhub 源` | GitHub 源被标成 MIT，走了镜像分支 | 正常，GitHub 源一律出取件器；脚本已自动改走取件器，若仍报错检查脚本版本 |
| dsh 里看不到新条目 | 目录缓存 6 小时，或页脚显示 `snapshot`（离线用随包快照） | 页脚点「刷新」；仍旧则 `rm -f ~/.dsh/storages/financial-skills/catalog.cache.json` 再刷 |

---

## 10. 红线

1. **不把技能正文放进仓库**，包括 `dist/` 里生成后又提交。`build.py` 会拦。
2. **不手改 `docs/catalog.js`、`marketplace.json`**，它们是产物；改 `catalog.json` 再构建。
3. **不把 `proprietary` 改成镜像包**。许可不明按未授权处理，只出取件器。
4. **不用 `git push`**，走 `scripts/sync.py`。也别 `--amend` 改历史。

---

## 11. 发布检查清单

发版前：

- [ ] `catalog.json` 的 `id` 唯一、`category` 存在、`license` 照实填、`summary.zh` 是人话
- [ ] `python3 scripts/build.py --check` 通过

发版后：

- [ ] `[pack]` 里该重打的条目确实重打了（不是「沿用」）
- [ ] `[publish]` 的包数与清单条数一致
- [ ] `[sync]` 打印了新的 commit
- [ ] `check_market.py` 输出 `✓ 通过`
- [ ] WorkBuddy 市场里能看到新卡，点装可用
