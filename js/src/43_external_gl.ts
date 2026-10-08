/** Preserve the owner-visible state around existing XYG mark programs.
 * No shader or geometry policy lives here (spec/design/external-gl.md). */
export function withExternalGLState<T>(gl: WebGL2RenderingContext, operation: () => T): T {
  if (gl.isContextLost()) throw new Error("xy: borrowed WebGL context is lost");
  if (gl.getParameter(gl.TRANSFORM_FEEDBACK_ACTIVE)) {
    throw new Error("xy: borrowed WebGL context has active transform feedback");
  }
  const get = (name: number) => gl.getParameter(name);
  const enabled = [gl.BLEND, gl.CULL_FACE, gl.DEPTH_TEST, gl.STENCIL_TEST,
    gl.SCISSOR_TEST, gl.POLYGON_OFFSET_FILL, gl.RASTERIZER_DISCARD,
    gl.SAMPLE_ALPHA_TO_COVERAGE, gl.SAMPLE_COVERAGE, gl.DITHER]
    .map((name) => [name, gl.isEnabled(name)] as const);
  const program = get(gl.CURRENT_PROGRAM), vao = get(gl.VERTEX_ARRAY_BINDING);
  const array = get(gl.ARRAY_BUFFER_BINDING), pack = get(gl.PIXEL_PACK_BUFFER_BINDING), unpack = get(gl.PIXEL_UNPACK_BUFFER_BINDING);
  const draw = get(gl.DRAW_FRAMEBUFFER_BINDING), read = get(gl.READ_FRAMEBUFFER_BINDING);
  const viewport = get(gl.VIEWPORT), scissor = get(gl.SCISSOR_BOX), colorMask = get(gl.COLOR_WRITEMASK);
  const clear = get(gl.COLOR_CLEAR_VALUE), active = get(gl.ACTIVE_TEXTURE);
  const blend = [gl.BLEND_SRC_RGB, gl.BLEND_DST_RGB, gl.BLEND_SRC_ALPHA, gl.BLEND_DST_ALPHA,
    gl.BLEND_EQUATION_RGB, gl.BLEND_EQUATION_ALPHA].map(get);
  const blendColor = get(gl.BLEND_COLOR), depthMask = get(gl.DEPTH_WRITEMASK);
  const pixelNames = [gl.PACK_ALIGNMENT, gl.PACK_ROW_LENGTH, gl.PACK_SKIP_PIXELS, gl.PACK_SKIP_ROWS,
    gl.UNPACK_ALIGNMENT, gl.UNPACK_ROW_LENGTH, gl.UNPACK_IMAGE_HEIGHT, gl.UNPACK_SKIP_PIXELS,
    gl.UNPACK_SKIP_ROWS, gl.UNPACK_SKIP_IMAGES, gl.UNPACK_FLIP_Y_WEBGL,
    gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, gl.UNPACK_COLORSPACE_CONVERSION_WEBGL];
  const pixels = pixelNames.map((name) => [name, get(name)] as const);
  // The existing painter uses units zero and one. Setup always starts at zero,
  // so an owner's higher active unit is never touched.
  const textures = [0, 1].map((unit) => {
    gl.activeTexture(gl.TEXTURE0 + unit);
    return [get(gl.TEXTURE_BINDING_2D), get(gl.SAMPLER_BINDING)];
  });
  gl.activeTexture(active);
  const attributes = Array.from({ length: get(gl.MAX_VERTEX_ATTRIBS) }, (_, slot) =>
    gl.getVertexAttrib(slot, gl.CURRENT_VERTEX_ATTRIB));
  let isolation: WebGLVertexArrayObject | null = null;
  try {
    isolation = gl.createVertexArray();
    if (!isolation) throw new Error("xy: borrowed WebGL vertex array allocation failed");
    gl.bindVertexArray(isolation);
    for (let slot = 0; slot < attributes.length; slot++) gl.vertexAttrib4f(slot, 0, 0, 0, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
    gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null);
    gl.bindBuffer(gl.PIXEL_UNPACK_BUFFER, null);
    for (const [name] of enabled) gl.disable(name);
    gl.enable(gl.BLEND);
    gl.enable(gl.DITHER);
    gl.blendEquation(gl.FUNC_ADD);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.colorMask(true, true, true, true);
    gl.depthMask(false);
    gl.activeTexture(gl.TEXTURE0);
    for (const name of pixelNames) {
      const value = name === gl.PACK_ALIGNMENT || name === gl.UNPACK_ALIGNMENT ? 4
        : name === gl.UNPACK_COLORSPACE_CONVERSION_WEBGL ? gl.NONE : 0;
      gl.pixelStorei(name, value);
    }
    for (let unit = 0; unit < textures.length; unit++) gl.bindSampler(unit, null);
    return operation();
  } finally {
    // A lost namespace cannot be restored. Its owner handles restoration;
    // trying to query/delete its old objects here would obscure the failure.
    if (!gl.isContextLost()) {
      gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, draw);
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, read);
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, array);
      gl.bindBuffer(gl.PIXEL_PACK_BUFFER, pack);
      gl.bindBuffer(gl.PIXEL_UNPACK_BUFFER, unpack);
      gl.useProgram(program);
      for (let slot = 0; slot < attributes.length; slot++) {
        const value = attributes[slot];
        if (value instanceof Int32Array) gl.vertexAttribI4iv(slot, value);
        else if (value instanceof Uint32Array) gl.vertexAttribI4uiv(slot, value);
        else gl.vertexAttrib4fv(slot, value);
      }
      for (let unit = 0; unit < textures.length; unit++) {
        gl.activeTexture(gl.TEXTURE0 + unit);
        gl.bindTexture(gl.TEXTURE_2D, textures[unit][0]);
        gl.bindSampler(unit, textures[unit][1]);
      }
      gl.activeTexture(active);
      for (const [name, value] of pixels) gl.pixelStorei(name, value);
      gl.viewport(...viewport as [number, number, number, number]);
      gl.scissor(...scissor as [number, number, number, number]);
      gl.colorMask(...colorMask as [boolean, boolean, boolean, boolean]);
      gl.clearColor(...clear as [number, number, number, number]);
      gl.blendFuncSeparate(blend[0], blend[1], blend[2], blend[3]);
      gl.blendEquationSeparate(blend[4], blend[5]);
      gl.blendColor(...blendColor as [number, number, number, number]);
      gl.depthMask(depthMask);
      for (const [name, on] of enabled) if (on) gl.enable(name); else gl.disable(name);
      if (isolation) gl.deleteVertexArray(isolation);
    }
  }
}
