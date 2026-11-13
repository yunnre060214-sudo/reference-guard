# 工具工作流与数据契约

## 导航

- 环境与退出码
- 输入与工作底稿
- 登记元数据与字段比对
- 复核与冻结导出
- 版本迁移与限制

## 环境与退出码

工具面向 Python 3.10+、Node.js 20+，仅使用 Python 标准库与随包 citeproc-js。在运行环境中将下面的 `S` 设为实际 skill 目录，工作文件放入独立任务目录，不写回 skill。

```sh
S=/absolute/path/to/reference-guard
python3 "$S/scripts/reference_guard.py" doctor
```

`doctor` 离线检查运行时和 manifest 内全部六项资源摘要；它不检测网络或真实子代理能力。Node 不可用时，DOI、audit、packet/check 和文本导出仍可单独运行。成功输出不表示规范条款或来源已核实。

退出码：`doi_metadata.py` 的 0 表示每个输入都取得登记记录，1 表示存在未取得记录/非法 DOI，2 表示输入输出或参数错误。`review_gate.py check` 的 0 只表示结构通过，包括可明确部分交付的情形；1 表示阻断，2 表示输入错误。`reference_guard.py` 的 0 表示命令完成，doctor 检查失败为 1，其他阻断/输入错误为 2。`audit` 发现差异仍返回 0，因为它成功生成诊断；不能用退出码代替逐条处理。格式工具失败返回 1。

## 输入与工作底稿

推荐使用 UTF-8 JSON 字符串数组，每个元素是一条完整原始文献，允许元素内包含换行。`--input-format lines` 仅用于已确认一行一条的文件，空行会报错；不自动猜测折行或从 PDF 提取结构。`init` 不去重、不核验、不补元数据，所有条目初始为 unresolved。

```sh
python3 "$S/scripts/reference_guard.py" init --input originals.json \
  --main-agent-id '<真实主代理ID>' --style 'APA 7' --output draft.json
```

用户明确无格式要求时改用 `--no-style-requirement`；格式未定就省略这两个选项，真实性核查可继续，格式交付会被阻断。记录真实来源后补齐 `style.rules`，工具不会自动把模板当作已阅读规范。`input` 保存原文件名、字节 SHA-256、原始数量及 ID/原文序列的 originals_sha256；gate 会核对数量与原文指纹，主代理仍须确认文件提取完整。它不证明未被登记的源材料已完整覆盖。

为每条维护来源、作品/版本身份和字段证据。推荐在条目里附加 `field_evidence`、`corrections`、`search_log`，这些扩展字段也进入完整草稿摘要。主代理不得把新增字段当作已独立核验的证明。

## 登记元数据与字段比对

```sh
python3 "$S/scripts/doi_metadata.py" --input dois.txt --output metadata.json \
  --cache-dir .doi-cache --retries 2 --timeout 20
python3 "$S/scripts/doi_metadata.py" --input dois.txt --offline --cache-dir .doi-cache
python3 "$S/scripts/reference_guard.py" audit --items items.json \
  --metadata metadata.json --output audit.json
```

DOI 文件每个非空行是一个精确 DOI 或 doi.org URL；不从自由文本自动截取，不删除可能属于 DOI 的句点或括号。URL 中字面 `?` 和 `#` 必须编码；拒绝追踪参数与片段以避免静默截断标识符。批内相同 DOI 只查询一次，输出保留每次输入及其顺序。

Crossref 与 DataCite 顺序查询，404 尝试另一登记机构；某机构访问失败后也可尝试另一机构。仅两个接口都明确 404 才报告 `not_found_in_registries`，仍不证明作品不存在。响应标识符错配立即报告 `response_mismatch`。429、5xx 和网络错误最多按 `--retries 0..3` 重试，退避至多 30 秒，记录每次尝试。可显式 `--mailto` 提供联系邮箱，该地址会发给登记接口；工具不会自行收集邮箱。

