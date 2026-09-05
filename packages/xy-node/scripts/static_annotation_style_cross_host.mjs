/** Raw framing checks only; this probe does not claim public authoring parity. */
import { staticAnnotationStyle } from "../src/index.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const results = {};
for (const [name, value] of Object.entries(JSON.parse(input))) {
  try {
    results[name] = { output: Buffer.from(staticAnnotationStyle(Buffer.from(value, "base64"))).toString("base64") };
  } catch (error) {
    results[name] = { error: String(error.message ?? error) };
  }
}
process.stdout.write(JSON.stringify(results));
