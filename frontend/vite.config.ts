import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Geliştirmede API ve SSE istekleri FastAPI'ye aktarılır; böylece çerez aynı kökende kalır.
// Varsayılan 8000; port doluysa HKY_API_URL=http://127.0.0.1:8001 ile değiştirilebilir.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
const apiTarget = env?.HKY_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
});
