## 这次提交

- 技能 id：`<your-skill-id>`
- 分类：`<categories 里的 id>`
- 来源：`skillhub` / `github`（附仓库或 SkillHub 链接）

## 自查

- [ ] 只改了 `catalog.json`，**没有把技能正文复制进仓库**
- [ ] 许可已核对（原件明确声明；没有声明的填 `proprietary`）
- [ ] `category` 命中 `catalog.json` → `categories[].id` 里已有的值
- [ ] `name.zh` / `name.en` / `summary.zh` / `summary.en` 都填了
- [ ] 本地跑过 `python3 scripts/build.py --check`，通过
- [ ] 本地跑过 `python3 scripts/install.py --verify --only <your-skill-id>`，能取回正文
- [ ] 没有手改 `docs/catalog.js`、`marketplace.json`、`dist/`（都是构建产物）

> 分类不全或不会写 JSON 也没关系：走 [提交表单](https://github.com/openfcp/awesome-financial-skills/issues/new?template=skill-submission.yml)，维护者代录入。

## 它解决什么

<!-- 具体到什么岗位、什么任务；不要写「提升金融效率」这类泛化描述 -->

## 能力边界与人工兜底

<!-- 不适用于什么场景？哪一步必须人来看？涉及投资建议、征信、承保的要写明 -->

## 你实际用它做过什么

<!-- 一句话也行：跑过哪类任务、结果如何、哪里需要返工。没有实际使用记录的建议先走 Issue 表单 -->
