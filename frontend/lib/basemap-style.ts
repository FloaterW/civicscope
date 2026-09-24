import type { ExpressionSpecification, FilterSpecification, StyleSpecification } from "maplibre-gl";

/** Guard the observed OpenFreeMap range filter without altering other layers. */
export function normalizeBasemapStyle(style: StyleSpecification): StyleSpecification {
  return {
    ...style,
    layers: style.layers.map(layer => {
      if (layer.id !== "boundary_3" || layer.type !== "line" || layer.source !== "openmaptiles" || layer["source-layer"] !== "boundary") return layer;
      const filter = layer.filter;
      if (!Array.isArray(filter) || filter[0] !== "all" ||
          JSON.stringify(filter[1]) !== JSON.stringify([">=", ["get", "admin_level"], 3]) ||
          JSON.stringify(filter[2]) !== JSON.stringify(["<=", ["get", "admin_level"], 6])) return layer;
      // Missing/non-numeric values previously failed the whole filter. Keep
      // them excluded, but avoid a runtime assertion warning for each tile.
      const level: ExpressionSpecification = ["number", ["get", "admin_level"], -1];
      const guarded: FilterSpecification = ["all", [">=", level, 3], ["<=", level, 6], ...filter.slice(3) as ExpressionSpecification[]];
      return { ...layer, filter: guarded };
    })
  };
}
