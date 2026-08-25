// Classic-worker contract fixture: usable from a self-contained file: export
// under worker-src blob:, without fetch(), importScripts(), or module URLs.
export async function verifyInlineWasmWorker(inline) {
  if (!inline?.base64 || !inline?.classicWorkerSource) throw new Error("inline WASM artifact missing");
  if (/\bfetch\s*\(|importScripts\s*\(|import\.meta|type:\s*["']module/.test(inline.classicWorkerSource)) {
    throw new Error("inline WASM classic worker is not offline-safe");
  }
  const url = URL.createObjectURL(new Blob([inline.classicWorkerSource], { type: "application/javascript" }));
  const worker = new Worker(url);
  try {
    const reply = await new Promise((resolve) => {
      worker.onmessage = (event) => resolve(event.data);
      worker.postMessage({ type: "xyg-inline-wasm-init", base64: inline.base64 });
    });
    if (reply?.type !== "xyg-inline-wasm-ready" || !reply.exports?.includes("memory")) throw new Error("inline WASM compile failed");
  } finally { worker.terminate(); URL.revokeObjectURL(url); }
}
