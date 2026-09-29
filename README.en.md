# reference-guard

[中文](README.md) · [Skill instructions](skills/reference-guard/SKILL.md) · [Validation](docs/VALIDATION.md)

An Agent Skill for preventing fabricated references and correcting bibliographic metadata and reference-list formatting. Use it when drafting a bibliography, checking references in an existing paper, or delivering a corrected reference list.

## Install

Ask a skill-capable agent to install the complete directory at:

<https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard>

With Node.js/npm and the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add yunnre060214-sudo/reference-guard --skill reference-guard
```

Select your agent when prompted. Add `-g` for a user-wide installation. Supported agents and installation locations are determined by the CLI's current support.

For manual installation, download or clone this repository and copy the **entire** `skills/reference-guard/` directory into your agent's skills directory. Reload skills as required by your agent. Copying only `SKILL.md` is insufficient.

Codex users can ask:

```text
$skill-installer https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard
```

Then invoke `$reference-guard`. Other agents use their own invocation mechanism.

## Contract

- Retrieve actual source records before generating entries; match the work, version, and output fields.
- Ask when the reference format is unspecified. Use **GB/T 7714—2025** only after the user explicitly says they have no format requirement.
- Deliver problem descriptions, verified corrected references, and unresolved original entries.
- Create a **real adversarial subagent** to independently review every original and proposed entry, including unresolved entries. Sampling or roleplay does not fulfill this requirement.
- Re-review the complete current version after repairs; deliver the reviewed text unchanged.
- A failed search is not proof that a work does not exist. Ask the user when conflicting identities cannot be resolved; do not silently replace the work.

The scope is bibliographic authenticity, metadata, and final reference-list formatting. Paper prose, citation strategy, claim support, in-text numbering, and publication-version recommendations belong to the writing workflow.

## Requirements and verification

Full execution requires source access, access to the applicable formatting rules, and actual subagent tools. Helpers use Python 3 and Node.js. The formatter and pinned CSL resources are bundled; no separate citeproc package is required.

The included GB/T, APA 7, and IEEE styles produce candidates, not a correctness certificate. Unavailable evidence or review capabilities must be reported as incomplete.

Development validation included 39 regression tests, an independent adversarial tool review, and independent review of all four entries in a live-source test case. See [coverage and limits](docs/VALIDATION.md). Full APA/IEEE normative coverage and final Word/PDF rendering were not certified.

## License

Original instructions, tools, and tests: **AGPL-3.0-or-later**. The bundled citeproc-js source uses AGPL-3.0-or-later; CSL styles and locales retain **CC-BY-SA-3.0** and attribution.

See [LICENSE](LICENSE), [skill licensing](skills/reference-guard/LICENSE.md), and [third-party notices](skills/reference-guard/assets/THIRD_PARTY_NOTICES.md). Reference standards and publisher manuals are not redistributed.
