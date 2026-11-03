/** Persisted authoring intent. Hosts resolve local source references; Rust owns composition. */
const object = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
const field = (v) => typeof v === 'string' && v.trim().length > 0;
const optionalField = (v) => v === undefined || field(v);
const keysOnly = (v, keys) => Object.keys(v).every(key => keys.includes(key));
const localPath = (v) => field(v) && !/^[a-z][a-z0-9+.-]*:/i.test(v);

/** Native ingress is untrusted: validate explicit field names and bounded layout options. */
function isVisualizationIntent(value) {
  if (!object(value) || !keysOnly(value,['format','name','result','kind','filters',...(value.kind === 'result-graph' ? ['base','intent','graph'] : value.kind === 'chart' ? ['chart'] : value.kind === 'temporal' ? ['temporal'] : value.kind === 'geospatial' ? ['geospatial'] : [])]) || value.format !== 'xyg.intent/v1' || typeof value.name !== 'string' || !localPath(value.result)
    || !Array.isArray(value.filters) || !value.filters.every(f => object(f) && keysOnly(f,["column","operator","value"]) && field(f.column) && ['equals','contains'].includes(f.operator) && field(f.value))
    || (value.base !== undefined && !localPath(value.base)) || (value.intent !== undefined && !['graph','table','bar-chart','parallel-coordinates','embedding-coordinates'].includes(value.intent))) return false;
  if (value.kind === 'result-graph') return object(value.graph) && keysOnly(value.graph,['layout','iterations']) && ['cose','force','circle','grid'].includes(value.graph.layout) && Number.isInteger(value.graph.iterations) && Number(value.graph.iterations) >= 1 && Number(value.graph.iterations) <= 1000;
  if (value.kind === 'chart') return object(value.chart) && keysOnly(value.chart,["mark","x","y","color"]) && ['bar','scatter','line','histogram'].includes(value.chart.mark) && field(value.chart.x) && optionalField(value.chart.y) && (value.chart.mark === 'histogram' || field(value.chart.y)) && optionalField(value.chart.color);
  if (value.kind === 'temporal') return object(value.temporal) && keysOnly(value.temporal,["timestamp","value","series","timezone","mark"]) && field(value.temporal.timestamp) && field(value.temporal.value) && optionalField(value.temporal.series) && value.temporal.timezone === 'UTC' && ['line','bar','scatter'].includes(value.temporal.mark);
  if (value.kind === 'geospatial') {
    const geo = value.geospatial;
    return object(geo) && keysOnly(geo,["longitude","latitude","targetLongitude","targetLatitude","crs","projection","longitudeCenter","latitudeCenter","zoom"]) && field(geo.longitude) && field(geo.latitude) && optionalField(geo.targetLongitude) && optionalField(geo.targetLatitude) && Boolean(geo.targetLongitude) === Boolean(geo.targetLatitude) && geo.crs === 4326 && geo.projection === 3857 && ['longitudeCenter','latitudeCenter','zoom'].every(k => typeof geo[k] === 'number' && Number.isFinite(geo[k]));
  }
  return false;
}

function createGraphForgeIntent(input) {
  return {format:'xyg.intent/v1',name:input.name,result:input.result,kind:'result-graph',filters:input.filters ?? [],base:input.base,intent:input.intent,graph:{layout:'cose',iterations:250}};
}

exports.isVisualizationIntent = isVisualizationIntent;
exports.createGraphForgeIntent = createGraphForgeIntent;
