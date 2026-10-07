import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleTrack, cumulativeKm, haversineKm, trackHours } from '../src/lib/trajectory.ts';
import { rankDeltas, formatDelta } from '../src/lib/ranking.ts';
import { agentStatuses } from '../src/lib/pipeline.ts';
import { dataQuality, regionFlags, verificationRate, topRejection } from '../src/lib/regions.ts';
import { buildSearchIndex, searchIndex } from '../src/lib/search.ts';

const track = [
  { t: '2018-02-09T00:00:00Z', lat: 16, lon: -88, uncertainty_km: 0 },
  { t: '2018-02-09T12:00:00Z', lat: 16.1, lon: -88, uncertainty_km: 4 },
  { t: '2018-02-10T00:00:00Z', lat: 16.2, lon: -88, uncertainty_km: 10 },
];

test('playback never leaves the exported track', () => {
  assert.deepEqual(sampleTrack(track, -1), { ...sampleTrack(track, 0) });
  const start = sampleTrack(track, 0);
  const end = sampleTrack(track, 5);
  assert.equal(start.lat, 16); assert.equal(start.uncertainty_km, 0); assert.equal(start.distance_km, 0);
  assert.equal(end.lat, 16.2); assert.equal(end.uncertainty_km, 10); assert.equal(end.t, '2018-02-10T00:00:00.000Z');
  assert.equal(sampleTrack([], 0.5), null);
  assert.equal(sampleTrack(track, Number.NaN).lat, 16);
});

test('playback interpolates position, time, radius and distance between steps', () => {
  const mid = sampleTrack(track, 0.25);
  assert.ok(Math.abs(mid.lat - 16.05) < 1e-9);
  assert.equal(mid.uncertainty_km, 2);
  assert.equal(mid.t, '2018-02-09T06:00:00.000Z');
  const total = cumulativeKm(track).at(-1);
  assert.ok(Math.abs(total - 2 * haversineKm(track[0], track[1])) < 1e-6);
  assert.ok(Math.abs(sampleTrack(track, 0.5).distance_km - total / 2) < 1e-6);
  assert.equal(trackHours(track), 24);
});

test('uncertainty radius never shrinks while an exported envelope grows', () => {
  let last = -1;
  for (let f = 0; f <= 1; f += 0.01) {
    const r = sampleTrack(track, f).uncertainty_km;
    assert.ok(r >= last - 1e-12); last = r;
  }
});

test('rank deltas: up, down, unchanged, and new sites are not invented jumps', () => {
  const before = [{ detection_id: 'a', rank: 1 }, { detection_id: 'b', rank: 2 }, { detection_id: 'c', rank: 3 }];
  const after = [{ detection_id: 'c', rank: 1 }, { detection_id: 'a', rank: 2 }, { detection_id: 'd', rank: 3 }];
  const d = rankDeltas(before, after);
  assert.equal(d.get('c'), 2); assert.equal(d.get('a'), -1); assert.equal(d.get('d'), null);
  assert.equal(formatDelta(2).label, '↑ +2'); assert.equal(formatDelta(-1).label, '↓ -1');
  assert.equal(formatDelta(0).label, '—'); assert.equal(formatDelta(null).label, 'NEW');
  assert.equal(rankDeltas(null, after).get('d'), 0, 'first plan shows no movement');
});

test('pipeline states follow the planner: ablation propagates downstream', () => {
  const state = (ablate, notes = [], mpa = true) =>
    Object.fromEntries(agentStatuses(new Set(ablate), notes, mpa).map(s => [s.id, s.state]));
  assert.deepEqual(state([]), { detection: 'complete', verification: 'complete', drift: 'complete',
    attribution: 'complete', vessels: 'complete', prioritisation: 'complete' });
  const drift = state(['drift']);
  assert.equal(drift.drift, 'ablated'); assert.equal(drift.attribution, 'reduced'); assert.equal(drift.prioritisation, 'reduced');
  assert.equal(drift.vessels, 'complete');
  // Attribution is not a score component; switching it off leaves the ranking's inputs intact.
  assert.equal(state(['attribution']).prioritisation, 'complete');
  const puducherry = state([], ['vessels: no GFW SAR detections supplied']);
  assert.equal(puducherry.vessels, 'degraded'); assert.equal(puducherry.prioritisation, 'reduced');
  assert.equal(state([], [], false).prioritisation, 'reduced');
  assert.equal(state(['prioritisation']).prioritisation, 'ablated');
});

const honduras = { run_id: 'h', inputs_are_synthetic: false, detections: 826, verified: 443, rejected: 383,
  trajectories: 443, attributions: 443, correlations: 443, has_mpa_data: true, degradation_notes: [],
  geographic_holdout: false, failed_checks: { cloud_shadow: 12, bright_water_surface: 300 } };

test('data quality counts availability, and never omits missing ground truth', () => {
  const q = dataQuality(honduras);
  assert.equal(q.level, 'high');
  assert.equal(q.factors.find(f => f.id === 'ground_truth').state, 'missing');
  const pud = dataQuality({ ...honduras, correlations: 0, degradation_notes: ['vessels: no GFW'] });
  assert.equal(pud.level, 'partial');
  assert.deepEqual(regionFlags({ ...honduras, degradation_notes: ['vessels: no GFW'] }), ['PARTIAL DATA', 'NO GFW', 'NO GROUND TRUTH']);
  assert.deepEqual(regionFlags({ ...honduras, geographic_holdout: true }), ['FULL DATA', 'NO GROUND TRUTH', 'UNSEEN TEST REGION']);
  assert.equal(dataQuality({ ...honduras, inputs_are_synthetic: true }).level, 'synthetic');
  // An old summary without the new fields is "unknown", not "available".
  assert.equal(dataQuality({ run_id: 'old', inputs_are_synthetic: false }).factors.find(f => f.id === 'vessels').state, 'unknown');
  assert.ok(Math.abs(verificationRate(honduras) - 443 / 826) < 1e-12);
  assert.equal(verificationRate({ run_id: 'x', detections: 0 }), null);
  assert.deepEqual(topRejection(honduras), ['bright_water_surface', 300]);
});

test('command search is local navigation over loaded data', () => {
  const index = buildSearchIndex({
    runs: [{ run_id: 'gulf_of_honduras', region_name: 'Gulf of Honduras', detections: 826 }, { run_id: 'bad', unreadable: true }],
    artefact: {
      run_id: 'gulf_of_honduras',
      detections: [{ id: 'det-1', tile_id: '16PCC', acquired_at: '2018-02-09T16:00:00', lat: 16, lon: -88 }],
      verifications: [{ detection_id: 'det-1', verified: true }],
      attributions: { 'det-1': { candidates: [{ name: 'Motagua', probability: 0.6 }] } },
      protected_areas: [{ name: 'Punta de Manabique', designation: 'Wildlife refuge', lat: 15.9, lon: -88.5 }],
    },
    views: [{ id: 'regions', label: 'Regions' }],
  });
  assert.ok(!index.some(i => i.id === 'bad'));
  assert.equal(searchIndex(index, 'motagua')[0].detectionId, 'det-1');
  assert.equal(searchIndex(index, 'honduras')[0].kind, 'region');
  assert.equal(searchIndex(index, 'manabique')[0].kind, 'protected_area');
  assert.deepEqual(searchIndex(index, '16pcc verified').map(i => i.id), ['det-1']);
  assert.equal(searchIndex(index, 'nothing matches this').length, 0);
  assert.ok(searchIndex(index, '').every(i => i.kind === 'view' || i.kind === 'region'));
});
