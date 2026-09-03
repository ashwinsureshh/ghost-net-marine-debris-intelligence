import type {
  AppMeta,
  ApprovalRecord,
  BenchmarkReport,
  PlanResponse,
  RejectedResponse,
  RunArtefact,
  RunSummary,
} from "./types";

/**
 * Two transports behind one interface.
 *
 * Normally the app talks to the FastAPI backend. But PRD 9.1 requires an
 * on-disk static export that survives a sleeping free-tier host or dead venue
 * wifi, and in that mode there is no server to call. When the page is opened
 * from `file://`, or a `window.__GHOSTNET_STATIC__` bundle was injected by the
 * static exporter, every read is served from that bundle instead.
 *
 * The one thing static mode cannot do is record an approval (FR-6.4), because
 * that is a write. It says so plainly rather than pretending to succeed.
 */

declare global {
  interface Window {
    __GHOSTNET_STATIC__?: {
      meta: AppMeta;
      benchmark?: BenchmarkReport;
      runs: RunSummary[];
      artefacts: Record<string, RunArtefact>;
      plans: Record<string, PlanResponse>;
      rejected: Record<string, RejectedResponse>;
    };
  }
}

export const isStaticMode = () =>
  typeof window !== "undefined" && Boolean(window.__GHOSTNET_STATIC__);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      "Cannot reach the server. If it is deployed on a free tier it may be " +
        "waking up — retry in a few seconds.",
      0,
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

const staticBundle = () => window.__GHOSTNET_STATIC__!;

export const api = {
  async meta(): Promise<AppMeta> {
    if (isStaticMode()) return staticBundle().meta;
    return request<AppMeta>("/api/meta");
  },

  async benchmark(): Promise<BenchmarkReport> {
    if (isStaticMode()) {
      // An export built before the strip existed simply has no benchmark
      // block. Say that, rather than rendering an empty strip that reads as
      // "no measured results" when the results are merely not in this bundle.
      return (
        staticBundle().benchmark ?? {
          available: false,
          unavailable_reason:
            "This offline export was built before measured results were bundled. " +
            "Rebuild it with scripts/build_static_export.py, or read eval/results.md.",
          dataset: "MARIDA",
          dataset_version: "",
          dataset_doi: "",
          source_file: "eval/marida_ablation.json",
          results_doc: "eval/results.md",
          fdi_threshold: null,
          detector: null,
          verification: null,
          detectors: [],
          verification_overlap: null,
          multi_temporal: null,
          multi_temporal_caveats: [],
          generalisation: null,
          generalisation_caveats: [],
          caveats: [],
        }
      );
    }
    return request<BenchmarkReport>("/api/benchmark");
  },

  async runs(): Promise<RunSummary[]> {
    if (isStaticMode()) return staticBundle().runs;
    const body = await request<{ runs: RunSummary[] }>("/api/runs");
    return body.runs;
  },

  async run(runId: string): Promise<RunArtefact> {
    if (isStaticMode()) {
      const artefact = staticBundle().artefacts[runId];
      if (!artefact) throw new ApiError(`Run ${runId} is not in the static export.`, 404);
      return artefact;
    }
    return request<RunArtefact>(`/api/runs/${encodeURIComponent(runId)}`);
  },

  async rejected(runId: string): Promise<RejectedResponse> {
    if (isStaticMode()) {
      const found = staticBundle().rejected[runId];
      if (!found) throw new ApiError(`Run ${runId} is not in the static export.`, 404);
      return found;
    }
    return request<RejectedResponse>(`/api/runs/${encodeURIComponent(runId)}/rejected`);
  },

  async plan(
    runId: string,
    body: {
      vessel_capacity: number;
      planning_horizon_days: number;
      ablate: string[];
      include_rationales?: boolean;
    },
  ): Promise<PlanResponse> {
    if (isStaticMode()) {
      const frozen = staticBundle().plans[runId];
      if (!frozen) throw new ApiError(`Run ${runId} is not in the static export.`, 404);
      // Capacity still applies client-side so the control keeps working
      // offline; ablation cannot, because it would need re-scoring.
      if (frozen.plan) {
        const assignments = frozen.plan.assignments.slice(0, body.vessel_capacity);
        const deferred = [
          ...frozen.plan.assignments.slice(body.vessel_capacity).map((a) => a.detection_id),
          ...frozen.plan.deferred,
        ];
        return {
          ...frozen,
          plan: {
            ...frozen.plan,
            vessel_capacity: body.vessel_capacity,
            assignments,
            deferred,
          },
        };
      }
      return frozen;
    }
    return request<PlanResponse>(`/api/runs/${encodeURIComponent(runId)}/plan`, {
      method: "POST",
      body: JSON.stringify({ include_rationales: true, ...body }),
    });
  },

  async approve(
    runId: string,
    body: {
      reviewer: string;
      vessel_capacity: number;
      ablate: string[];
      detection_ids: string[];
      note?: string;
    },
  ): Promise<{ approval: ApprovalRecord; warning: string | null }> {
    if (isStaticMode()) {
      throw new ApiError(
        "This is the offline static export, which is read-only. Recording an " +
          "approval (FR-6.4) needs the live server.",
        0,
      );
    }
    return request(`/api/runs/${encodeURIComponent(runId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: "", ...body }),
    });
  },

  async approvals(runId: string): Promise<ApprovalRecord[]> {
    if (isStaticMode()) return [];
    const body = await request<{ approvals: ApprovalRecord[] }>(
      `/api/runs/${encodeURIComponent(runId)}/approvals`,
    );
    return body.approvals;
  },
};
