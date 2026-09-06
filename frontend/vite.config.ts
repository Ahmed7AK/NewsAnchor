import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Where the NewsAnchor API is listening. Override when you run the backend on
// a different port, e.g. NEWSANCHOR_API=http://127.0.0.1:9000 npm run dev
const API = process.env.NEWSANCHOR_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy so the browser talks to one origin in development and CORS stays
    // a non-issue.
    proxy: {
      "/api": { target: API, changeOrigin: true },
    },
  },
});
