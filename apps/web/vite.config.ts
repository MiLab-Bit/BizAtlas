import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5174,
    proxy: {
      // 本地 API；若 8000 被僵死进程占用可改用 8010
      "/v1": process.env.VITE_API_PROXY ?? "http://127.0.0.1:8010",
    },
  },
});
