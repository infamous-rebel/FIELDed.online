import { defineConfig } from "vite";
import vinext from "vinext";
import { cloudflare } from "@cloudflare/vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import { cdnAdapter } from "@vinext/cloudflare/cache/cdn-adapter";

export default defineConfig({
  plugins: [
    tailwindcss(),
    vinext({
      cache: { cdn: cdnAdapter() },
    }),
    cloudflare({
      viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
    }),
  ],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
