# Third-party sources and licenses

The bundled files are pinned snapshots. Their exact source URLs, upstream revisions, and SHA-256 hashes are recorded in `manifest.json`. They are supplied as formatting implementations; they do not replace the applicable reference standard.

## citeproc-js

`vendor/citeproc_commonjs.js` is the unmodified source from the `citeproc` npm package, version **2.4.63**. Its internal processor version is reported separately at runtime.

Copyright 2009–2019 Frank Bennett. Upstream offers CPAL-1.0 or AGPL-3.0-or-later; this bundle uses **AGPL-3.0-or-later**. The upstream notice is retained in `vendor/LICENSE-citeproc.txt`, and the full license is supplied in `vendor/AGPL-3.0.txt`. The formatter wrapper in `../scripts/format_bibliography.cjs` is also supplied under AGPL-3.0-or-later, as marked in its source.

Source archive: <https://registry.npmjs.org/citeproc/-/citeproc-2.4.63.tgz>. Upstream project: <https://github.com/Juris-M/citeproc-js>.

## CSL styles and locales

The style and locale sources are pinned snapshots from the Citation Style Language project. APA, IEEE, and both locales are unmodified. The GB/T style has the local changes described in `styles/gbt2025-patches.md`:

- `styles/gbt2025-numeric.csl`: derived from China National Standard GB/T 7714-2025 (numeric, 中文), originally authored by Zeping Lee; locally corrected for reference-guard.
- `styles/apa7.csl`: APA Style 7th edition.
- `styles/ieee.csl`: IEEE Reference Guide (version recorded in the file's title).
- `locales/locales-zh-CN.xml` and `locales/locales-en-US.xml`: Chinese and English locale data.

They are licensed under **Creative Commons Attribution-ShareAlike 3.0**. Author, contributor, translator, and license notices remain in each file's `<info>` section. Exact commits and source links are in `manifest.json`.

Projects: <https://github.com/citation-style-language/styles> and <https://github.com/citation-style-language/locales>. License: <https://creativecommons.org/licenses/by-sa/3.0/>.

No copy of GB/T 7714—2025 or any publisher's reference manual is redistributed with this skill. Normative source links are in `../references/formatting.md`.
