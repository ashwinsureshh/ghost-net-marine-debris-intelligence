# Drift uncertainty via eddy diffusivity — protocol, frozen 2026-09-29

Frozen before any outcome was computed. It answers the checklist item
"physically justified uncertainty-ensemble calibration, not just widening".

## Why

The production ensemble perturbs each member with a *constant* velocity scale
(σ = 0.25) and windage offset (σ = 0.03 m/s), so member separation grows
roughly **linearly** in time. The September 22 calibration then multiplied
the resulting radius by 2.865. That is post-hoc dilation: the multiplier is
the same at every horizon and has no physical meaning.

Dispersion by currents the field does not resolve is modelled in Lagrangian
drift practice as a random walk with horizontal eddy diffusivity K (m²/s).
Displacement variance grows as 2Kt per axis, so spread grows as **√t**. It
has one parameter, and published drifter-derived values give a physical range
to check the fitted value against.

## Method

- **Model change (opt-in):** each member takes an extra zero-mean Gaussian
  step of standard deviation √(2 K Δt) per axis after every RK4 step, drawn
  from a separate seeded stream. With K = 0 no extra draws are made, so the
  baseline is bit-identical. Existing velocity and windage perturbations are
  kept.
- **Data:** the same 2014-04-01..2014-09-30 Gulf of Honduras drogued buoys,
  segments, 7-day horizon, seed, ensemble size (64), step (6 h) and time-mean
  OSCAR field as `eval/drift_temporal.json`'s mean arm. Not the demo window.
- **Split:** the existing `ghostnet.uncertainty.split_buoys` ID-hash split
  (six calibration buoys, thirteen evaluation), identical to
  `eval/drift_calibration.json`.
- **Grid, fixed in advance:** K ∈ {0, 30, 100, 300, 1000, 3000, 10000} m²/s.
- **Selection rule, calibration buoys only:** the smallest K on the grid whose
  pooled calibration coverage (error ≤ 90th-percentile radius) is ≥ 0.90. If
  none reaches it, report that and select nothing.
- **Evaluation, held-out buoys, selected K frozen:** track-mean coverage and
  mean radius, overall and per horizon (24/48/72/96/120/168 h, tracks with a
  fix at that horizon). Compare against (a) the uncalibrated baseline and (b)
  the 2.865 radius multiplier from `eval/drift_calibration.json`, on the same
  evaluation buoys.
- **The physical test:** whether coverage is more uniform across horizons
  than under the constant multiplier, and whether the fitted K is inside the
  order of magnitude reported for drifter-derived surface diffusivity
  (roughly 10³–10⁴ m²/s at mesoscale; e.g. Zhurbas & Oh 2004; LaCasce 2008).
  A K outside that range would mean the term is absorbing mean-path error,
  not representing dispersion.

## Reporting rules

- Report width with coverage, never coverage alone.
- Mean-path error is reported too. Diffusion should not change it
  systematically; any change is ensemble sampling noise.
- Internal validation on previously inspected data, not external
  confirmation. Served runs and the production default (K = 0) are unchanged
  whatever the outcome; promotion needs separate review.
- A negative result (no K reaches 0.90, K is implausible, or uniformity does
  not improve) is reported as such.
