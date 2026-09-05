import fs from "node:fs";

import { staticPanelChrome } from "../src/index.js";

const requests = JSON.parse(fs.readFileSync(0, "utf8"));
const results = requests.map((encoded) => {
  try {
    const output = staticPanelChrome(Uint8Array.from(Buffer.from(encoded, "base64")));
    return { output: Buffer.from(output).toString("base64") };
  } catch (error) {
    return { error: String(error.message) };
  }
});
process.stdout.write(JSON.stringify(results));
