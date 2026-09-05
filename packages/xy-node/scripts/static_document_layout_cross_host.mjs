import fs from "node:fs";

import { staticDocumentLayout } from "../src/index.js";

const requests = JSON.parse(fs.readFileSync(0, "utf8"));
const results = requests.map((encoded) => {
  const bytes = Uint8Array.from(Buffer.from(encoded, "base64"));
  try {
    return { output: Buffer.from(staticDocumentLayout(bytes)).toString("base64") };
  } catch (error) {
    return { error: String(error.message) };
  }
});
process.stdout.write(JSON.stringify(results));
