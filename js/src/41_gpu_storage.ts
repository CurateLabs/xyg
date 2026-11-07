/** Requested WebGL storage, not physical VRAM (dossier §27).
 * One record per GL object prevents aliases in LOD/retired traces from being
 * counted twice. The context owns bindings; wrappers never cache binding state.
 */
export class GPUAdmissionPending extends Error {
  constructor() { super("xy: GPU storage awaits Rust dashboard admission"); }
}

type Allocation = { owner: object; bytes: bigint; kind: string };
export class GPUStorage {
  private readonly objects = new Map<object, Allocation>();
  constructor(private readonly reserve: (owner: object, peak: bigint) => void,
    private readonly changed: (owner: object) => void) {}

  bytes(owner?: object): bigint {
    let total = 0n;
    for (const allocation of this.objects.values()) {
      if (!owner || allocation.owner === owner) total += allocation.bytes;
    }
    return total;
  }

  snapshot() {
    return Object.freeze({ logicalBytes: this.bytes(), objects: this.objects.size,
      buffers: [...this.objects.values()].filter(a => a.kind === "Buffer").length,
      textures: [...this.objects.values()].filter(a => a.kind === "Texture").length });
  }

  clear(): void { this.objects.clear(); }

  release(gl: WebGL2RenderingContext, owner: object): void {
    let removed = false;
    for (const [object, allocation] of this.objects) {
      if (allocation.owner !== owner) continue;
      (gl[`delete${allocation.kind}`] as Function).call(gl, object);
      this.objects.delete(object);
      removed = true;
    }
    if (removed) this.changed(owner);
  }

  context(gl: WebGL2RenderingContext, owner: object): WebGL2RenderingContext {
    const ledger = this;
    const methods = new Map<PropertyKey, Function>();
    return new Proxy(gl, { get(target, key) {
      const value = Reflect.get(target, key, target);
      if (typeof value !== "function") return value;
      if (methods.has(key)) return methods.get(key);
      const method = (...args: any[]) => {
        const name = String(key);
        if (/^create(Buffer|Texture|Framebuffer|VertexArray|Program|Shader)$/.test(name)) {
          const object = value.apply(target, args);
          if (object) ledger.objects.set(object, { owner, bytes: 0n, kind: name.slice(6) });
          return object;
        }
        if (name.startsWith("delete")) {
          const allocation = ledger.objects.get(args[0]);
          // Shared handles can be bound by clients but have a single owner.
          if (allocation && allocation.owner !== owner) throw new Error("xy: foreign GPU deletion");
          const result = value.apply(target, args);
          if (ledger.objects.delete(args[0])) ledger.changed(owner);
          return result;
        }
        let object: object | null = null, bytes: bigint | null = null;
        if (name === "bufferData") {
          const binding = new Map([[gl.ARRAY_BUFFER, gl.ARRAY_BUFFER_BINDING],
            [gl.ELEMENT_ARRAY_BUFFER, gl.ELEMENT_ARRAY_BUFFER_BINDING],
            [gl.UNIFORM_BUFFER, gl.UNIFORM_BUFFER_BINDING],
            [gl.COPY_READ_BUFFER, gl.COPY_READ_BUFFER_BINDING],
            [gl.COPY_WRITE_BUFFER, gl.COPY_WRITE_BUFFER_BINDING]]).get(args[0]);
          if (binding === undefined) throw new Error("xy: unaccounted GPU buffer target");
          object = gl.getParameter(binding);
          const source = args[1];
          bytes = BigInt(typeof source === "number" ? source :
            args.length > 3 ? (args[4] || source.length - (args[3] || 0)) * source.BYTES_PER_ELEMENT : source.byteLength);
        } else if (name === "texImage2D" || name === "texStorage2D") {
          if (args[0] !== gl.TEXTURE_2D || (name === "texImage2D" && (args.length !== 9 || args[1] !== 0))
            || (name === "texStorage2D" && args[1] !== 1)) throw new Error("xy: unaccounted GPU texture shape");
          object = gl.getParameter(gl.TEXTURE_BINDING_2D);
          if (name === "texImage2D" && args[7] !== gl.UNSIGNED_BYTE) throw new Error("xy: unaccounted GPU texture element type");
          const format = args[2];
          const bpp = format === gl.R8 ? 1 :
            [gl.RGBA, gl.RGBA8, gl.RGBA8UI, gl.R32UI].includes(format) ? 4 : 0;
          if (!bpp) throw new Error("xy: unaccounted GPU texture format");
          bytes = BigInt(args[3]) * BigInt(args[4]) * BigInt(bpp);
        } else if (/^(texStorage3D|texImage3D|compressedTexImage|renderbufferStorage)/.test(name)) {
          throw new Error("xy: GPU storage operation needs an accounting contract");
        }
        if (bytes !== null) {
          const allocation = object && ledger.objects.get(object);
          if (!allocation || allocation.owner !== owner) throw new Error("xy: unowned GPU storage");
          // Reserve old + new storage before the call. Driver-side retirement,
          // alignment and implementation internals remain opaque, not VRAM claims.
          ledger.reserve(owner, ledger.bytes(owner) + bytes);
          const result = value.apply(target, args);
          allocation.bytes = bytes;
          ledger.changed(owner);
          return result;
        }
        return value.apply(target, args);
      };
      methods.set(key, method);
      return method;
    } }) as WebGL2RenderingContext;
  }
}
