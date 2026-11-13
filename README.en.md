# reference-guard

[中文](README.md) · [Agent instructions](skills/reference-guard/SKILL.md) · [Workflow and contracts](skills/reference-guard/references/workflow.md) · [Validation](docs/VALIDATION.md) · [Changes](CHANGELOG.md)

**2.0.0** provides a bibliography workflow from original references and source evidence to metadata comparison, candidate formatting, independent review and frozen delivery. Verify the same work and publication version before accepting its fields.

## Capabilities

- Preserve every original, stable ID, input fingerprint and bibliography order. Detect missing entries and changed originals after initialization.
- Retrieve Crossref/DataCite records in batches, with bounded retries, provider fallback, opt-in positive caching and offline cache reads. Access failure is distinct from a registry returning no record.
- Compare supplied CSL-JSON with registry metadata. Flag title, author, container, volume, issue, page, article-number and date differences. Shared DOIs identify duplicate candidates, never automatic merges.
- Generate candidates with bundled GB/T 7714—2025, APA 7, IEEE or a supplied independent CSL. Preserve text, HTML, layout and input/output ID mappings.
- Require a real independent subagent to review every original and candidate, including unresolved entries. Seal all draft fields, including decisions, evidence, duplicate mappings and ordering; check external artifact bytes too.
- Export exact reviewed text, a problem report, full draft/review evidence and file hashes. Partial releases are explicit and retain unresolved originals.

Registry availability, similarity scores, renderer success and structural checks do not authenticate a citation or prove that an agent was created. A failed search does not establish nonexistence. The scope is the reference list; claim support, in-text numbering and decisions about which version to cite belong to the writing workflow.

## Installation

Ask an Agent Skills-compatible agent:

```text
Install reference-guard from https://github.com/yunnre060214-sudo/reference-guard/tree/main/skills/reference-guard, preserving the entire folder including references, scripts, assets, agents and licenses. Run doctor and confirm that the host can access sources and create a real independent subagent.
```

Or use the [skills CLI](https://github.com/vercel-labs/skills):

```sh
npx skills add yunnre060214-sudo/reference-guard --skill reference-guard
```

Add `-g` for global installation where supported. Agent support and installation paths are determined by that installer. For manual installation, copy the entire `skills/reference-guard/` folder into your host's skills directory and reload it using that host's procedure.

## Usage

```text
Use reference-guard to check these references against my institution's template. Deliver the corrected list, source-backed problem report and unresolved originals after real independent per-entry review.
```

Use an explicitly supplied format immediately. If unspecified, ask while continuing source verification; choose GB/T 7714—2025 only when the user explicitly has no format requirement. Missing source access, verifiable rules or real delegation must be reported as incomplete work.

## Command-line tools

Requires Python 3.10+ and Node.js 20+. Python uses only its standard library; citeproc-js is bundled. From the repository root:

```sh
python3 skills/reference-guard/scripts/reference_guard.py doctor
python3 skills/reference-guard/scripts/reference_guard.py --version
```

The example files contain **synthetic, unverified references** and demonstrate mechanics only:

```sh
python3 skills/reference-guard/scripts/reference_guard.py init \
  --input examples/originals.synthetic.json --main-agent-id YOUR_ACTUAL_AGENT_ID \
  --style 'APA 7' --output draft.json
node skills/reference-guard/scripts/format_bibliography.cjs \
  --input examples/items.synthetic.json --style apa7 --output rendered.json
```

Retrieve and compare actual metadata:

```sh
python3 skills/reference-guard/scripts/doi_metadata.py 10.1038/s41586-021-03819-2
python3 skills/reference-guard/scripts/doi_metadata.py --input dois.txt \
  --output metadata.json --cache-dir .doi-cache --retries 2
python3 skills/reference-guard/scripts/reference_guard.py audit \
  --items items.json --metadata metadata.json --output audit.json
```

After source verification, candidate preparation and real independent review:

```sh
python3 skills/reference-guard/scripts/review_gate.py packet --draft draft.json --output packet.json
python3 skills/reference-guard/scripts/review_gate.py check --draft draft.json --review review.json
python3 skills/reference-guard/scripts/reference_guard.py export \
  --draft draft.json --review review.json --output-dir release
```

Exports contain `bibliography.txt`, `report.md`, `release.json` and `manifest.json`. Pending entries block export unless the verified subset is explicitly released with `--allow-partial`. External rich documents need visual review and artifact hashes; text export does not preserve italics or hanging indents. The output directory must be new.

See the [workflow](skills/reference-guard/references/workflow.md) for parameters, exit codes, cache limits and data contracts. All commands except DOI retrieval can run offline; doctor cannot test source access or real delegation.

## Validation and migration

```sh
python3 -m unittest discover -s skills/reference-guard/scripts/tests -v
```

Node must be on PATH; renderer tests also accept `REFERENCE_GUARD_TEST_NODE`. GitHub Actions runs offline regressions and asset checks across Python/Node combinations. Consult the actual commit's CI and the [validation record](docs/VALIDATION.md), which separates historical claims from current tests and lists limitations.

Draft schema versions 1 and 2 are accepted; new drafts and renderer output use version 2. **Old review hashes cannot be reused.** Regenerate the packet and obtain a real full review after upgrading. Preserve initialized input inventory metadata.

## License

Original instructions, tools and tests: AGPL-3.0-or-later. Bundled citeproc-js is distributed under AGPL-3.0-or-later; CSL styles/locales retain CC-BY-SA-3.0 and their authors' attribution. See [LICENSE](LICENSE), [skill licensing](skills/reference-guard/LICENSE.md) and [third-party notices](skills/reference-guard/assets/THIRD_PARTY_NOTICES.md). Standards and publisher manuals are not redistributed.
