# 强制逐条独立对抗复核

## 派发条件与资料

每次交付前使用运行环境**真实可用**的子代理创建/委派工具。遵守当前会话或 AGENTS 对模型和推理配置的要求；指定配置不可用时说明，不静默替换。不给一个主代理自称的“第二人格”算复核，也不以外部聊天或新建用户任务代替内部子代理。

用独立上下文，给：完整原始条目及稳定 ID、当前候选修正版、用户确认的目标格式/模板、可查阅的规范来源、清晰的读写范围。富文本交付时同时给实际 HTML、布局和最终文件；复核最终载体的斜体、缩进等，不能只核对纯文本。主代理的已通过结论、字段核验台账、预期缺陷清单不作为答案传入。代理可独立查阅同一权威原始记录，但必须自己实际访问/核对。

需要机器检查时准备 `draft.json` 并生成去除主代理判定的资料包：

```sh
python3 <skill目录>/scripts/review_gate.py packet --draft draft.json --output packet.json
```

## 委派提示词

> 你是参考文献的独立对抗复核代理。请实际逐条核对所有原始条目及当前候选修正版，包括没有修正版的条目，不做抽查。只核查文献存在、作品/版本身份、输出元数据和文末参考文献格式；不评价正文论断、正文写法或应引用哪篇文献。
>
> 自行打开出版者/机构/可信数据库记录和目标规范，逐项检查作者、题名、载体、日期、卷期、页码/文章编号、文献类型与 DOI/URL 是否属于同一作品；按指定格式检查最终字符、标点、顺序与必备字段。样式引擎运行成功不是规范符合性的证据。没有 DOI、合法省略的字段、规范允许的等价格式不算错误。
>
> 给每条 ID 返回：作品真实性、元数据、格式分别为 verified / unresolved / not_applicable，verdict 为 pass / fix / unresolved / needs_user / duplicate，实际来源及定位、问题和建议的修正依据。身份有歧义时列明候选与需确认的问题；检索失败不能写成证明不存在。读写限于提供的材料与本次审查目录，不修改候选稿或用户原件。
>
> 结果覆盖所有原始 ID 并对应当前资料包摘要；不得只返回一句“全部通过”。已交付条目出现错误或未核实字段就不能 pass。没有新证据时如实写未解决。报告你实际执行了哪些核查及访问限制。

子代理只返回问题、依据和复核结果。主代理负责修正；意见冲突时按原始证据处理，不能为了让审查通过而删掉真实字段或引入错误。修改后再次复核当前全部材料。已结束的真实审查代理可再次派发；不能只复核改动条目。

## 资料结构与放行检查

`draft.json`：

```json
{
  "schema_version": 1,
  "main_agent_id": "/root",
  "style": {
    "name": "GB/T 7714—2025",
    "selection": "user_no_requirement",
    "rules": [{"url": "https://example.org/target-rules", "locator": "本次适用条款"}]
  },
  "entries": [{
    "id": "R1", "original": "原始条目",
    "decision": "include", "candidate": "当前候选修正版",
    "evidence_status": "verified",
    "sources": [{"url": "https://example.org/work-record", "locator": "已核对字段位置"}]
  }]
}
```

这是结构示意；URL、字段及结论必须来自本次真实操作。`style.name` 使用规范名，细则另行记录；用户明确无要求时它必须是 GB/T 7714—2025。`decision` 可为 include、unresolved、needs_user、duplicate；未解决条目的 candidate 是 null，并保留原文及问题。完全重复的同版作品可给 duplicate 指定 `duplicate_of`，保存映射；主审与复审均须有核实依据、复审不能留有问题，不能只因 DOI 相同就合并题名不一致的条目。

交付 HTML 时，每行补 `candidate_html`；布局参数写入顶层 `presentation`。这两项也进入资料包和版本摘要。未解决/重复行不保留待交付的 HTML。其他文件载体也必须把实际内容及布局交给代理审查；JSON 检查不能证明外部文件与资料包相同，交付前由主代理核对冻结版本。

`review.json` 包含真实 `reviewer_agent_id`、`independent: true`、当前 `packet_sha256`、覆盖每个原始 ID 的 `rows`。每行必须明确填写三项状态和 `issues` 列表，未解决行也不能只写 ID 与结论。`issues` 只列当前仍需解决的问题；原始错误已经修复时另存 `original_issues`，保留诊断，避免把历史问题混作修正版的阻断问题。问题要有 `code` 和 `detail`；来源地址/路径与定位必须是非空字符串。include 行只有 identity、metadata、format 都 verified、verdict 为 pass、没有问题，才可放行；duplicate 行必须确认同版作品与信息一致、没有遗留问题，并对应已通过的保留条目；其他条目保持明确的未解决状态。

```sh
python3 <skill目录>/scripts/review_gate.py check --draft draft.json --review review.json
```

检查工具验证覆盖、重复 ID、主审与复审标识、版本摘要及状态一致性；**不验证 URL 内容，也不能证明 JSON 中的代理标识确实对应真实调用**。主代理仍须查验真实委派及审查操作。`complete: false` 时只能交付明确标注的已核实部分。覆盖不足、草稿修改、交付条目有阻断问题时返回失败；任何这些失败都不能被一句“复核已通过”覆盖。

如果没有真实子代理工具或来源访问能力，交付实际已有的诊断与未完成原因，不能冒充独立核验过的正确参考文献。遇到身份或证据问题，向用户索取必要材料，并继续能独立完成的条目；不无限重复没有新信息的相同检索。
