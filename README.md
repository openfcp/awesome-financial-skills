# 金融行业skill精选 · Awesome Financial Skills

> 为金融从业者策展的 AI 技能清单。按业务场景分九类，标注来源与能力边界。
> **仓库只存引用，不存技能正文**——正文始终留在原作者那里，装的时候现取。

**网站**：https://openfcp.github.io/awesome-financial-skills/
**清单源文件**：[`catalog.json`](./catalog.json)（唯一真相源，站点数据由它生成）
**架构与原理**：[`ARCHITECTURE.md`](./ARCHITECTURE.md)（WorkBuddy 市场怎么工作、为什么这么设计、踩过的坑）

---

## 为什么不把技能正文放进仓库

上一版把 17 个技能完整复制进 `plugins/`，10 MB、555 个文件。实测比对：这些副本与 SkillHub 上的原件**字节级完全一致**，也就是说这 10 MB 全是搬运，代价是：

- **必然过期**——作者更新后仓库里的副本还是旧的，读者装到的是老版本；
- **版权不清**——正文版权属作者，清单作者只是索引，没有转授权；
- **体积膨胀**——每加一个技能就多一份正文，仓库最终会长成一个臃肿的镜像站；
- **三份包装**——同一份正文为了喂不同客户端，还要各自生成 `package.json` / `index.js` / 插件元数据。

现在的做法：`catalog.json` 里每条只记**坐标**（SkillHub 的 `namespace/slug`，或 GitHub 的 `repo/path/ref`），消费端按清单顶部的 `resolve` 规则回原件取正文。仓库体积从 22 MB 降到 20 KB 量级，收录新技能只改一行 JSON。

> **零正文**：仓内任何位置出现清单未声明的 `SKILL.md` 都会让构建失败——防止副本再长回来。`vendored: true` 机制保留给"正文确实必须在本仓"的特例（当前没有），用到时构建会校验目录真实存在。

---

## 三种消费方式

| 用途 | 地址 | 怎么用 |
|---|---|---|
| **浏览 / 检索** | https://openfcp.github.io/awesome-financial-skills/ | 直接打开：九类筛选、来源筛选、中英切换、一键复制安装命令 |
| **WorkBuddy 安装** | 添加市场（清单地址）或终端一条命令，见下 | 读清单 → 点哪张装哪张 → 正文按需取回 |
| **SkillHub CLI** | `skillhub install <slug> --namespace <ns>` | 目录里每条都带完整命令，站点卡片可复制 |

### WorkBuddy：添加市场（清单地址）

技能 → 套件 → 右上角「添加市场」，市场源填：

```
https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/marketplace.json
```

**添加时只下载这份清单（11 KB），不会把技能全部拉到本地。** 之后市场里出现 16 张卡，点哪张装哪张。

清单里每条都是 `archive` 源，按许可证分成两类：

| 类型 | 条数 | 包里是什么 | 装完能不能直接用 |
|---|---|---|---|
| **镜像**（MIT） | 3 | 从 SkillHub 取回的正文 + `plugin.json` + `NOTICE.md`（作者/原页面/许可） | ✅ 能，离线可用 |
| **取件器**（proprietary 或未声明） | 13 | 只有我们自己的 `plugin.json` / `SKILL.md` / `fetch.py`，约 2 KB | 首次使用时跑一次 `fetch.py`，从 SkillHub 现取正文 |

这样安排是因为：**未获再分发许可的正文不进本仓**。镜像的 3 条在包内附了 `NOTICE.md` 写明作者、原页面与许可证；如果你是作者并要求下架，到 issue 区提一条，我们 24 小时内移除对应包与清单条目。

**新增技能后，站点和市场要分别更新**（`catalog.json` 是共同源头，但两条链路由两套脚本生成，互不触发）：

```bash
WITH_MARKET=1 ./scripts/release.sh "feat: 新增 xx"   # 站点 + 市场包 + 市场清单，一条搞定
```

只刷新市场包、不动站点：

```bash
python3 scripts/pack_market.py     # 出 16 个包到 dist/pkgs，并重写 marketplace.json
python3 scripts/publish_market.py  # 推到 marketplace 分支，打印市场源地址
./scripts/release.sh "chore: 更新市场清单"   # marketplace.json 在 main 上，还得推一次
```

### WorkBuddy：终端一条命令

```bash
curl -fsSL https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/install.sh \
  | bash -s -- --all
```

> 这是**终端命令**，不是「添加市场」的市场源。那个输入框只认 GitHub 仓库、zip 地址、本地路径；把 `curl …` 粘进去会报 `Internal error`。

`install.sh` 只是把 `scripts/install.py` 和 `catalog.json` 取到临时目录再执行。取件按 `raw` → `jsDelivr` 顺序试，并带时间戳查询串：jsDelivr 会把 `@main` 解析结果缓存十几小时，只认它时会拿到旧清单。也可以克隆仓库后本地跑：

```bash
python3 scripts/install.py --list                  # 清单里有什么、本机装没装
python3 scripts/install.py --all                   # 全装（默认 ~/.workbuddy/skills）
python3 scripts/install.py --only law-skills       # 只装一个
python3 scripts/install.py --only a,b --dir ~/my   # 指定几个 + 指定目录
python3 scripts/install.py --verify                # 只验证引用还通不通，不落盘
python3 scripts/install.py --all --dry-run         # 只打印将要做什么
python3 scripts/install.py --all --force           # 已存在且内容不同时覆盖（旧的留 .bak）
```

行为约定，都是踩过坑定下来的：

