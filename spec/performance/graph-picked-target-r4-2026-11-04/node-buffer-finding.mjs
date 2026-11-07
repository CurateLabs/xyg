// Separate existing Node codec finding; no product change or guard bypass.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { encodeContainer, decodeContainer, DTYPE } from "../../../packages/xy-node/src/graphforge-container.js";
const bytes=encodeContainer("XYGI",[{name:"header.u64",dtype:DTYPE.u64,values:[7n,9n,1n]}]);
const backing=Buffer.alloc(bytes.length+1);backing.set(bytes);
const buffer=backing.subarray(0,bytes.length);
assert.deepEqual([...buffer],[...bytes]);
assert.deepEqual([...decodeContainer(bytes,"XYGI").get("header.u64#0").value],[7n,9n,1n]);
assert.throws(()=>decodeContainer(buffer,"XYGI"),RangeError);
console.log(JSON.stringify({finding:"Existing Node numeric decoder uses Buffer.slice().buffer without restricting backing span",productionFile:"packages/xy-node/src/graphforge-container.js",sha256:createHash("sha256").update(fs.readFileSync("packages/xy-node/src/graphforge-container.js")).digest("hex"),validInputBytes:bytes.length,bufferBackingBytes:buffer.buffer.byteLength,inputBytesIdentical:true,plainUint8ArrayPasses:true,bufferThrowsRangeError:true,productChanged:false},null,2));
