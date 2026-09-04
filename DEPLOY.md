# Deploying the operator console

The console is a course deliverable (PRD §9.1), so it has to live at a URL an
evaluator can open. This file is the operational half of that decision: what
gets deployed, where, and what to do when the free tier misbehaves.

## What is deployed, and what deliberately is not

| Deployed | Not deployed |
|---|---|
| FastAPI server (`src/ghostnet/webapp/`) | MARIDA (~5.5 GB) |
| Built React frontend | Raw Sentinel-2 tiles |
| Precomputed run artefacts (`webapp_data/*.run.json`) | Any imagery or band arrays |
| Measured results (all of `eval/`) | Model checkpoints (`detector_v1.pt`, the holdout experiment) |

`COPY eval/ ./eval/` takes the whole directory, which matters more than it used
to: the metrics strip now reads six artefacts, not one — the ablation, both
detector arms, the FR-2.2 headline pair and both geographic-holdout arms.
`python -m ghostnet.provenance` is the check that every number served still
traces to one of them, and it runs in CI.

**The data cannot be deployed** — that constraint shapes the whole design and is
not a shortcut. PRD §9.1 puts tile ingestion, detection, verification and drift
on the workstation, which exports one JSON artefact per region/window. The
server serves those and recomputes only prioritisation (FR-6.1/6.2) live, plus
FR-6.3 rationales and the FR-6.4 approval. That is genuine server-side work in
response to operator input, not a static page behind a URL.

The practical consequence: `requirements-deploy.txt` is a strict subset of the
development install. No rasterio/GDAL, no geopandas, no netCDF4, no xarray.
**Measured 2026-09-04 on a clean build: 659 MB, about a minute** (`docker images
ghostnet-console`). Installing the geospatial stack would roughly double both
for code that never runs there.

## Host

**Render, free web service, Docker runtime.** Chosen because it deploys a
Dockerfile straight from a private GitHub repo with no card on file, and this
project has a two-toolchain build (npm for the frontend, pip for the server)
that a language-native runtime handles awkwardly. `render.yaml` is a blueprint,
so the service is defined in the repo rather than clicked together in a
dashboard.

Its cost, stated plainly: **a free instance spins down after ~15 minutes idle
and takes roughly a minute to wake.** PRD §9.1 anticipates exactly this and
requires the offline export as the viva fallback — see below. The console's own
fetch error already tells an operator the host may be waking rather than showing
a bare failure.

### One-time setup

1. Push `main` (the blueprint has to be on the branch Render reads).
2. Render dashboard → **New** → **Blueprint** → connect the GitHub account →
   pick `ghost-net-marine-debris-intelligence`.
3. Render reads `render.yaml` and offers one service,
   `ghostnet-operator-console`. It will prompt for the one secret the blueprint
   declares but does not carry:
   - `ANTHROPIC_API_KEY` — optional. With it, FR-6.3 dispatch rationales are
     written by Claude server-side. Without it the app falls back to its
     deterministic template, reports `rationale_source: "template"` from
     `/api/meta`, and the UI labels each rationale accordingly. It does not
     fail, and the plan itself is unaffected — the model only explains it.
4. Apply. First build takes a few minutes; subsequent ones are faster.

`autoDeployTrigger: commit` means every push to `main` redeploys.

**Live since 2026-09-04:** <https://ghostnet-operator-console.onrender.com>
(service `srv-dadal02jnfac73f5bplg`, blueprint-managed, free tier). Verified on
that date: health `runs: 1`, benchmark `available: true` with both detectors and
the generalisation block, frontend serving, and the console driven end to end in
a browser.

### If verification fails right after a push — check for deploy churn first

`autoDeployTrigger: commit` cuts both ways. Every push to `main` replaces the
instance, and **while the swap is in flight Render's router has no healthy
backend**, so requests return:

```
HTTP/2 404
x-render-routing: no-server
```

That is the edge saying *no instance*, not the app 404-ing — an app 404 is JSON
(`{"detail":"Not Found"}`), this is 10 bytes of `text/plain`. Two or three
pushes in quick succession make it look like a flapping service: measured 4/10
to 9/12 success during a burst of three deploys in eight minutes, and 12/12 once
they settled.

**So before diagnosing anything else, look at Events for a deploy started in the
last few minutes** — including one pushed from the *other* machine, which is
easy to forget on a two-machine project. Wait for `Deploy live`, then re-test.

Ruled out on 2026-09-04 while chasing this, so nobody repeats the work: it is
not memory. Running this image under Render's free-tier cap
(`docker run --memory=512m`) and driving 60 requests through it, including 20
live plan recomputes, held flat at **132 MiB of 512 MiB with zero restarts and
`OOMKilled=false`**.

