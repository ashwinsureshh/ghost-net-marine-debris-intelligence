import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from '../node_modules/esbuild/lib/main.js';
import { coverageFromSummaries } from '../src/lib/coverage.ts';

const built = await build({ entryPoints: ['frontend/src/lib/api.ts'], bundle: true,
  write: false, format: 'esm', platform: 'node' });
const { api } = await import('data:text/javascript;base64,' + Buffer.from(built.outputFiles[0].text).toString('base64'));
const coverage = { runId: 'india', name: 'India', bounds: [79,11,80,12],
  scope: 'requested-aoi', start: '2021-01-21', end: '2021-02-01',
  detections: 117, synthetic: false, partial: true };
const summary = { run_id: 'india', inputs_are_synthetic: false, coverage, input_status: 'partial' };

test('live coverage opens and reopens using only the runs response', async () => {
  const paths = [];
  globalThis.window = {};
  globalThis.fetch = async path => {
    paths.push(path);
    assert.equal(path, '/api/runs');
    return new Response(JSON.stringify({ runs: [summary, { run_id: 'demo', inputs_are_synthetic: true }] }));
  };
  const runs = await api.runs();
  for (let opening = 0; opening < 3; opening++) {
    assert.deepEqual(coverageFromSummaries(runs), { coverage: [coverage], failed: 0 });
  }
  assert.deepEqual(paths, ['/api/runs']);
});

test('new and legacy offline bundles supply coverage without network requests', async () => {
  globalThis.fetch = () => { throw new Error('offline must not fetch'); };
  globalThis.window = { __GHOSTNET_STATIC__: { runs: [summary], artefacts: {} } };
  assert.deepEqual(coverageFromSummaries(await api.runs()).coverage, [coverage]);
  window.__GHOSTNET_STATIC__ = { runs: [{ run_id: 'india', inputs_are_synthetic: false }],
    artefacts: { india: { run_id: 'india', region: { name: 'India', bbox: [79,11,80,12],
      window_start: null, window_end: null }, provenance: { notes: [], inputs_are_synthetic: false },
      detections: [], degradations: ['gfw unavailable'] } } };
  const result = coverageFromSummaries(await api.runs()).coverage[0];
  assert.equal(result.partial, true);
  assert.equal(result.scope, 'region');
});
