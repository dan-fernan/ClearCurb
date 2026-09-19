// MapLibre v6 finds its web worker with new URL("./maplibre-gl-worker.mjs", import.meta.url), i.e. "next to
// my own file". Once a bundler folds maplibre-gl into a chunk, that path 404s and every GeoJSON/vector layer
// silently stays empty (only raster tiles, which load on the main thread, still work).
// So serve the worker and the shared module it imports from /public and point MapLibre at them
// (see setWorkerUrl in src/components/MapView.tsx). Copying from node_modules keeps them in step with the
// installed version.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const from = join(root, "node_modules", "maplibre-gl", "dist");
const to = join(root, "public", "maplibre");

mkdirSync(to, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(from, file), join(to, file));
}
console.log("copied MapLibre worker files to public/maplibre/");
