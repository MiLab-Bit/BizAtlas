import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
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
  build: {
    rollupOptions: {
      output: {
        // C1：按依赖分组分包，降低首屏单包体积 + 提升缓存粒度
        // pnpm 布局注意：模块 id 形如 .../node_modules/.pnpm/<pkg>@<ver>/node_modules/<pkg>/...
        // 必须取最后一个 node_modules/ 之后的真实包名——早年按第一段取会得到 ".pnpm"，
        // 导致全部依赖被并成一个 vendor-.pnpm 巨块（3MB+，缓存零粒度）。
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return;
          const seg = id.split("node_modules/").pop()!.split("/");
          const name = seg[0].startsWith("@") ? `${seg[0]}/${seg[1]}` : seg[0];
          if (/^(react|react-dom|scheduler)$/.test(name)) return "vendor-react";
          if (/^(echarts|echarts-for-react|zrender)$/.test(name)) return "vendor-charts";
          if (/^(@antv|@xyflow)/.test(name)) return "vendor-graph";
          if (/^@radix-ui/.test(name)) return "vendor-radix";
          return "vendor-misc";
        },
      },
    },
  },
});
