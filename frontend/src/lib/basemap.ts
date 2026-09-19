import type { StyleSpecification } from "maplibre-gl";

/**
 * Basemap for the map canvas. The design wants a colourless vector basemap on the neutral ramp so the
 * accent is reserved for route and hazard data.
 *
 * Set NEXT_PUBLIC_BASEMAP_STYLE_URL to a MapLibre style JSON (e.g. a MapTiler or Stadia style, or a
 * self-hosted Protomaps one) to use a real vector basemap. Without it we fall back to OpenStreetMap's
 * public raster tiles, desaturated. OSM's tile server is meant for development and light use only
 * (https://operations.osmfoundation.org/policies/tiles/), so set a real provider before launch.
 */
export const BASEMAP_STYLE_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE_URL;

export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    basemap: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "ground", type: "background", paint: { "background-color": "#d7d3d3" } },
    {
      id: "basemap",
      type: "raster",
      source: "basemap",
      // Strip all colour, and lift it slightly so the route reads clearly on top.
      paint: { "raster-saturation": -1, "raster-contrast": -0.15, "raster-brightness-min": 0.12 },
    },
  ],
};

// Lower Manhattan, the area the routing graph covers.
export const HOME_CENTER: [number, number] = [-73.9915, 40.7185];
export const HOME_ZOOM = 13;
