# Foundation disposal failure investigation

The release coordinator observed one current-source full foundation failure:
`browser page errors: worker was disposed`, while Rust workspace checks ran
concurrently. That original message-only error is retained by the coordinator;
it contains no pending-promise identity or disposal stage. No runtime fix or
assertion suppression was made in this investigation.

A transient diagnostic harness served the current foundation fixture with
console messages before/after each awaited `dispose()` and captured complete
pageerror stacks. It kept all assertions and pageerror rejection intact. The
run passed without a pageerror; [its log](current-diagnostic.log) records the
stages. Logging changes timing, so this is diagnostic evidence, not an
unmodified candidate qualification.

The original unmodified `scripts/wasm_foundation_smoke.mjs` was then run
against static assets from the immutable baseline wheel
`xyg 0.0.1.dev2875+cbf2c0eb`, copied from the isolated installed environment.
A transient `@curatelabs/xyg` package wrapper used the original cbf `package.json`
(version `0.0.0`) and a SHA256/byte manifest solely to let the existing harness
consume these exact wheel bytes. This is not a published npm package.

```bash
XYG_BROWSER_DIST=/tmp/xyg-cbf-foundation-baseline \
XYG_WASM_FOUNDATION_REPORT=/tmp/xyg-cbf-foundation-baseline.json \
node scripts/wasm_foundation_smoke.mjs
```

The [baseline report](xyg-cbf-foundation-baseline.json), six screenshots,
[asset manifest](baseline-asset-manifest.json) and [log](baseline.log) retain
the passing full foundation result. An initial setup run completed browser
assertions but could not write its report because the transient package
wrapper lacked `package.json`; supplying the exact original metadata fixed
that reporting setup, without changing browser assets or assertions.

Inspection found that `XygWasmWorker.dispose()` creates this error when
rejecting outstanding work. The worker implementation, tick adapter and
foundation fixture are unchanged by #10. Tick task results are awaited inside
a try/catch with disposed/cancelled admission checks; worker disposal's
bounded acknowledgement race attaches rejection handlers. The original
unhandled promise cannot be identified without a reproducing stack. Both
comparison runs were quiet relative to the original concurrent workspace
validation. The failure remains **unreproduced**, not fixed; the coordinator
must retain that qualification alongside final candidate checks.
