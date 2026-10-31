#!/usr/bin/env bash
set -euo pipefail
export GITHUB_WORKSPACE="$PWD"
cargo build --release -p xyg-core
npm ci --prefix packages/xy-node
export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"
export XYG_FRAME_LEASE_WASM="$GITHUB_WORKSPACE/packages/xy-client/dist/xyg-wasm.wasm"
node scripts/geo_frame_leases_conformance.mjs
node scripts/geo_overview_membership_engine_conformance.mjs
XYG_GEO_DOMAIN_MEMBERS_REPORT="$GITHUB_WORKSPACE/geo-overview-domain-members-ci.json" node scripts/geo_overview_domain_members_conformance.mjs
XYG_GEO_RECOVERY_REPORT="$GITHUB_WORKSPACE/geo-allocation-recovery-ci.json" node scripts/geo_allocation_recovery_conformance.mjs
XYG_SELECTED_MUTATION_REPORT="$GITHUB_WORKSPACE/geo-selected-mutation-recovery-ci.json" XYG_SELECTED_MUTATION_BASELINE="$GITHUB_WORKSPACE/spec/performance/geo-selected-mutation-recovery-2026-10-09/legacy-baseline.json" node scripts/geo_selected_mutation_recovery_conformance.mjs
XYG_SELECTED_PUBLICATION_REPORT="$GITHUB_WORKSPACE/geo-selected-publication-recovery-ci.json" XYG_SELECTED_PUBLICATION_BASELINE="$GITHUB_WORKSPACE/spec/performance/geo-selected-publication-recovery-2026-10-09/legacy-baseline.json" node scripts/geo_selected_publication_recovery_conformance.mjs
XYG_SNAPSHOT_RECOVERY_REPORT="$GITHUB_WORKSPACE/geo-snapshot-recovery-ci.json" node scripts/geo_snapshot_recovery_conformance.mjs
node scripts/gen_geo_overview_wire.mjs --check
node scripts/geo_overview_conformance.mjs
node scripts/gen_geo_selected_wire.mjs --check
node scripts/geo_selected_conformance.mjs
node scripts/gen_geo_hierarchy_node.mjs --check
node scripts/gen_geo_overview_hosts.mjs --check
node scripts/geo_hierarchy_conformance.mjs
node scripts/geo_selected_hierarchy_conformance.mjs
XYG_SELECTED_HIERARCHY_REPORT="$GITHUB_WORKSPACE/geo-hierarchy-recovery-ci.json" node scripts/geo_hierarchy_recovery_conformance.mjs
XYG_GEO_MEMBERS_REPORT="$GITHUB_WORKSPACE/geo-overview-members-hosts-ci.json" XYG_GEO_OVERVIEW_WASM="$GITHUB_WORKSPACE/packages/xy-client/dist/xyg-wasm.wasm" node --test packages/xy-node/test/geo-hierarchy.test.mjs packages/xy-node/test/geo-overview-selected.test.mjs packages/xy-node/test/geo-selected-hierarchy.test.mjs packages/xy-node/test/geo-selected-state-nonce.test.mjs packages/xy-node/test/geo-overview-source.test.mjs packages/xy-node/test/geo-overview-recovery.test.mjs packages/xy-node/test/geo-overview-members.test.mjs packages/xy-node/test/geo-overview-members-recovery.test.mjs