### Verifying a deploy

The responses below were observed against this exact image running locally on
2026-09-04, so a deploy that differs from them has gone wrong somewhere.

```bash
curl -s https://<service>.onrender.com/api/health
```

```
{"status":"ok","version":"0.1.0","artefact_schema":"1.1","runs":1}
```

`runs` must be **1**, not 0 — 0 means `webapp_data/` did not make it in and the
console will boot with an empty run picker.

```bash
curl -s https://<service>.onrender.com/api/benchmark | head -c 400
```

Three things to look for in that body, each catching a different broken deploy:

| Field | Expect | If wrong |
|---|---|---|
| `available` | `true` | `eval/marida_ablation.json` is missing; the strip reads "unavailable" |
| `detectors` | both `fdi` and `cnn` | a detector artefact did not copy; the strip may describe a CNN run with FDI numbers |
| `generalisation` | present, `f1_cost` ≈ `-0.0723` | the holdout artefacts are missing; region recall loses its within-tile qualifier |

And open `/` — if it returns the "API is running; the frontend is not built"
page, the npm stage failed and the server is up without a UI. A correct response
starts `<!doctype html>` with `class="light"` on the `<html>` element.

`GHOSTNET_DURABLE_STORAGE` is **deliberately unset**. A free instance has an
ephemeral disk, so an FR-6.4 approval may not survive a restart; the API returns
that warning with every approval. Setting the flag would silence a warning that
is true. Set it only on a host with a persistent volume.

## Publishing a new run

The deployed app serves whatever artefacts are in the image, so shipping a real
region is a commit, not a deploy step:

```bash
python scripts/export_run.py --region gulf_of_honduras --out webapp_data/
```

Run that on the workstation (it needs the local datasets), commit the resulting
`webapp_data/<run_id>.run.json`, and push. Render rebuilds and the run appears
in the console's run picker. Artefacts are a few hundred KB — small enough to
commit, which is what keeps the deploy reproducible. If one ever exceeds ~2 MB,
cut trajectory step resolution before cutting evidence or rejections.

## Running the image locally

Identical to what the host runs, which makes it the right place to reproduce a
deploy failure:

```bash
docker build -t ghostnet-console .
```

```bash
docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY ghostnet-console
```

The build smoke-imports the server and asserts that both a run artefact and the
measured results are readable inside the image, so a missing dependency or a
mis-copied directory fails the build rather than the first request. A successful
build prints it:

```
ok: 1 run(s), benchmark from eval/marida_ablation.json
```

**Pre-flight before a first deploy.** Render sets `$PORT` rather than using
8000, and a server that ignores it boots and then fails its health check for no
visible reason. Prove the image honours it *before* touching the dashboard —
this is the exact sequence run on 2026-09-04, and all of it passed:

```bash
docker run -d --name ghostnet-test -e PORT=10000 -p 10000:10000 ghostnet-console
```

```bash
curl -s http://localhost:10000/api/health && curl -s http://localhost:10000/ | head -c 40
```

Then run the same three `/api/benchmark` checks from the table above against
`localhost:10000`. Clean up with `docker rm -f ghostnet-test`. If every check
passes locally, a failed deploy is a host or blueprint problem, not an
application one — which narrows the search considerably.

## The fallback, which is not optional

Free-tier hosts sleep and venue wifi fails. Build the offline export before any
demo and carry it on disk:

```bash
cd frontend && npm run build && cd .. && python scripts/build_static_export.py
```

`static_export/index.html` opens from `file://` with no server, no Python and no
network, and carries the same run, the same rejected detections and the same
measured metrics strip. It is read-only by design: recording an approval
(FR-6.4) and live ablation need the server, and it says so rather than faking
them.

**Rebuild `frontend/dist` first.** The exporter copies the last build; a stale
`dist` silently produces a fallback that is a version behind the deploy.

## If Render's free tier changes

The Dockerfile is host-agnostic — it honours `$PORT` and defaults to 8000 — so
moving means writing a new service definition, not changing the app:

| Host | Notes |
|---|---|
| Hugging Face Spaces (Docker SDK) | Free, and sleeps far less aggressively than Render, which suits a viva. Needs `app_port: 8000` in the Space's README front-matter. |
| Koyeb | Free instance, Docker from a Git repo, no card. |
| Fly.io | Docker-native and fast, but the free allowance has narrowed — check before relying on it. |

Whichever host, the same two environment variables apply: set
`ANTHROPIC_API_KEY` if you want Claude-written rationales, and leave
`GHOSTNET_DURABLE_STORAGE` unset unless the disk actually persists.
