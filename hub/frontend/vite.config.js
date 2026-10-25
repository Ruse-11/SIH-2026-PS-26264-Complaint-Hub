import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/* is forwarded to the hub backend, so the browser never hits CORS problems in dev.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
