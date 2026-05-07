import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// SPA mounted at /app/* by Flask. The `base` ensures every emitted
// asset URL is prefixed with /app/ so assets resolve correctly when
// served from that subpath in production. The dev server proxies
// /api/v2/* to the running Flask app on :5000, mirroring the prod
// dispatcher so client code can use the same URLs in both modes.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/v2": {
        target: "http://localhost:5000",
        changeOrigin: false,
      },
      // Static assets the SPA reuses from Flask (logos, design-tokens
      // CSS) live at /static/* on the Flask app; proxy them in dev so
      // SPA imports of /static/... work without CORS.
      "/static": {
        target: "http://localhost:5000",
        changeOrigin: false,
      },
    },
  },
});
