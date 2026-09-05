import { staticLegendFit } from '../src/scene.js';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const results = JSON.parse(input).map((encoded) => {
  try {
    return { output: Buffer.from(staticLegendFit(Buffer.from(encoded, 'base64'))).toString('base64') };
  } catch (error) {
    return { error: String(error.message ?? error) };
  }
});
process.stdout.write(JSON.stringify(results));
