# 验证记录 / Validation

日期：2026-09-29。以下是实际执行结果，不代表任意输入都能得到正确文献表。

## 已执行

| 检查 | 结果 |
|---|---|
| Skill 入口校验 | 通过 |
| 安装目录回归测试 | 39 项通过，没有跳过 |
| 独立工具对抗审查 | 18 个 DOI 探针、15 个覆盖与版本检查探针、19 个内置格式探针符合预期 |
| 其他独立工具检查 | 自定义 CSL 分支、6 个固定资产摘要通过 |
| 真实 DOI 接口 | AlphaFold DOI 取得 Crossref 记录，Attention arXiv DOI 取得 DataCite 记录 |
| 四条参考文献用例 | 4/4 真实独立逐条复核；2 条修正版通过，2 条身份冲突待确认 |
| 安装与原交付包一致性 | 20 个核心文件逐文件 SHA-256 一致 |

实测开发环境：Python 3.9.6、Node v24.19.0。独立审查使用真实子代理，规范相关判断直接查看了 GB/T 7714—2025 的适用条款，没有把 CSL 样式当成规范本身。

已修复并独立重跑的问题包括：用访问年补造出版年、错误接口响应被当作 DOI 记录、漏审原始条目仍放行、重复项冲突未解决仍放行、无格式要求时选错标准、HTML/布局变化没有触发重新复核、丢失档案页码、报告形态误判、期刊估计年方括号遗漏，以及版本标签重复。

## 未验证部分

- 完整 APA、IEEE 规范正文：只验证了工具运行及特定字段、HTML、布局输出。
- 全部 GB/T 类型、语言组合与机构模板：没有穷举。
- 用户真实论文及其最终 Word/PDF 排版：四条用例是开发材料，交付纯文本。
- 所有 agent 宿主：目录采用公开 Agent Skills 格式，完整执行仍取决于宿主是否提供联网查证和真实子代理能力。
- 每个格式询问对话分支：用例测试了明确无格式要求的分支，未把其他分支记作已运行。

The checks above cover the recorded inputs and frozen implementation. They do not certify arbitrary references, all formatting rules, or every agent host. Real source verification and real independent subagent review remain mandatory for each task.

## 发布内容

[verified-core-sha256.json](verified-core-sha256.json) 记录独立审查所对应的 20 个核心文件摘要。公开仓库保留这些核心文件原样，另外添加安装说明、许可证说明和自动测试配置。

GitHub Actions 的结果以具体提交的运行记录为准；本页的开发记录不代替 CI 实际结果。
