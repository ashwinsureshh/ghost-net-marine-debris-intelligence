# GFW vessel-data integration

Fetch on the workstation with `GFW_API_TOKEN` in the local `.env`:

```powershell
py -3.11 scripts/fetch_gfw.py --region gulf_of_honduras
```

The default query covers the configured region plus a 100 km spatial buffer
and seven days on either side of the run window. Seven-day report chunks run
sequentially and are cached for resumption under `data/gfw/.parts/`.
The final `data/gfw/<region>.json` is replaced atomically only after all chunks
succeed. A different existing query requires `--overwrite` or another output
directory. Never commit these local files or credentials.

`export_run.py` loads only the named region cache and requires coverage of the
run's buffered time window. A missing, legacy unscoped, or short-window cache
degrades explicitly with `--allow-degraded`; it cannot silently supply another
region's data. Existing explicit-path legacy fixtures remain readable.

## What these records mean

The [GFW 4Wings report endpoint](https://globalfishingwatch.org/our-apis/documentation/docs/v3/4wings/report)
provides hourly SAR counts at 0.01-degree grid-cell centres. These are **grid
observations**, not individual exact-position SAR returns or raw AIS tracks.
Each record retains its detection count and the resolved dataset identifier.
Stable IDs derive from the reported bin and identity, not request order.

Matched and unmatched observations are requested separately using GFW's
`matched` filter. `ais_matched` preserves that classification independently of
the MMSI: [GFW documents matched records without vessel details](https://api-doc.globalfishingwatch.org/our-apis/documentation/docs/examples/report/report-example9).
A missing MMSI alone does not make such a record dark. The existing local
SAR/AIS matcher remains available for actual AIS-position inputs.

Use `date` as the hourly observation time. A live response demonstrated that
`entryTimestamp` and `exitTimestamp` repeat a wider reporting interval across
different hourly records. Coordinates and times remain quantized; the scoring
formula operates on grid observations and does not expand aggregated counts
into invented vessel positions. Evidence and export notes carry this limitation.

No observations does not establish satellite coverage or vessel absence.
Unmatched AIS is an investigation signal, not proof of illegality or source
attribution. A fixed spatial buffer may miss contacts beyond its boundary.

## Validation and limits

On 2026-09-10, an authenticated query for the Honduras region (no spatial
buffer), 2018-02-01 through 2018-02-08 exclusive, returned 27 hourly grid
observations: 11 unmatched and 16 matched. This verifies acquisition and parsing,
not the detector's accuracy, vessel-match accuracy, or full demo coverage.
The smoke cache lives only in the isolated GFW worktree.

HTTP failures never become empty caches. Requests have bounded timeouts,
bounded 429/502/503 retries, response-size limits and no bearer-token redirects.
Pagination is rejected rather than silently truncated; reduce the chunk size.
For a gateway timeout, retry smaller chunks rather than downloading an
unidentified last report belonging to a concurrent session.

Remaining work after this integration: acquire full region/window caches,
re-export and assess FR-5 against independent reference evidence. The successful
smoke request alone does not close either partial PRD acceptance criterion.
