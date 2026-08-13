import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE = fs.readFileSync(path.join(here, "graph_page_template.html"), "utf8");
const CLIENT_JS = fs.readFileSync(
  path.resolve(here, "..", "packages", "xy-client", "dist", "standalone.js"),
  "utf8",
);

export function writeGraphPage({ outPath, title, host, spec, blob, meta }) {
  const client = CLIENT_JS.replace(/<\//g, "<\\/");
  const specJs = JSON.stringify(spec).replace(/</g, "\\u003c");
  const metaJs = JSON.stringify(meta).replace(/</g, "\\u003c");
  const html = TEMPLATE.replaceAll("__TITLE__", title)
    .replaceAll("__HOST__", host)
    .replaceAll("__CLIENT_JS__", client)
    .replaceAll("__SPEC__", specJs)
    .replaceAll("__META__", metaJs)
    .replaceAll("__B64__", Buffer.from(blob).toString("base64"));
  fs.writeFileSync(outPath, html);
}
