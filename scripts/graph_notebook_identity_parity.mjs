#!/usr/bin/env node
// Replay actual notebook callback trace/row pairs through the public Node API.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {decodeGraphForgeDocument, graphforgePick, graphforgeStaticPayload} from '../packages/xy-node/src/graphforge.js';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const input = await readFile(process.argv[2]);
const {routedIdentity, layeredIdentity, uuidMasks} = JSON.parse(input);
// Host spelling is the only normalization: preserve exact IDs, row integers,
// layer order and null versus empty result IDs.
const core = row => ({kind: row.kind, uuid: row.uuid, index: row.index, layers: row.layers.map(layer => ({
  layer: layer.layer,
  result_id: Object.hasOwn(layer, 'resultId') ? layer.resultId : layer.result_id,
  row: layer.row,
}))});
const prepare = fixture => {
  const document = Buffer.from(fixture.composition, 'base64');
  const composition = decodeGraphForgeDocument(document);
  const payload = graphforgeStaticPayload(composition, {width: 900, height: 420, positions: fixture.positions});
  assert.equal(payload.figure._graphMeta[0].layout, 'preset', 'parity must not fall back to another layout');
  assert.deepEqual(fixture.positions.uuid, composition.nodes.uuid);
  assert.deepEqual([...payload.positions.x], fixture.positions.x);
  assert.deepEqual([...payload.positions.y], fixture.positions.y);
  return {composition, payload, documentSha256: sha(document)};
};
const {fixture, clicks} = routedIdentity;
const property = prepare(fixture);
const picks = clicks.map(click => {
  assert.equal(click.graphforge.length, 1);
  const expected = fixture.expected.find(row => row.uuid === click.graphforge[0].uuid);
  assert.ok(expected, 'callback must address a fixture edge');
  const identity = graphforgePick(property.payload.figure, property.composition, click);
  assert.deepEqual(identity, expected);
  assert.deepEqual(core(identity), click.graphforge[0]);
  return {trace: click.trace, index: click.index, identity: core(identity)};
});
assert.deepEqual([...new Set(picks.map(pick => pick.identity.index))].sort(), [0, 1, 2, 3, 4]);
const layer = prepare(layeredIdentity);
const layered = graphforgePick(layer.payload.figure, layer.composition, layeredIdentity.click);
assert.deepEqual(layered, layer.composition.identify('node', 0));
assert.deepEqual(core(layered), layeredIdentity.expected);
assert.deepEqual(core(layered), layeredIdentity.click.graphforge[0]);
assert.deepEqual(core(layered).layers, [{layer: 0, result_id: 'notebook-rank', row: 0}]);

// These are real GPU selection buffers read after the Python-origin UUID reply.
const nodeMask = uuidMasks.find(mask => mask.trace === fixture.nodeTrace);
const edgeMask = uuidMasks.find(mask => mask.trace === fixture.edgeTrace);
assert.equal(nodeMask.active, true);
assert.equal(edgeMask.active, true);
assert.deepEqual(nodeMask.selected, [property.payload.figure._graphMeta[0].member_of[0]]);
assert.deepEqual(edgeMask.selected, fixture.edgeSources.flatMap((members, i) => members.length === 1 && members[0] === 0 ? [i] : []));
for (const mask of [nodeMask, edgeMask]) {
  assert.equal(mask.values.length, mask.count);
  assert.ok(mask.values.every(value => value === 0 || value === 1));
  assert.deepEqual(mask.values.flatMap((value, i) => value === 1 ? [i] : []), mask.selected);
}
console.log(JSON.stringify({
  ok: true,
  inputSha256: sha(input),
  nativeSha256: sha(await readFile(process.env.XYG_NATIVE_LIB)),
  documentSha256: property.documentSha256,
  layeredDocumentSha256: layer.documentSha256,
  picks,
  layered: core(layered),
  nodeMask: nodeMask.selected,
  edgeMask: edgeMask.selected,
}));
