// The Node geographic wire files share the browser TypeScript verbatim and are
// also served to browsers by the conformance pages, so they must not import
// native bindings. They therefore carry the Scene schema version as a generated
// constant read from the same Rust-owned value the browser client imports
// (js/src/wasm_abi_generated.ts, generated from spec/wasm/abi.json); `--check`
// regeneration fails when it drifts, so a Scene bump cannot go unnoticed.
import {readFileSync} from 'node:fs';

const generated = readFileSync(new URL('../js/src/wasm_abi_generated.ts', import.meta.url), 'utf8');
const SCENE_VERSION = Number(/XYG_WASM_SCENE_VERSION = (\d+)/.exec(generated)?.[1]);
if (!Number.isInteger(SCENE_VERSION)) throw new Error('XYG_WASM_SCENE_VERSION missing from wasm_abi_generated.ts');

export function nodeSceneVersion(text) {
  return text.replaceAll(
    "import {XYG_WASM_SCENE_VERSION} from './wasm_abi_generated';",
    `const XYG_WASM_SCENE_VERSION=${SCENE_VERSION}; // generated: scripts/geo_node_scene_version.mjs`,
  );
}
