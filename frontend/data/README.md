# Public TRREB resale archive

The owner explicitly authorized publishing these aggregate figures in the public
GitHub repository on September 25, 2026. This is not a listing-level dataset.
Source: Toronto Regional Real Estate Board (TRREB), Market Watch, all home types.
The project's MIT license covers application code; it is not a grant of rights
in TRREB's third-party source reports. Preserve the publisher attribution.

`trreb-resale-2020-2025.json` contains exactly 1,950 observations: 25 municipal
reporting contexts × (72 months + six actual year-end tables). It is exported
without recalculation from approved release
`253fbe7ac0c9668b08d60cc9034aaa9cf81cbc992273fe736e056c5f6148329d`.
Each row preserves the report URL, PDF fingerprint, page, warnings and
geography/vintage disclosures. Annual medians are not monthly averages.

Original PDFs, private manifests, staging databases and quarterly rental tables
remain outside Git. Reporting-area matches are not certified Census polygon
equivalence; no census-tract allocation or map colouring is supported.

Regenerate through `backend/etl/export_trreb_web.py` with the separately approved
release SHA. Output is exclusively created. Review changes, update the file hash
in the server reader, and run the archive and browser tests before deployment.
These are archived 2020–2025 figures, not current market quotes or an automatically
refreshed dataset. Public repository history cannot be withdrawn by a UI rollback.
