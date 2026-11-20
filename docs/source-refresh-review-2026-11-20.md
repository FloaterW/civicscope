# Source candidate review — November 20, 2026

The November 16 CMHC candidate is numerically equivalent to the published data.
The November 16 transit candidate remains on hold. No packaged data, production
database, or source-verification timestamp is changed by this code/workflow release.

The candidate files have been preserved locally in
`output/recheck-2026-11-20/refresh-candidates/` before the reported December 16 Actions
artifact expiry. Machine-readable independent review results are in
`output/workflow-implementation-2026-11-20/source-candidate-review.json`.
These local files survive remote artifact expiry; they are not a durable remote
backup. The content hashes below identify the reviewed inputs.

## CMHC: accept numerical equivalence; keep published artifacts

- All 200 municipality/year records and 8,198 tract/year records have identical keys
  and cells, including source labels, zeros and nulls. No records were added or removed.
- The municipal seed differs only in `metadata.fetched_at` (November 4 → November 16).
- The tract CSV has identical headers, rows and ordering. Its byte hash changes only
  because the published file uses LF and the candidate uses CRLF (8,199 line endings).
- There are 4,484 zero-valued tract starts, 3,148 zero-valued tract completions, and
  2,488 missing completion cells in both files. Missing cells remain missing; this
  review does not substitute zero or invent unreported years.
- Starts retain 8,043 `official` and 155 `estimated_parent` source labels. Completions
  retain 5,596 `official`, 114 `estimated_parent`, and 2,488 blank labels. Thus the
  unchanged candidate does not remove the previously disclosed parent-tract estimates.
- Municipal coverage still has 200/200 records and is nonpartial; completions retain
  the documented 92% field coverage. A successful source fetch does not fill official
  reporting gaps.

The numerical review is complete. A separate data-verification change may record the
November 16 check and candidate hashes while binding verification to the existing
published hashes. There is no reason to replace audited files merely for a timestamp
or newline change. Do not copy the candidate's entire refresh manifest, which contains
older metadata for other sources.

## Transit: reject promotion of this candidate

Artifact hashes, full tract identity coverage, score arithmetic, route coordinates and
declared agency membership passed the independent offline checks. Those checks do not
prove the original GTFS computation or operating-date validity.

| Observation | Published | November 16 candidate |
| --- | ---: | ---: |
| Tract score rows | 1,159 | 1,334 |
| Route features | 381 | 450 |
| TTC routes | 227 | 230 |
| MiWay routes | 72 | 67 |
| GO Transit routes | 43 | 45 |
| Brampton Transit routes | 0 | 70 |
| Durham Region Transit routes | 39 | 38 |

The candidate includes all five configured agencies, 175 added tract rows, and 128
zero-route tracts. Among the previously present tracts, 551 route counts and 999 scores
change. **531 scores change while their route counts do not.** The candidate uses
all 1,334 tracts for normalization (10th/90th percentiles 1/21); the published snapshot
used the 1,159 nonzero tract rows (2/21). Both still claim `routes-within-800m-v1`.
The change therefore cannot be described as merely adding Brampton service.

The retained candidate contains only derived CSV/GeoJSON/manifest files. None of the
five exact GTFS input ZIPs is present, although their hashes are recorded. Redownloading
current feeds cannot reconstruct those historical inputs. The importer also uses all
feed trips without evaluating `calendar.txt` or `calendar_dates.txt`; retrieval on
November 16 does not establish service on November 16. The official
[GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/#calendartxt)
defines service dates and exceptions through those files.

For these reasons, do not promote this transit candidate or mark transit checked.
The existing partial snapshot and its warning remain. Future candidates now retain
the exact ZIPs and identify the all-tract calculation as
`routes-within-800m-all-tracts-v2`, with explicit normalization and service-calendar
policy fields. This improves reproducibility without presenting a methodological
change as an unchanged v1 refresh. Before a future data release, independently
recompute from those exact inputs, review agency service calendars, decide whether
the intended product is an all-feed route inventory or service for a defined date,
and update user-facing methodology if the new interpretation is adopted.

## Census: no new verification claim

The supplied local review bundle contains CMHC and transit candidates only; no Census
candidate was independently reviewed in this pass. The recorded November 16 refresh
workflow succeeded, so absence from this local bundle is not evidence of a failed
Census run. The prior reviewed Census data and verification date stay in place.
Bounded retries and sanitized failure artifacts are now implemented for future
transient upstream failures without publishing partial results. Parsing,
FLAG/suppression handling and complete-geography gates remain mandatory.

## Reviewed SHA-256 digests

| Candidate file | SHA-256 |
| --- | --- |
| CMHC `cmhc_seed.json` | `6d9cc24aa212b0a17e9714b9a464ae717ef9d4b2a720bc0c039cb20d4a9ac17e` |
| CMHC `cmhc_ct_metrics.csv` | `4bff7eab279c03e0162a05c31303921f16e6903b05fce3dec1be0eb59e63869b` |
| CMHC `refresh_manifest.json` | `d2a00d28252471d02d08bccefe28dc39ec6b44bfa8b10c7e1cfd87bedd94284d` |
| Transit `transit_scores.csv` | `219edf9bab08b05869a96a45e7a1d27591dace1165bfaa2e630b958cf118b89b` |
| Transit `transit_routes.geojson` | `ce72103e3823422236378238488b0698b9c40fbd73af6fe6ad9c625875b8cabc` |
| Transit `transit_manifest.json` | `4e0bf4d70be2d7432bb90f2b30d0b8276a42863ff76eac2e9ab1ce2c7c5ace87` |
| Transit `refresh_manifest.json` | `ed1f31da079ba55e8941f0e6187ee7b6b3b890ccbce005fb50e52a68f468c973` |

All five payload hashes match the candidate refresh manifests. The two refresh
manifest digests are independently recorded above; neither is self-authenticating.
