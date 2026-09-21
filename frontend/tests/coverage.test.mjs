import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCoverage } from '../src/lib/coverage.ts';

const run = (notes = [], bbox = [-90, 10, -80, 20]) => ({
  run_id: 'test', region: { name: 'Test', bbox, window_start: '2021-01-01', window_end: '2021-02-01' },
  provenance: { notes, inputs_are_synthetic: false }, detections: [], degradations: [],
});

test('uses exported AOI rather than larger named region, including zero detections', () => {
  const result = runCoverage(run(['Imagery covers AOI [-88.86, 15.88, -88.36, 16.28], not necessarily the full named region.']));
  assert.deepEqual(result.bounds, [-88.86, 15.88, -88.36, 16.28]);
  assert.equal(result.scope, 'requested-aoi');
  assert.equal(result.detections, 0);
});
test('legacy region bounds are labelled as region, never observed pixel coverage', () => {
  assert.equal(runCoverage(run()).scope, 'region');
});
test('malformed or unsafe metadata cannot invent a footprint', () => {
  for (const note of ['Imagery covers AOI ["1",2,3,4]', 'Imagery covers AOI [3,2,1,4]',
    'Imagery covers AOI [0,0,181,2]', 'Imagery covers AOI [0,0,1]', 'Imagery covers AOI [nope]']) {
    assert.equal(runCoverage(run([note], null)).scope, 'unknown');
    assert.equal(runCoverage(run([note], null)).bounds, null);
  }
});
test('synthetic status and historical dates survive extraction', () => {
  const fixture = run(); fixture.provenance.inputs_are_synthetic = true;
  const result = runCoverage(fixture);
  assert.equal(result.synthetic, true);
  assert.equal(result.start, '2021-01-01');
  assert.equal(result.end, '2021-02-01');
});
test('missing inputs remain explicit even when there are detections', () => {
  const fixture = run(); fixture.degradations = ['vessels: unavailable']; fixture.detections = [{}];
  assert.equal(runCoverage(fixture).partial, true);
});
