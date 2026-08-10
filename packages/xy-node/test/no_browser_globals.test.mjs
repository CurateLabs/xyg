import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src");

function collectJsFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...collectJsFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".js")) {
      out.push(full);
    }
  }
  return out;
}

test("@xy/node modules do not reference browser globals", () => {
  const files = collectJsFiles(root);
  assert.ok(files.length > 0);
  const banned = /\b(?:window|document|HTMLElement|localStorage)\b/;
  for (const file of files) {
    const src = fs.readFileSync(file, "utf8");
    // Allow mentioning the words in comments / docs strings that explain the
    // VS Code webview split, but forbid executable references.
    const codeLines = src
      .split("\n")
      .filter((line) => {
        const trimmed = line.trim();
        return !(
          trimmed.startsWith("//") ||
          trimmed.startsWith("*") ||
          trimmed.startsWith("/*") ||
          trimmed.startsWith("*/")
        );
      })
      .join("\n");
    assert.equal(
      banned.test(codeLines),
      false,
      `${path.relative(root, file)} references a browser global`,
    );
  }
});
