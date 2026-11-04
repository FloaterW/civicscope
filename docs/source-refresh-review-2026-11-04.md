# Source refresh review — November 4, 2026

Reviewed the successful [November 2 workflow run](https://github.com/FloaterW/civicscope/actions/runs/41488920149), built from `f6ac83a`. No candidate observations were promoted. Census qualifies for a manually reviewed unchanged-data check dated November 2; the changed transit candidate remains unpublished. The existing November 4 CMHC verification remains unchanged.

Both downloaded ZIPs matched GitHub's archive digests, and every extracted artifact matched its refresh-manifest hash:

| Candidate | Artifact ID | ZIP SHA-256 |
| --- | --- | --- |
| Census | 13162703423 | `c6bc984cb1bae00e414a45259c84e63d8ace5326e10e38281d6bbe4cecc03287` |
| Transit | 13163371288 | `15633bf1fb5efc0f5d2f2a2f525d135c38b2731797e40346af0a8295e7132927` |

## Census: unchanged observations, different retrieval provenance

All **1,359 geography records, including every metric and boundary**, are identical. `statcan_ct_metrics.csv` is byte-identical, SHA-256 `e444dc58fe929bdf147dd64972944eb070e3e572be0172d8c5a2ad8d6b651a7b`.

Only `demo_seed.json` metadata differs. The packaged snapshot describes the audited Statistics Canada bulk CSVs; the candidate describes its independent official SDMX DF_CSD/DF_CT retrieval. The importer actually uses those SDMX endpoints. The candidate's check completed at **2026-11-02T17:15:56.758296+00:00**.

The [Census job log](https://github.com/FloaterW/civicscope/actions/runs/41488920149/job/125426456977) confirms 25 municipal rows updated, all 34 tract batches fetched, and 1,334 tract rows validated without missing, duplicate or unexpected geoids. The importer files are unchanged from the run's commit. `refresh_candidate` invokes `load_census --update-seed` and `load_tract_census --generate-csv --update-seed`, using the official [DF_CSD](https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/data/STC_CP,DF_CSD) and [DF_CT](https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/data/STC_CP,DF_CT) endpoints. Both request CSV with `detail=full`, require observation flags, and preserve suppressed values through `observation_value`. This verifies the metric retrieval; existing 2021 boundaries were retained, not independently refreshed.

The strict `record_source_check` helper correctly rejects the metadata-different candidate and remains unchanged. An independent manual review confirmed the exact observation equality and both artifact hashes; its evidence is retained in the main checkout's ignored `out/census-reviewed-source-check-20261104.json`. The approved manifest-only update records the November 2 source check against the published artifact hashes, links the reviewed candidate/workflow, and preserves the original bulk-source provenance. It does not replace any Census observations or claim a November 4 retrieval.

## Transit: substantive changes requiring reconciliation

The candidate snapshot is **2026-11-02T17:13:36.571445+00:00**, compared with June 24. Feed retrieval times and five source ZIP hashes are recorded, but the original ZIPs are absent from the workflow artifacts.

| Agency | Published overlay features | Candidate |
| --- | ---: | ---: |
| TTC | 227 | 230 |
| MiWay | 72 | 67 |
| GO Transit | 43 | 45 |
| Brampton Transit | 0 | 70 |
| Durham Region Transit | 39 | 38 |
| **Total** | **381** | **450** |

- Candidate scores cover all **1,334 expected tracts** without duplicates or unknown geoids, compared with 1,159 explicit rows previously. Of 175 added rows, 122 explicitly record zero routes. All overlay geometries passed coordinate/shape checks; agency/route labels are unique.
- **606 route counts change**: 437 increase and 169 decrease. All 122 Brampton tracts gain route coverage when its agency is included. These are coverage/vintage changes, not evidence that those services were newly introduced.
- **1,045 scores change**, including **529 with unchanged route counts**. The old CSV normalized over 1,159 nonzero-route tracts (10th/90th percentiles: 2/21); the candidate includes all 1,334 tracts (1/21). Both sets of scores exactly reproduce their respective distributions, but retain the same `routes-within-800m-v1` label.
- **1,135 tract metric rows change overall**. The overlay adds 83 route labels, removes 14, and changes geometry for 367 shared labels.

Before promotion:

1. Preserve the exact source ZIPs and independently replay the spatial computation. Current artifacts prove hashes and internal consistency, not the underlying stop-to-tract joins.
2. Check feed validity and service calendars. The importer includes all trips without evaluating `calendar.txt`/`calendar_dates.txt`; retrieval date alone does not establish which services operate on that date.
3. Review the normalization-universe change and its method/version disclosure. Preserve route counts alongside relative scores; avoid interpreting score changes alone as service changes.
4. Describe coverage as the five configured agencies. "Complete" does not mean every GTA operator: [YRT](https://www.yrt.ca/en/about-us/open-data.aspx) and [Burlington Transit](https://opendata.burlington.ca/gtfs-rt/) are examples of official feeds outside that configuration. No agencies were added in this review.
5. Review the data diff and a scoped database update before publishing; keep the June snapshot and its dates until that review is complete.

## Portable artifact hashes

The candidate transit CSV uses CRLF. Its raw SHA-256 is `be5e45ab703f35f0d8b9806acf31c94de70a10614294bfde453ce28b541c31a7`; LF checkout changes it to `ae2ddd64b4e18abae57e131fa0d122bdd8546ce9dbc315a6eb37949b54b66ac5`. Copying the candidate directly into Git would therefore invalidate both manifests' CSV hashes.

The exporter now writes CSV and transit-manifest JSON with explicit LF before hashing. An offline regression runs the export, simulates LF checkout, and checks candidate validation plus application provenance verification. This changes future serialization only; packaged observations, method labels, agency lists and dates remain untouched.

Detailed reports and untouched downloaded artifacts are retained under `out/source-review-20261104/` in the backend-lock-consistency review worktree: `source-review-summary.json`, `census-diff.json`, `transit-analysis.json`, and `transit-metric-changes.json`.
