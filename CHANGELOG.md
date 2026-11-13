# Changelog

## 2.0.0 · 2026-11-14

### Added

- Offline workflow CLI: runtime/asset doctor, original-reference initialization, metadata comparison and frozen release export.
- Input inventory with original ID/text fingerprint and count; explicit bibliography ordering with input/output positions.
- Batch DOI file input, request deduplication, optional contact identification, bounded network retries, registry fallback, opt-in positive cache and offline mode.
- Registry field diagnostics and duplicate DOI candidate groups, without automatic work selection, date selection or merging.
- External artifact path containment and byte-hash verification; exact text, evidence JSON, report and release manifest exports.
- Adversarial regression coverage and a Python/Node CI matrix; clearly labeled synthetic examples.

### Fixed

- Review hashes now bind the entire draft, including decisions, evidence, duplicate mappings, source inventory and order. Blind packets still withhold the main agent's judgments.
- Malformed review/draft objects, whitespace agent IDs, unsafe source URLs, impossible dates, invalid name fields and historical findings fail explicitly.
- Truncated HTTP responses participate in retries; a partial registry outage is never reported as universal absence.
- Export validates and builds content before creating its destination, refuses existing release directories and explicitly labels partial releases.
- CSL input accepts UTF-8 BOM; formatter output refuses overwriting an existing file.

### Migration

Draft schemas 1/2 are readable. New drafts and formatter output use schema 2. Old packet/review digests are intentionally invalid: regenerate the packet and obtain real independent review of the full current draft. Keep initialized inventory metadata intact. Bundled styles, locales and citeproc-js are unchanged.

## Initial publication

Original source verification, three candidate formats, mandatory independent per-entry review, structural gate, 39 regression tests and licensing documentation.
