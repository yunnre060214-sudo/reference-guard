# reference-guard · 参考文献纠错

[English](README.en.md) · [执行指令](skills/reference-guard/SKILL.md) · [工具工作流](skills/reference-guard/references/workflow.md) · [验证记录](docs/VALIDATION.md) · [更新记录](CHANGELOG.md)

**2.0.0**：为参考文献建立从原始输入、来源证据、字段比对、格式生成到独立复核与冻结交付的完整流程。目标是文献真实、作品与出版版本一致、著录字段准确、格式符合本次要求。

## 能做什么

- 保留每条原始文献、稳定 ID、输入指纹与输出顺序，检查初始化后漏项或原文变化。
- 批量查询 Crossref/DataCite，支持文件输入、有限重试、登记机构回退、可选本地缓存与离线读取；网络错误与未找到记录分开报告。
- 比对 CSL-JSON 与登记元数据，提示题名、作者、卷期、页码、文章编号和日期差异；共享 DOI 只标记重复候选，不自动合并。
- 随包提供 GB/T 7714—2025、APA 7、IEEE 和 citeproc-js，支持独立自定义 CSL，输出文本、HTML、布局及 ID 排序映射。
- 强制真实子代理逐条独立复核。摘要绑定完整草稿，包含取舍、证据、重复映射和排序；外部交付文件同时校验字节摘要。
- 通过检查后原样导出文献表、问题记录、完整证据材料及文件摘要；部分交付必须明确标注，保留全部未解决原文。

辅助工具不会证明文献真实或代理确实创建。检索不到不等于作品不存在；登记记录、相似度和格式器成功均不能替代实际来源查阅与独立复核。本项目只处理文末参考文献，正文论断支持性、引文编号和引用版本选择由写作流程负责。

## 安装

把下面这段交给支持 Agent Skills 的 agent：

```text
请安装 https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard 中的 reference-guard。保留整个目录，包括 references、scripts、assets、agents 与许可证文件。安装后运行 doctor，并确认宿主能实际访问来源与创建真实独立子代理。
```

也可通过 [skills CLI](https://github.com/vercel-labs/skills) 按提示选择自己的 agent：

```sh
npx skills add yunnre060214-sudo/reference-guard --skill reference-guard
```

全局使用可加 `-g`，支持的 agent 及实际安装位置以安装工具为准。手动安装时复制 `skills/reference-guard/` 整个目录，按宿主方式重新加载。不要仅复制 SKILL.md。

## 使用

```text
使用 reference-guard 核查这篇论文的参考文献，按学校模板修正，保留每条来源，交付问题说明、修正版和未解决项。
```

```text
使用 reference-guard 检查这份文献表。我没有格式要求，请完成真实逐条独立复核后交付。
```

用户已有格式要求时直接采用；未明确时先询问，同时可继续真实性核查。只有明确无格式要求才采用 GB/T 7714—2025。无法核实目标规范、来源或没有真实子代理时，报告未完成与实际已完成部分。

## 工具快速开始

需要 Python 3.10+、Node.js 20+，无需 pip/npm 安装额外依赖。在仓库根目录运行：

```sh
python3 skills/reference-guard/scripts/reference_guard.py doctor
python3 skills/reference-guard/scripts/reference_guard.py --version
```

下面使用**虚构演示数据**，只演示输入保留与格式生成，不代表文献已被核实：

```sh
python3 skills/reference-guard/scripts/reference_guard.py init \
  --input examples/originals.synthetic.json --main-agent-id YOUR_ACTUAL_AGENT_ID \
  --style 'APA 7' --output draft.json
node skills/reference-guard/scripts/format_bibliography.cjs \
  --input examples/items.synthetic.json --style apa7 --output rendered.json
```

对实际 DOI 可执行：

```sh
python3 skills/reference-guard/scripts/doi_metadata.py 10.1038/s41586-021-03819-2
python3 skills/reference-guard/scripts/doi_metadata.py --input dois.txt \
  --output metadata.json --cache-dir .doi-cache --retries 2
python3 skills/reference-guard/scripts/reference_guard.py audit \
  --items items.json --metadata metadata.json --output audit.json
```

核实来源、填好候选与规范证据后，生成资料包交给真实子代理。获得完整复核后检查并导出：

```sh
python3 skills/reference-guard/scripts/review_gate.py packet --draft draft.json --output packet.json
python3 skills/reference-guard/scripts/review_gate.py check --draft draft.json --review review.json
python3 skills/reference-guard/scripts/reference_guard.py export \
  --draft draft.json --review review.json --output-dir release
```

导出目录包含 `bibliography.txt`、`report.md`、`release.json`、`manifest.json`。未解决项存在时默认阻断导出，满足部分交付条件后显式加 `--allow-partial`；富文本文件单独完成视觉复核并登记为 artifacts，文本导出不承诺保留斜体或缩进。输出目录必须是新目录。

完整参数、退出码、数据契约、缓存限制与富文本流程见 [工具工作流](skills/reference-guard/references/workflow.md)。除 DOI 查询命令外，上述工具均可离线运行；`doctor` 无法测试网络和代理能力。

## 验证与升级

```sh
python3 -m unittest discover -s skills/reference-guard/scripts/tests -v
```

运行时需让 Node 在命令路径中；格式测试也支持 `REFERENCE_GUARD_TEST_NODE` 指定可执行文件。GitHub Actions 在多组 Python/Node 组合上运行离线回归与资源完整性检查，具体结果以该提交的 CI 为准。[验证记录](docs/VALIDATION.md) 区分历史与本次实测范围，不把测试通过当成任意文献或全部规范均已验证。

2.0 兼容 schema_version 1/2 的草稿结构，新增底稿和格式器输出使用 2。**旧复核摘要不能沿用**：更新后必须重新生成 packet 并对当前完整稿真实复核。初始化生成的输入清单应完整保留。

## 许可证

原创指令、工具与测试采用 AGPL-3.0-or-later。citeproc-js 以 AGPL-3.0-or-later 分发；CSL 样式与 locale 保留 CC-BY-SA-3.0 和原作者信息。见 [LICENSE](LICENSE)、[skill 许可证说明](skills/reference-guard/LICENSE.md)和[第三方声明](skills/reference-guard/assets/THIRD_PARTY_NOTICES.md)。标准与出版者手册全文未随包分发。
