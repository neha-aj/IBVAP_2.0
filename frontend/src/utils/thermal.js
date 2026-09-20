// A camera whose thermal view is *generated* from its own uploaded video
// (rather than a separately uploaded thermal file) carries this marker in
// `thermalSourceUrl` -- same literal the backend stores.
export const DERIVED_THERMAL_SOURCE = "derived:rgb";

export function hasGeneratedThermal(camera) {
  return camera?.thermalSourceUrl === DERIVED_THERMAL_SOURCE;
}