缓存需显式指定目录，只保存取得的登记记录，检查 DOI、记录摘要和年龄，默认有效期 86400 秒。过期或损坏不回退为可信记录，离线缺失为 `cache_miss`。保留原抓取时间；缓存摘要只能检测意外改动，不能认证来源。独立复核仍须实际打开来源。

`audit` 输入已整理的 CSL-JSON 和登记工具输出，诊断题名、责任者顺序、载体、卷期、页码、文章编号和日期差异，保留在线/印刷等日期种类。相似度是检索提示，没有自动“确认同一作品”的阈值；未提供/登记未覆盖字段是 `not_compared`。多份不同登记记录会报告冲突，不按先后或多数票择一。共享 DOI 只产生重复候选组；无 DOI 条目进入非 DOI 核查流程。工具不自动生成经核验的 CSL，不决定引用版本，也不覆盖所有登记字段。

## 复核与冻结导出

按 adversarial-review.md 填写 draft，按 formatting.md 生成候选。将格式工具的 `bibliography_order` 写入草稿，特别是 APA 等排序文献表。顺序必须恰好覆盖 include 项，每个 ID 一次；不重排原始 entries。将最终候选文本写入 candidate，HTML 写入 candidate_html，布局写入 presentation。

交付外部 HTML、DOCX 或 PDF 时，在草稿目录内先完成文件，添加：

```json
{"artifacts": [{"path": "final.pdf", "sha256": "实际文件字节的小写SHA256"}]}
```

以上仅为字段示意。路径必须相对 draft 所在目录，不能越界或通过符号链接逃逸。把文件交给真实子代理实际查看；CLI check/export 同时验证文件字节。最终文件修改后重新登记摘要、生成 packet，并重新复核。摘要不能证明视觉排版已被检查。

```sh
python3 "$S/scripts/review_gate.py" packet --draft draft.json --output packet.json
# 将 packet 和实际材料交给真实子代理，接收本次 review.json
python3 "$S/scripts/review_gate.py" check --draft draft.json --review review.json
python3 "$S/scripts/reference_guard.py" export --draft draft.json \
  --review review.json --output-dir release
```

`packet` 隐去主代理判定与证据台账，同时以摘要绑定完整草稿。真实子代理返回相同 packet_sha256 和全部 ID 的逐条结果。摘要绑定取舍但不向它提供取舍结论；它须独立给 pass/fix/unresolved/needs_user/duplicate。主代理据此更新取舍后，重新生成 packet 并复核当前完整稿。

未解决项存在时 export 默认阻断；已满足部分交付条件才显式加 `--allow-partial`，且至少要有一条已通过。输出目录必须不存在，避免覆盖历史交付。

- `bibliography.txt`：按冻结次序逐条输出 candidate，不重写内容，仅以换行连接并追加末尾换行。纯文本不会保留斜体、缩进等排版。
- `report.md`：原始条目、取舍、主代理来源及审查问题；已修正错误放 review 行的 `original_issues`，当前问题放 `issues`。详细证据见 release.json。
- `release.json`：完整 draft、review、结构检查和 complete/partial 状态，保留 candidate_html 与全部扩展证据。它不是新的真实性认证。
- `manifest.json`：前三个文件的字节摘要与草稿摘要。交付后可据此检测修改；不冒充数字签名。

外部富文本文件保留在原位置，导出器不复制或重新排版；与上述核查材料一起交付经过实际复核的文件。不要把 bibliography.txt 作为 APA 等富文本排版通过的证明。

## 版本迁移与限制

2.0 接受 schema_version 为 1 或 2 的草稿，新增底稿使用 2。摘要契约已升级，旧 packet/review 无法直接沿用，必须重新生成资料包并真实复核。格式器输出 schema_version 2，额外包含输入摘要、输入/输出位置与排序映射。

工具不实际创建代理，不验证代理 ID 的真实性，不判定任意文献存在，不证明某标准所有条款都正确实现。不可手写“真实代理ID”与 pass 来冒充真实审查。标准、来源或代理能力受限时，按 SKILL 的未完成契约交付。
