# Private overview allocation recovery

Dossier §27–29 and §34. Issued Python/Node/browser overview owners automatically
use the existing Rust nonce/recovery grammar for26–29. Raw nonce0, ABI383,
WASM33, the sixteen-handle/eight-session/eight-Data quotas and engine128/384 MiB
ledgers do not change. This adds transport ownership, not geometry or temporal
policy. Domain45 adoption, mutations35/36 and unknown snapshot6 are separate.

A private per-issuer/per-command slot captures the original producer callables,
complete bounded canonical request and monotonic nonce before dispatch. Requests
are at most280 bytes, confirmations256 bytes. Mutable public bridge/handle/query
fields cannot redirect replay or cleanup. Confirmed live births permit another
nonce; an unconfirmed or retired-but-unreleased birth blocks replacement.
Exact47Confirm settles a captured receipt before publication or another nonce.
Lost ACK retries47 alone. Retired22 carries no owner: exact target0 confirmation
and ReleaseBirth2 must settle before the guard clears. Known older births use
47Confirm, not lower-nonce allocation replay.

A released latest receipt stays attached to its genuine issuer until confirmed
issuer disposal permits Forget1. Python retains a bounded cleanup descriptor in
an issuer-owned token, with global weak values and no owner backlink. JavaScript
uses WeakMap ephemeron ownership. Garbage collection of the original operation
cannot discard its issuer's pending Forget authority. Lost/rejected cleanup ACKs
remain retryable; ReleaseBirth accepts only strict code0, never retired22.

`index.recover()` / `recover_async()` coalesce the complete builder continuation;
`frame.recover()` coalesces the complete authenticated packet read. Disposal waits
these continuations and their exact callback ACKs before releasing credit.
The same fence tracks initial26/29 publication through read23, not only later
recovery. Closing fences prevent late recovered publication. Query publication is one-shot.
Command29 replaces the known Query with Data; failed definite resource admission
leaves its completed Query retryable. Cancel/trap/lost/malformed replies remain
uncertain, even when an exception carries a numeric status. Only proved atomic
resource/stale/output-capacity rejections can end admission without replay.

Known Data disposal drops all views before10. Lost10 is authenticated by direct
47Confirm on its exact birth; it never guesses absence from generic Stale.
ReleaseBirth2 and issuer Forget run afterward, with failed notification retained
for retry. The internal canonical update helper captures the issued Query before28,
returns independent ownership without assigning index.current, and retains failed
post-publication Frame cleanup privately on that Query even after Query close.
The internal canonical retain helper captures its issued copy before26.
Private issued-kind registries dispatch captured canonical close methods even
for unpublished copies and closed Queries with pending Frame cleanup. Public
method decoration cannot redirect host settlement. A canonical host inspection
uses one owned packet copy parsed from privately captured admitted bytes. Public
Scene/count/header backing edits cannot alter it. The existing four-wire ingress
preflight covers admitted transient, private packet, public inspection and the
single host inspection; hosts cache that inspection and drop it before close.
A second inspection request fails rather than allocating unbounded copies.

Retain captures an opaque private membership-context token before26. Installation
occurs only after genuine Data header/source/sequence/snapshot validation. The
canonical callback and snapshot survive disposal of the original Frame/index;
no decoded public token can mint context. Python token ownership avoids a global
registry-value → frame/bridge retention cycle. Source/callback storage remains
caller owned; no resident source-sized host array is introduced.

Actual proofs use the unchanged dependency engine pair and exercise lost/corrupt
26–29, lost47 ACK, old-target lost10 after higher nonces, retired target0 with
corrupt2 ACK, lost Forget, transfer detachment, private producer checks, five-view
sixteen-handle admission, exact domain membership after producer disposal, and
concurrent recovery with gated read/callback/closing controls. They do not claim
massive latency, live browser composition or transport-reset recovery.

```sh
node scripts/gen_geo_overview_hosts.mjs --check
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run pytest tests/test_geo_overview_recovery.py tests/test_geo_overview_source.py tests/test_geo_overview_members.py tests/test_geo_frame_leases.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" node --test packages/xy-node/test/geo-overview-recovery.test.mjs packages/xy-node/test/geo-overview-source.test.mjs
```