- **目录名取 `SKILL.md` 的 `name`**，不是清单的 `id`。WorkBuddy 按 `name` 触发技能，二者不一致时列表里看得到却调不到（例：`id: ai-ppt-skill` → `name: ppt-master`）。
- **失败就是失败，不装空壳**。下载不到宁可缺一个，也不在技能目录里留一份只有 `SKILL.md` 的半成品——空壳能列出来，一调用就错，比装不上难排查得多。
- **token 只发给 `api.github.com`**。第三方 CDN 一律匿名，避免被平台判成凭证泄漏。
- **每次都取最新原件**。清单里的 `version` 是策展时记录的值，实际装到的是作者当前发布的版本；真需要锁定，用 GitHub 源的 `ref` 写死 commit。

### 给 dsh 插件作者：清单契约

清单是自描述的，插件的取回逻辑不必硬编码地址——读 `resolve` 就行：

```json
"resolve": {
  "skillhub": { "kind": "zip",   "url": "https://api.skillhub.cn/api/v1/download?slug={slug}" },
  "github":   { "kind": "files", "raw": "https://raw.githubusercontent.com/{repo}/{ref}/{path}",
                 "api": "https://api.github.com/repos/{repo}/contents/{path}?ref={ref}" }
}
```

任取一条技能：`source.type == "skillhub"` 就用 `{slug}` 拼 zip 地址、解压后 `SKILL.md` 在根；`source.type == "github"` 就把 `{path}` 目录下所有文件按 `{repo}@{ref}` 取回，`raw` 不通时退到 `api`（可带 token），再退到 `https://fastly.jsdelivr.net/gh/{repo}@{ref}/{path}`。`resolve` 里的模板用 `str.format` 语义替换，未知占位符保持原样即可。

---

## 清单格式（format 3）

```json
{
  "id": "consumer-protection-review",
  "name": { "zh": "消保审查", "en": "Consumer Protection Review" },
  "summary": { "zh": "…", "en": "…" },
  "category": "consumer-protection",
  "tags": ["审查", "营销材料"],
  "version": "1.0.0",
  "author": "八大权益",
  "license": "proprietary",
  "source": {
    "type": "skillhub",
    "namespace": "user_e3180ba3",
    "slug": "consumer-protection-review"
  },
  "install": {
    "skillhub": "skillhub install consumer-protection-review --namespace user_e3180ba3"
  }
}
```

GitHub 源把 `source` 换成：

```json
"source": { "type": "github", "repo": "owner/repo", "path": "skills/xxx", "ref": "main", "vendored": false },
"install": { "plugin": "./skills/xxx" }
```

`vendored: true` 只在"正文确实必须在本仓"时用（当前没有这类条目），构建会校验目录存在。

---

## 目录结构

```
ARCHITECTURE.md           架构与原理：市场机制、数据流、许可分流、决策日志
catalog.json              唯一真相源：分类 + 技能引用（双语、来源、安装方式、取回规则）
marketplace.json          WorkBuddy 市场清单（构建产物，16 条 archive 源）
schema.json               catalog 的 JSON Schema（构建时校验）
install.sh                一条命令装的引导脚本
docs/                     GitHub Pages 站点目录（Pages 只认 / 或 /docs）
  index.html              静态站（单文件，无外部依赖，file:// 也能打开）
  catalog.js              ← 构建产物，站点内嵌数据（带内容指纹）
scripts/
  install.py              读清单 → 回原件取正文 → 装进技能目录（WorkBuddy 侧）
  pack_market.py          出市场包：许可允许再分发的出镜像，其余出取件器
  publish_market.py       把 dist/pkgs 推到 marketplace 分支（整体替换）
  build.py                校验清单 + 生成 docs/catalog.js
  sync.py                 经 GitHub API 推送改动（绕开直连 github.com 的限制）
  release.sh              一键发布：校验 + 验证引用 + 构建 + 推送
```

## 本地开发

```bash
python3 scripts/build.py --check      # 只校验（含"仓内不得有正文"守卫）
python3 scripts/build.py --urls       # 顺便看每条引用的取回地址
python3 scripts/install.py --verify   # 逐条验证引用是否还取得到
npm run serve                         # 本地预览站点 http://localhost:8787
./scripts/release.sh "feat: …"        # 校验 + 验证 + 构建 + 推送
```

改清单的流程永远是：**改 `catalog.json` → 跑 `release.sh`**。不要手改 `docs/catalog.js`，它会被覆盖。

## 收录标准

1. **场景真实**——对应金融业务中的具体岗位任务，不是泛化的"金融问答"；
2. **边界清晰**——说明适用范围、不适用范围，以及必须人工复核的环节；
3. **来源可查**——**以 [SkillHub](https://skillhub.cn) 为唯一权威来源**；同一个技能 SkillHub 上有，就记 SkillHub 的坐标，不另存副本；
4. **可安装**——必须有可执行的安装方式（`skillhub install …`，或一个能被按目录取回的仓库路径）；
5. **合规自觉**——不承诺替代持牌机构决策，涉及投资建议、征信、承保须注明人工介入点。

**不收录**：纯 prompt 集合、无执行能力的角色扮演、无法验证效果的营销材料、以及**复制他人技能正文**的二次打包（只写引用，不搬运正文——这也是本仓库现在的硬规则）。

## 许可与免责

清单内容 MIT。各技能正文版权归各自作者，遵循其仓库或 `SKILL.md` 中的声明；来自 SkillHub 的技能以 SkillHub 上的许可为准。本清单是技术资源索引，不构成投资建议、法律意见或合规承诺；金融业务落地前请自行完成合规评估与人工复核。

## 贡献

见 [CONTRIBUTING.md](./CONTRIBUTING.md)。
