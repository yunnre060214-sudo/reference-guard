# Local GB/T style corrections

This file describes the changes from the upstream snapshot pinned in `../manifest.json`. The original copyright, author attribution, and CC-BY-SA-3.0 license are retained. The local style has its own ID and marks its changes in XML comments.

1. **Access date is not a publication-year estimate.** Removed the fallback from missing `issued` to the year in `accessed`. GB/T 7714—2025 7.5.4.3 allows sourced copyright/printing years and evidenced estimates; merely accessing an undated item does not supply that evidence.
2. **Known archive pages are retained.** The archive publication-information branch now appends `page` after formation date, following table 12 and 8.12.3.
3. **Evidenced approximate years retain brackets.** The date macro and periodical date branches preserve uncertainty qualifiers, including an approximate online publication date. `circa` is interpreted using the CSL approximate-date condition; it must come from evidence, not a guess made during formatting. Normative basis: GB/T 7714—2025 7.5.4.3. Input semantics: <https://docs.citationstyles.org/en/stable/specification.html#approximate-dates>.

The format wrapper also requires a verified publication form when report publisher information is present, to avoid inferring a book form merely from `publisher`. Numeric preprint/dataset versions with an existing V label are normalized before the style adds that same label. Its transformations and warnings are reported in the generated candidate JSON.

These fixes cover the reproduced defects. The skill still requires independent comparison of every final reference with the applicable standard.
