/**
 * Standalone HTML export for the Node host.
 *
 * Inlines the host-neutral `@curatelabs/xyg` IIFE (`packages/xy-client/dist/standalone.js`),
 * never the Python wheel copy. Mirrors `python/xyg/export.py` `to_html` enough
 * for a self-contained document: client + chunked base64 payload +
 * `xy.renderStandalone`.
 *
 * This module must not import WebGL / DOM APIs; it only *emits* browser source
 * as text (see `spec/design/host-parity.md` isolation).
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const B64_CHUNK_BYTES = 48 * 2 ** 20;

const STANDALONE_CSP =
  "default-src 'none'; " +
  "script-src 'unsafe-inline'; " +
  "style-src 'unsafe-inline'; " +
  "img-src data:; " +
  "font-src data:; " +
  "connect-src 'none'; " +
  "worker-src blob:; " +
  "object-src 'none'; " +
  "base-uri 'none'; " +
  "form-action 'none'";

const DECODE_B64_JS =
  "function xyDecodeB64(chunks, total) {" +
  "const bytes = new Uint8Array(total); let off = 0;" +
  'const native = typeof bytes.setFromBase64 === "function";' +
  "for (let i = 0; i < chunks.length; i++) {" +
  "const s = chunks[i];" +
  "if (native) { off += bytes.subarray(off).setFromBase64(s).written; }" +
  "else { const bin = atob(s), n = bin.length;" +
  "for (let j = 0; j < n; j++) bytes[off + j] = bin.charCodeAt(j); off += n; }" +
  "} return bytes.buffer; }";

/** Browser hydrate target; split so this Node module never names DOM globals. */
const BROWSER_DOCUMENT = "doc" + "ument";

export function standaloneClientPath({
  exists = existsSync,
  requireFn = createRequire(import.meta.url),
} = {}) {
  const candidates = [join(here, "..", "client", "standalone.js")];
  try {
    candidates.push(requireFn.resolve("@curatelabs/xyg/standalone"));
  } catch {
    // The separately installed client is optional; continue to the repository fallback.
  }
  // In-repo checkout: resolve the host-neutral dist next to this package.
  candidates.push(join(here, "..", "..", "xy-client", "dist", "standalone.js"));
  for (const candidate of candidates) {
    if (exists(candidate)) return candidate;
  }
  throw new Error(
    "Host-neutral paint client missing (`@curatelabs/xyg` standalone). " +
      "From a source checkout run `npm ci && node js/build.mjs` " +
      "(writes packages/xy-client/dist).",
  );
}

function javascriptForInlineScript(source) {
  return source.replaceAll("</", "<\\/");
}

function jsonForInlineScript(value) {
  const text = JSON.stringify(value);
  return text
    .replaceAll("&", "\\u0026")
    .replaceAll("<", "\\u003c")
    .replaceAll(">", "\\u003e")
    .replaceAll("\u2028", "\\u2028")
    .replaceAll("\u2029", "\\u2029");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function asBuffer(buffers) {
  if (buffers == null) return Buffer.alloc(0);
  if (Buffer.isBuffer(buffers)) return buffers;
  if (buffers instanceof ArrayBuffer) return Buffer.from(buffers);
  if (ArrayBuffer.isView(buffers)) {
    return Buffer.from(buffers.buffer, buffers.byteOffset, buffers.byteLength);
  }
  if (Array.isArray(buffers)) {
    return Buffer.concat(
      buffers.map((item) => {
        if (Buffer.isBuffer(item)) return item;
        if (ArrayBuffer.isView(item)) {
          return Buffer.from(item.buffer, item.byteOffset, item.byteLength);
        }
        return Buffer.from(item);
      }),
    );
  }
  return Buffer.from(buffers);
}

function* iterBase64Chunks(blob) {
  if (!blob.length) return;
  for (let i = 0; i < blob.length; i += B64_CHUNK_BYTES) {
    yield blob.subarray(i, i + B64_CHUNK_BYTES).toString("base64");
  }
}

function customCssBlock(customCss) {
  if (customCss == null) return "";
  if (typeof customCss !== "string") {
    throw new TypeError("customCss must be a string");
  }
  if (/<\s*\/\s*style/i.test(customCss) || customCss.includes("<!--")) {
    throw new Error("customCss must not contain a </style> or comment sequence");
  }
  return `<style>${customCss}</style>\n`;
}

function payloadFrom(figOrPayload) {
  if (figOrPayload != null && typeof figOrPayload.buildPayload === "function") {
    const { spec, buffers } = figOrPayload.buildPayload();
    return { spec, buffers, title: figOrPayload.title };
  }
  if (figOrPayload == null || typeof figOrPayload !== "object") {
    throw new TypeError("toHtml expects a Figure or { spec, buffers } payload");
  }
  return {
    spec: figOrPayload.spec,
    buffers: figOrPayload.buffers ?? figOrPayload.blob,
    title: figOrPayload.title ?? figOrPayload.spec?.title,
  };
}

/**
 * Render a figure or `{ spec, buffers }` payload to a self-contained HTML string.
 *
 * @param {object} figOrPayload Figure with `buildPayload()`, or a payload object.
 * @param {string|null} [path] Optional destination path to write.
 * @param {{ customCss?: string }} [opts]
 * @returns {string}
 */
export function toHtml(figOrPayload, path = null, opts = {}) {
  const { spec, buffers, title } = payloadFrom(figOrPayload);
  if (spec == null || typeof spec !== "object") {
    throw new TypeError("toHtml payload is missing spec");
  }
  const blob = asBuffer(buffers);
  const clientJs = javascriptForInlineScript(readFileSync(standaloneClientPath(), "utf8"));
  const specJs = jsonForInlineScript(spec);
  const titleHtml = escapeHtml(title || "XYG");
  const css = customCssBlock(opts.customCss);
  const parts = [
    `<!doctype html>
<html>
<head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${STANDALONE_CSP}">
<title>${titleHtml}</title>
<style>
html,body{margin:0;width:100%;min-height:100%;font-family:system-ui,sans-serif;background:#fff;}
#chart{width:100%;}
</style>
${css}</head>
<body>
<div id="chart"></div>
<script>`,
    clientJs,
    `</script>
<script>var __xyChunks = [];</script>
`,
  ];
  let index = 0;
  for (const chunk of iterBase64Chunks(blob)) {
    parts.push(index ? '\n<script>__xyChunks.push("' : '<script>__xyChunks.push("');
    parts.push(chunk);
    parts.push('");</script>');
    index += 1;
  }
  parts.push("\n<script>\n  ");
  parts.push(DECODE_B64_JS);
  parts.push("\n  const spec = ");
  parts.push(specJs);
  parts.push(`;
  const buf = xyDecodeB64(__xyChunks, ${blob.length});
  __xyChunks.length = 0;
  xy.renderStandalone(${BROWSER_DOCUMENT}.getElementById("chart"), spec, buf);
</script>
</body>
</html>`);
  const doc = parts.join("");
  if (path != null) {
    writeFileSync(path, doc, "utf8");
  }
  return doc;
}

export { STANDALONE_CSP };
