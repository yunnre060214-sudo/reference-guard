# reference-guard · 参考文献纠错

[English](README.en.md) · [Skill 指令](skills/reference-guard/SKILL.md) · [验证记录](docs/VALIDATION.md)

让 agent 在生成、核查或修复参考文献时遵守两个要求：**不编造文献，正确著录文献的信息与格式**。

适用于写论文时整理参考文献、核查现有文献表，以及交付修正后的文献表。采用 [Agent Skills 目录格式](https://agentskills.io/specification)。

## 安装

### 给你的 agent 一句话

把下面这段发给支持 skills 安装的 agent：

```text
请安装 https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard 中的 reference-guard skill。完整保留它的 references、scripts、assets 和许可证文件，然后确认你的运行环境能执行联网查证和真实子代理逐条复核。
```

在 Codex 中也可以直接使用：

```text
$skill-installer https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard
```

### 用命令安装

已安装 Node.js/npm 时，使用 [skills CLI](https://github.com/vercel-labs/skills)，按提示选择自己的 agent：

```bash
npx skills add yunnre060214-sudo/reference-guard --skill reference-guard
```

需要在所有项目中使用时加 `-g`。该工具支持哪些 agent、安装到哪里，以工具当时的支持列表为准。

### 手动安装

1. 下载本仓库 ZIP，或克隆仓库。
2. 把 `skills/reference-guard/` **整个目录**复制到你的 agent 的 skills 目录。
3. 按该 agent 的方式重新加载 skills，并调用 `reference-guard`。

不要只复制 `SKILL.md`；它还需要同目录内的核查协议、格式资源与辅助工具。

## 使用

```text
使用 reference-guard 核查这篇论文的参考文献，按学校提供的模板修正，并交付问题说明和修正版。
```

```text
使用 reference-guard 检查下面的文献表。没有格式要求，请交付修正后的正确参考文献。
```

在 Codex 中可用 `$reference-guard` 显式调用。其他 agent 按自己的 skill 调用方式使用。

## 固定规则

- 先取得真实来源记录，核对作品身份与实际输出字段，再生成文献条目。
- 未指定格式先询问；只有明确表示没有格式要求，才采用 **GB/T 7714—2025**。
- 同时交付问题说明、经过验证的修正后参考文献，以及仍待确认的原始条目。
- 交付前必须创建**真实对抗性子代理**，逐条独立复核全部原始条目和候选修正版，包括尚未解决的条目。
- 修正后重新复核当前完整版本；通过后冻结并原样交付。
- 检索不到不等于证明不存在；作品身份冲突仍无法消除时，向用户确认，不擅自替换或删除。

范围是文末参考文献的真实性、著录信息和格式。正文写作、如何引用、论断支持性、正文引文编号及版本推荐由论文撰写流程负责。

## 运行条件

完整执行需要 agent 能实际访问来源、读取适用的格式规范，并创建真实子代理。辅助工具需要 Python 3 与 Node.js；格式处理器和固定样式已随 skill 提供，无需另外安装 citeproc 包。

内置 GB/T 7714—2025、APA 7、IEEE 样式生成的是候选结果，仍须对照本次适用的规范独立核验。其他格式按用户提供的规范处理。缺少必要能力或证据时，skill 要求报告未完成，并只交付明确已核实的部分；脚本通过不能代替真实查证与子代理调用。

## 验证与维护

开发时已实际完成 39 项回归测试、独立对抗审查，以及四条参考文献的全量独立复核。详细覆盖和未验证部分见 [验证记录](docs/VALIDATION.md)。GitHub Actions 运行随包提供的离线回归测试。

维护者可在仓库根目录运行：

```bash
python3 -m unittest discover -s skills/reference-guard/scripts/tests -v
```

运行前让 Node.js 在命令路径中；也可以设置 `REFERENCE_GUARD_TEST_NODE` 为实际 Node 可执行文件。Python 工具使用标准库，测试数据中的合成条目不作为真实文献交付。

## 许可证

本项目原创指令、工具与测试使用 **AGPL-3.0-or-later**。随包的 citeproc-js 按 AGPL-3.0-or-later 分发；CSL 样式和 locale 保留 **CC-BY-SA-3.0** 及原作者信息。

完整条款见 [LICENSE](LICENSE)、[skill 许可证说明](skills/reference-guard/LICENSE.md)和 [第三方声明](skills/reference-guard/assets/THIRD_PARTY_NOTICES.md)。参考文献标准和出版者手册未随仓库分发。
