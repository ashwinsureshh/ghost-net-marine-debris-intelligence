# Drift comparison protocol — September 22, 2026

Freeze this method before reading new outcomes. Do not promote the experimental
field into the demo merely because one summary metric improves.

- Same 2014-04-01..2014-09-30 Gulf of Honduras drogued-buoy sample selection
  as the historical study; preserve the 2018 demo distinction.
- Compare historical time-mean currents with linear temporal interpolation of
  the downloaded snapshots. These are sampled approximately every six days,
  not newly acquired daily observations. Reject extrapolation and gaps >7 days.
- Same seed, ensemble size, integration step, initial position and observations
  for both arms. Retain baseline output and enumerate any paired exclusions.
- Report 24/48/72/96/120/168-hour results on tracks with an observed fix at that
  horizon. Report sample counts per horizon; never imply all 19 tracks last a week.
- Report mean positional error, endpoint error, envelope coverage and envelope
  radius. An enormous envelope is not a useful success even if coverage improves.
- Any uncertainty calibration must split by buoy ID before fitting, never by
  observations from the same buoy. Fit on calibration buoys only, freeze, then
  evaluate the other buoys. These historical data were inspected previously;
  this is internal validation, not a new independent external test.
- Missing temporal data must fail or be recorded explicitly; never silently
  switch that arm back to the mean field.
- Backward RK4 intermediate timestamps must move backward too. The existing
  constant-field default masked that bug; add an analytic reversal regression.

The time-varying loader is opt-in. Production pipeline configuration and served
artifacts stay on their existing baseline until measured review justifies a change.
