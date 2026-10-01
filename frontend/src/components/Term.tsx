import * as React from "react";

/**
 * Plain-language definitions for the technical terms the console uses.
 * Short on purpose: a tooltip that needs scrolling is a paragraph.
 */
export const GLOSSARY = {
  "PR-AUC": "Precision-recall area under the curve: how well the model ranks real debris above everything else, without choosing a cut-off. Compare with the chance score.",
  FDI: "Floating Debris Index: a spectral index from red-edge, NIR and SWIR bands that highlights floating material. The baseline detector thresholds it.",
  AIS: "Automatic Identification System: the position broadcast most large vessels transmit. Not every vessel is required to, and signals can drop.",
  SAR: "Synthetic aperture radar: satellite radar that sees vessels through cloud and at night. GFW reports it here as 0.01° hourly grid cells, not individual vessels.",
  "AIS-unmatched": "A SAR observation with no AIS broadcast matched to it. An investigation signal only: it does not mean wrongdoing.",
  OSCAR: "NOAA Ocean Surface Current Analyses Real-time: the ocean-current field the drift ensemble is advected through.",
  "Uncertainty envelope": "The radius containing 90% of the drift ensemble's members at that time. Measured against real buoys it is too narrow: they fell inside only 24.5% of the time.",
  Ablation: "Switching one agent off and re-planning, to see what that agent contributes. Downstream agents lose its output.",
  "Verification confidence": "The detection's confidence after the five false-positive checks. It is not the probability the site is a ghost net.",
  "Detection confidence": "The detector's raw debris probability for this candidate, before any verification.",
  "Modelled trajectory": "Ensemble-mean path from the drift model. A prediction, not observed movement.",
  "Data quality": "Which inputs were available to the run. It is not accuracy: a run with every input can still be wrong.",
} as const;

export type GlossaryTerm = keyof typeof GLOSSARY;

/**
 * An inline term with its definition on hover AND keyboard focus. The text is
 * also the accessible description, so it is never hover-only information.
 */
export function Term({ term, children }: { term: GlossaryTerm; children?: React.ReactNode }) {
  const id = React.useId();
  return (
    <span className="gn-term" tabIndex={0} aria-describedby={id}>
      {children ?? term}
      <span role="tooltip" id={id} className="gn-term-tip">{GLOSSARY[term]}</span>
    </span>
  );
}
