import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on 5173 (matches backend CORS allow-list in config.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // needed so the container / other hosts can reach the dev server
  },
});
