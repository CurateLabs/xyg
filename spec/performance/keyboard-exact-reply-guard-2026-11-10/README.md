# Witness actual keyboard exact-reply consumption

Greptile P2 PRRT_kwDOTxX6Es61i6ld identified a false-positive test: ignoring the
keyboard exact-value reply left the last approximate hover and live text
unchanged, so the old cursor/live assertions passed. A private copy of the
exact0219c636 harness with only that injection dropped passed Chromium. That
passing counterfactual demonstrates the missing guard; it is not evidence that
a reply was consumed. The original completed hosted run remains a pass for
its actual assertions, with this specific coverage limitation retained.

The same required browser conformance command now copies the pre-reply cursor
and records the hover count. After delivery it requires a new `exact:true`
hover for trace0/row1 with the expected canonical f64 values; only that event
can supply the coordinate comparison. Announcement, activation, pointer,
stale-reply, key propagation, layout and pixel assertions and tolerances remain
intact. No production source, generated client/native/WASM, ABI, policy, cap,
default, deadline or CI command changes.

Fresh Chromium and headful Firefox pass. Private final-harness mutations drop
the reply, use a stale sequence or deliver another row; each fails at the new
exact-reply guard. Native/WASM/client inputs remain parent-identical and are
reused without rebuilding. Local headful tests use the already documented
private authenticated TCP display because the fixed /tmp Xvfb lock path hits
quota; the direct server wrapper exits and its cookie and TCP listener are
verified gone. This is not an ordinary-display, WebKit or reliability claim.

Reproduce the normal required test with Node22 and installed Playwright:

```sh
TMPDIR=/var/tmp node scripts/browser_conformance.mjs --browsers=chromium,firefox
```

Use a working display and XY_CONFORMANCE_HEADFUL=1 where software Firefox
requires it. The retained control source/logs and parent/current bindings make
the missing-reply negative reproducible. New final-head hosted browser checks,
completed independent review and the required merge queue remain pending.
The separate desktop proof and whole #1015/M4–7 acceptance remain open.
