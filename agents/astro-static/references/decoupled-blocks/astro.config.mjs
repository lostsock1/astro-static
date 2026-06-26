import { defineConfig } from "astro/config";

// Lean static output — no SSR adapter, no client runtime.
// Astro reads the markdown content directly; Tina only touches the admin.
export default defineConfig({
  output: "static",
});
