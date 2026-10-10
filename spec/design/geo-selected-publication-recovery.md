# Recoverable selected indexed publication

Dossier §27/§29/§34. This engine opt-in journals command19 publication for a
completed selected IndexedQuery. It adds no ABI, transport number, pool, quota,
render policy or geometry/selection policy. Public owner adoption is separate.

## Exact request and phase

XYGQ v1 command19 has exactly304 bytes: the existing256-byte header and48-byte
uniform style. Nonzero u64 nonce@240 opts in; nonce0 is unchanged. Fresh opt-in
requires the exact completed selected-replacement Query created by36. Ordinary
Indexed19 nonzero rejects before mutation; ordinary nonce0 still allocates a
separate Data ID. Exact receipt lookup precedes Query-kind and new-admission
lookup, because successful selected19 replaces Query with Data at the same ID.

The private bank stores the entire original request including style, budget,
sequence and nonce, plus its original256-byte code0 publication receipt. It
returns that exact receipt while the stamped selected semantic Data and its
publication sequence survive. Changed bytes at the same nonce or a lower nonce
reject. A higher nonce cannot recreate the consumed Query or recompile Data.

The19 birth is Data, not36's Query, despite their equal numeric handles. Its
phase requires exact semantic publication sequence, selected output and retained
Scope authority. The19 issuer phase is only the original selected Query. A36
replay/Confirm is retired22 after19, and cannot grant Data or authorize its
cleanup. The19 receipt survives the disappearance of its Query issuer.

## Confirmation and cleanup

Command47 accepts original-command19 with the unchanged272-byte private
Confirm/Forget/ReleaseBirth grammar. Confirm binds issuer, command, nonce,
publication sequence and target. A live19 birth confirms code0; a disposed19
birth confirms22/handle0 without recreating Data. Same request replay also
returns22 after disposal. Lost successful Data10 is authenticated by exact47,
not interpreted from generic errors and not replayed as a new publication.

A lost original19 reply followed by Data retirement permits target0 only for
that exact current retired receipt. Confirm and ReleaseBirth must settle before
replacement/forget. Known historical target retirement uses47 directly.
ReleaseBirth2 is permitted only after confirmed Data death; it does not dispose
Data or another Query/Source/Index. Forget1 needs confirmed receipt and vanished
Query issuer. Clients must retain the receipt until target cleanup is known;
forgetting immediately merely because Query was consumed would lose lost10
recovery authority. Data remains independently usable by retain, Rows, picking,
membership and frozen export under the existing semantic capabilities.

## Complete admission and compatibility

The existing fixed16 receipt and16 historical birth slots and8192-byte controls
are unchanged. Maximum journal request increases from280 to304 bytes; the
existing `4*request_length+512` credit reserves borrowed/canonical exact copies
before allocation. Bank controls, all prior receipts and new request credit are
subtracted before canonical publication. Stamp capacity is checked before Scene
work, including while the old36 stamp is still retained.

Opt-in19 additionally subtracts validated index, IndexOwner, Scope, Query wrapper
and completed result credits. Scope accounting includes its nonce33 receipt
and a distinct newer admitted State; only an Arc-identical State already
credited by the Query is excluded. The same complete Scope accounting applies
to opt-in35/36 without changing nonce0. Result accounting includes separately charged selection/State
storage, from its local processor allowance. The shared semantic clone, output
reservation and render path then use the remaining allowance; rendering deducts
its new semantic copy while that copy is live. These are local accounting
subtractions of already globally charged leases, not additional pools. Global
128MiB processor/384MiB derived,16 handles and8 Data remain unchanged.

Invalid style, failed local/global reserve, bank or Data capacity failure keeps
the completed Query retryable and preserves existing receipts and old frames.
Successful selected19 atomically becomes Data at the same handle, so the
sixteenth handle does not require a seventeenth. Legacy nonce0 preserves its
previous admission, style precedence and full output bytes.

## Proof and remaining gates

Focused tests cover lost-reply replay,36/19 phase separation, lost10 retirement,
exact whole-request/47 identity rejection, ordinary opt-in rejection, held36
stamp saturation and release,8 Data failure atomicity, exact local boundary and
one-byte-under, and unchanged nonce0 publication after failed opt-in admission.
Fresh native/WASM and pinned prior nonce0 full-packet controls are recorded
separately before integration. No massive latency claim follows from this
bounded journal. Public19 adoption, hierarchy44 recovery and remaining scheduling
and massive interaction gates remain open.

## Genuine Worker dispatcher provenance

The internal Worker capture envelope accepts at most304 bytes. Its dispatcher
whitelist adds only exact304-byte GeoScale19 requests and exact272-byte
GeoScale47 controls embedding original command19. Existing exact264-byte35/36,
272-byte47 embedding35/36, and256-byte Snapshot6/7 paths are unchanged. Other
lengths and commands (including44 and MemberData) do not receive provenance.

Every full-request match, including a cloned replay, updates all matching active
capture contexts to the latest private dispatch token. Only its original genuine
reply/error can validate. Returned receipt mutation fails byte comparison;
consumers must parse trusted scalar phase authority synchronously inside the
capture callback. A previous rejection, even from an earlier dispatch in the
same callback, cannot establish nonadmission after a successful clone. Capacity
remains16 contexts; no public testing export or persistent outcome bank is added.

The canonical request is borrowed by each context. One private request snapshot
per pending dispatch and one shared256-byte receipt snapshot remain within the
existing `4*request_length+512` credit (1728 bytes for304). Validation returns the
original reply alias without copying it. Superseding dispatches and scope closure
drop provenance. This dispatcher extension does not implement public19 adoption,
change Rust policy/quotas/ABI signatures, or claim massive-data interaction.

Reproduce the bounded actual Worker proof with:

```sh
CHROMIUM='/path/to/chromium' node scripts/geo_selected19_capture_smoke.mjs
```

Its four original rows include literal u64MAX duplicate feature IDs and signed
MIN time. It proves unready19 rejection then exact-clone successful publication
within one scope, strict47 Confirm, mutable replies, wrong lengths/tags, and
scope closure/capacity under strict CSP. Evidence is recorded in
`spec/performance/geo-selected19-capture-2026-10-10/`.
