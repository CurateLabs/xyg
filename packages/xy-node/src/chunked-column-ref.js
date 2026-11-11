// Private issued-plane framing shared by the native source and filter client.
export class ChunkedColumnRef {
  constructor(source, plane) { this.source = source; this.plane = plane; }
  get length() { return this.source.rows; }
}
