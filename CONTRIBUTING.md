# 贡献指南

感谢补充内容。为了让这份清单保持"能直接用"而不是"又一个链接坟场"，提交前请过一遍下面的检查。

## 提交前自查

- [ ] 项目公开可访问，链接能正常打开（不是登录墙后的项目）
- [ ] 对应金融业务中的**具体岗位任务**，不是泛化的"金融问答"
- [ ] 已在 `catalog.json` 的 `skills` 中新增条目，`category` 命中九个分类之一
- [ ] `summary.zh` 与 `summary.en` 都已填写（站点卡片读这两个字段）
- [ ] `source` 填了真实坐标：SkillHub 要有 `namespace` + `slug`，GitHub 要有 `repo` + `path` + `ref`
- [ ] `version` 与技能本体 `SKILL.md` frontmatter 一致
- [ ] 跑了 `python3 scripts/build.py --check` 且通过
- [ ] 跑了 `python3 scripts/install.py --verify`，确认新条目真的能取回正文
- [ ] **没有把技能正文复制进仓库**——只写引用，不搬运内容

## 双来源优先级

**SkillHub 是权威来源。** 同一技能在 SkillHub 和 GitHub 都存在时，一律记 SkillHub 的坐标与版本，不用 GitHub 副本替换：

```json
"source": { "type": "skillhub", "namespace": "<namespace>", "slug": "<slug>" },
"install": { "skillhub": "skillhub install <slug> --namespace <namespace>" }
```

仅当 SkillHub 确实没有发布时才标 `github` 源，并在 PR 里说明原因。

## 不要往仓库里放正文

这是本仓库的硬规则，也是构建时会强制检查的一条：**`plugins/` 这种"镜像一份"的做法已经废弃**。

- 作者更新后镜像必然过期，读者装到的是老版本；
- 正文版权归作者，清单只是索引，没有转授权；
- 同一个技能为喂不同客户端还要各生成一套包装文件，仓库迅速膨胀。

`build.py` 会扫描全仓，凡出现清单未声明的 `SKILL.md` 一律构建失败。`source.vendored: true` 的机制保留给"正文无法引用回原件"的特例（当前没有）——新增这类例外需要在 PR 里说明为什么无法引用。

## 新增技能的最小步骤

```bash
# 1) 在 catalog.json 的 skills 里加条目（只写坐标，不复制文件）
# 2) 校验 + 验证引用能取回正文
python3 scripts/build.py --check
python3 scripts/install.py --only <id> --dry-run
# 3) 一键发布（校验 → 验证每条引用 → 构建站点 → 推送）
./scripts/release.sh "feat: 收录 <slug>"
```

## PR 规范

1. **一条 PR 只加一个技能**，评审更快；
2. 只提交 `catalog.json` 的改动，不提交技能正文文件；
3. 不要手改 `docs/catalog.js`（构建产物，`release.sh` 会覆盖）；
4. PR 描述里回答：你用它实际完成过什么任务？哪里需要人工兜底？

## 移除规则

| 情况 | 处理 |
|---|---|
| 链接失效超过 30 天 | 移除 |
| 连续 24 个月无更新 | 标注 `[archived]` 并降低排序 |
| 被发现夸大能力、隐瞒边界 | 移除并在 PR 中说明 |
| 出现诱导投资、承诺收益等表述 | 立即移除 |
