import { FlaskConical, WifiOff } from "lucide-react";
import type { AppMeta, RunSummary } from "@/lib/types";
import { formatDateShort } from "@/lib/utils";
interface HeaderProps {
  meta: AppMeta | null; runs: RunSummary[]; activeRunId: string | null;
  onRunChange: (runId: string) => void; staticMode: boolean;
}
export function Header({ meta, runs, activeRunId, onRunChange, staticMode }: HeaderProps) {
  const active = runs.find(r => r.run_id === activeRunId);
  return <header className="atlas-header">
    <div className="atlas-masthead"><span>ghostnet<span className="atlas-brand-dot">.</span></span><p>Marine debris intelligence</p></div>
    <div className="atlas-run-picker">
      <label htmlFor="run-select">Observation region</label>
      <select id="run-select" value={activeRunId ?? ""} onChange={e => onRunChange(e.target.value)} disabled={!runs.length}>
        {!runs.length && <option value="">No runs available</option>}
        {runs.map(run => <option key={run.run_id} value={run.run_id}>{run.region_name ?? run.run_id}{run.generated_at ? ` — exported ${formatDateShort(run.generated_at)}` : ''}</option>)}
      </select>
    </div>
    <div className="atlas-run-status">
      <span>{active?.inputs_are_synthetic ? <><FlaskConical size={13} /> Synthetic run</> : <>Historical data</>}</span>
      <small>{staticMode ? <><WifiOff size={12} /> Offline · read only</> : `Research prototype · v${meta?.version ?? '—'}`}</small>
    </div>
    <p className="atlas-disclaimer">{meta?.prototype_notice ?? 'Decision-support only; every output stops at a recommendation for human review.'}</p>
  </header>;
}
