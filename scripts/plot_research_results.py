"""Rebuild report figures from measured JSON; no fitted or invented values."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "svg.fonttype": "none"})
BLUE, AMBER = "#29476b", "#ad742e"


def save(fig, name):
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


drift = json.loads((ROOT / "eval/drift_temporal.json").read_text("utf-8"))
horizons = [int(h) for h in drift["horizons_hours"]]
fig, ax = plt.subplots(figsize=(7.5, 5.2))
fig.subplots_adjust(bottom=.29)
for key, label, color, style in (("mean", "Mean-field baseline", BLUE, "-o"),
                                  ("temporal", "Interpolated currents", AMBER, "--s")):
    values = [drift["horizons_hours"][str(h)][key]["mean_endpoint_error_km"] for h in horizons]
    ax.plot(horizons, values, style, color=color, label=label, linewidth=1.8, markersize=5)
ax.set(title="Time interpolation did not consistently improve drift accuracy",
       xlabel="Prediction horizon (hours)", ylabel="Mean endpoint error (km)", ylim=(0, 90))
ax.set_xticks(horizons, [f"{h}\nn={drift['horizons_hours'][str(h)]['mean']['n_tracks']}"
                         for h in horizons])
ax.grid(axis="y", color="#e5e7eb")
ax.legend(frameon=False)
fig.text(.08, .025, "Paired arms within each horizon; track sets differ across horizons.\n"
                   "2014 drogued buoys; approximately six-day currents. Not demo validation.",
         fontsize=9, color="#526071")
save(fig, "drift-temporal-comparison")

sensitivity = json.loads((ROOT / "eval/priority_sensitivity.json").read_text("utf-8"))["runs"]
fig, ax = plt.subplots(figsize=(7.5, 4.6))
fig.subplots_adjust(bottom=.25)
for offset, key, label, color in ((-.18, "top1_changed", "First choice changes", BLUE),
                                (.18, "dispatch_set_changed",
                                 "Dispatch membership changes", AMBER)):
    values = [r["summary"][key] for r in sensitivity]
    bars = ax.barh([i+offset for i in range(3)], values, height=.32, color=color, label=label)
    ax.bar_label(bars, padding=4)
ax.set_yticks(range(3), ["Honduras", "Gonave", "Puducherry"])
ax.invert_yaxis()
ax.set(xlim=(0, 24), xlabel="Variants changing the recommendation (out of 24)",
       title="Priority weights can change the dispatch recommendation")
ax.legend(frameon=False, loc="lower right")
fig.text(.12, .025, "One weight at a time: ±10%, ±25%, ±50%; three-site capacity.\n"
                   "Fixed evidence; these counts are not probabilities of incorrect decisions.",
         fontsize=9, color="#526071")
save(fig, "priority-sensitivity")
