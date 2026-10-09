# Selected hierarchy static host matching

Dossier §27/§29/§34. A trusted selected hierarchy SceneData produced by43/44
may mount through the existing `chart.host(frame=frame)` surface. This is static
frame mounting, not an implicit query producer or selected live controller.

The matcher requires private hierarchy provenance and a validated complete
selected footer, including empty selection intent. Its original43 query must be
exactly264 bytes and declare exactly8 payload bytes at232. It compares the
canonical256-byte authoring fields after normalizing only the operation,
process-local source handle and consumed-State payload length/trailer. Immutable
packet source/camera/time/revisions and the exact48 style bytes remain checked.
Malformed/truncated/extra payloads and a selected packet without private hierarchy
provenance cannot obtain this exception. The host independently retains its Data
anchor; the original source/query/frame may be disposed without invalidating the
accepted static paint. Live preparation still rejects hierarchy provenance unless
an explicit hierarchy route is separately admitted.

`tests/test_geo_hierarchy_static_selected.py` exercises actual native37 scoped
build,43 State-to-Query admission,44 same-handle Data publication and static
mount after original frame/source disposal. It checks malformed payloads and
missing private marker before painting. Raw framing in this regression uses
existing canonical encoders; no projection or selection policy lives in the host.
This bounded compatibility proof does not establish massive latency or close
#50/#39.
