# Public compatibility policy for the synchronized 0.6 line

This is the policy required by [#108](https://github.com/CurateLabs/xyg/issues/108),
not a declaration that a candidate has passed acceptance. The currently
published `0.0.1a2` remains experimental. The policy below applies to the
explicitly stable records in the inventory accepted with the first `0.6`
candidate. [Readiness](0.6.0-readiness.md) records the remaining release gates.

## One public version line

Python `xyg`, the browser package, the Node facade, and all five Node native packages share one public release version.
[`release_version.py`](../../scripts/release_version.py) is the spelling
authority: `xyg-v0.6.0-rc.N` maps to Python `0.6.0rcN` and npm `0.6.0-rc.N`.
Different spellings do not identify different releases. GraphForge has its own
version sequence; matching candidate suffixes do not establish compatibility.
The packaged [Core declaration](../../python/xyg/graphforge-compatibility.json)
names the qualified versions and evidence.

## Classify before accepting

The [source inventory](api-inventory.md) must classify every exported surface
and supported configuration entry before release acceptance:

| Class | Commitment |
| --- | --- |
| Stable | The documented signatures, defaults, supported inputs, results, error codes, ownership, lifecycle, and host capabilities are backward compatible throughout `0.6.x`. |
| Experimental | Explicitly labeled at the public entry and in the accepted inventory. Changes require release notes and migration guidance; stable guarantees are not implied by an export alone. |
| Internal | Private modules, generated host bindings, binary transport details, build implementation, and undocumented implementation objects. Applications must use the owning public entry point. |
| Unclassified | A preparation gap. An exported name with this status cannot be treated as frozen or accepted. |

Classification is about compatibility, not capability acceptance. A required
#108 journey cannot be removed, silently degraded, or declared optional by
marking its API experimental. Each supported host still needs its specified
correctness, unsupported-case, resource, accessibility, and lifecycle evidence.

For stable APIs, the contract includes accepted keyword and positional forms,
return shapes and types, finite-value/identity rules, units, event ordering,
resource ownership, explicit close/dispose behavior, and default visual and
numerical semantics. A new required argument, removed export, changed default,
new implicit dependency, unsupported former host, or changed stable error code
is a compatibility change. Optional additions must preserve existing calls.
Rendering tolerances come from the relevant acceptance fixture; this policy
does not promise byte-identical pixels across different graphics drivers.

## Breaking changes and deprecation

A breaking stable-API change requires a new synchronized minor line and
migration guidance. The replacement must be available before removal. Normal
deprecation provides both at least **two minor releases** and **180 days** of
notice; both conditions must pass. For example, a deprecation introduced in
`0.6` cannot be removed before `0.8`, and not before the date threshold even
if two minor releases ship sooner. Patch releases in `0.6.x` cannot remove it.

The deprecation record names the old entry, replacement, first deprecated
version/date, earliest eligible removal version/date, affected hosts and
formats, and a tested before/after example. Use the language's documented
warning mechanism where one exists. Keep types, examples, and migration notes
consistent; a warning alone is not the migration plan.

A documented security exception may shorten that period. Its disposition
records the affected versions, concrete reason, new behavior, migration, and
rollback limitations. Do not invoke this exception for routine refactoring or
to hide a product regression. Fixing behavior that violated an existing
explicit contract still needs a regression test and release note when users
can observe the correction.

## Binary and dependency boundaries

Native C ABI, Scene, live wire, browser painter, WASM ABI, and their subordinate
packed records are co-versioned internal contracts. Public package semver is
not binary negotiation. Load only matching producer/consumer artifacts unless
that specific reader explicitly supports the incoming version. Unknown kinds,
versions, reserved bits, malformed lengths, and unsupported capabilities fail
before partial execution; hosts never reinterpret old bytes by changing a
version word. The generated [native](../abi/xyg-abi.json) and
[WASM](../wasm/abi.json) manifests, plus the final artifact ledger, bind the
accepted values. Follow [format and migration rules](formats-and-migration.md)
for stored data and rebuildable caches.

Python package consumers need no Node runtime. Node/browser consumers need no
Python runtime. Explicit development overrides and build controls belong to
the inventory with their actual scope; they do not authorize publishing a
wheel with a missing mandatory native core or browser asset. Changing a
supported runtime floor or public environment variable follows the same
stable/experimental classification as an API change.

## Acceptance and candidate changes

Before selecting the final unused candidate, reconcile the inventory with the
actual exports, signatures/defaults, types, examples, supported-host matrix,
and documented errors and lifecycle. Record unresolved experimental limits
with their owners. Retain the inventory and manifests with the exact accepted
source and archive hashes; a green PR check is not that freeze record.

A material change after candidate acceptance invalidates the affected
acceptance. Select a new unused candidate, rebuild its target archives once,
and rerun affected evidence and the required final matrix. Preserve previous
artifacts and their original status; never relabel an older draft or replace
registry bytes. RC publication does not declare stable `0.6.0`.
