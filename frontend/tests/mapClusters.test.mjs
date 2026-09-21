import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clusterObservations } from '../src/lib/mapClusters.ts';

test('every observation survives exactly once, including identical coordinates', () => {
  const records = Array.from({ length: 826 }, (_, i) => Object.freeze({ id: `${i}`, x: i % 4, y: i % 5 }));
  const groups = clusterObservations(Object.freeze(records));
  assert.equal(groups.length, 1);
  assert.deepEqual(groups.flatMap(g => g.members).map(p => p.id).sort(), records.map(p => p.id).sort());
  assert.equal(new Set(groups.flatMap(g => g.members).map(p => p.id)).size, 826);
});

test('selected observation stays individually reachable even in a coincident group', () => {
  const groups = clusterObservations([{ id: 'a', x: 2, y: 2 }, { id: 'b', x: 2, y: 2 }], 'b');
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.find(g => g.members[0].id === 'b').members.map(p => p.id), ['b']);
});

test('zooming separates nearby projected observations', () => {
  const records = [{ id: 'a', x: 10, y: 10 }, { id: 'b', x: 20, y: 20 }];
  assert.equal(clusterObservations(records).length, 1);
  assert.equal(clusterObservations(records.map(p => ({ ...p, x: p.x * 8, y: p.y * 8 }))).length, 2);
});

test('negative world coordinates and cell boundaries conserve records', () => {
  const records = [-57, -56, -1, 0, 55, 56].map(x => ({ id: String(x), x, y: 0 }));
  assert.deepEqual(clusterObservations(records).map(g => g.members.length), [1, 2, 2, 1]);
  assert.deepEqual(clusterObservations([]), []);
  assert.throws(() => clusterObservations(records, null, 0));
});

test('input order does not affect membership or centroid', () => {
  const records = [{ id: 'a', x: 1, y: 3 }, { id: 'b', x: 3, y: 1 }, { id: 'c', x: 100, y: 100 }];
  const normalise = rows => clusterObservations(rows).map(g => ({ ...g,
    members: g.members.map(p => p.id).sort() })).sort((a, b) => a.x - b.x);
  assert.deepEqual(normalise(records), normalise([...records].reverse()));
});
