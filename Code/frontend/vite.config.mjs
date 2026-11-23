import { defineConfig } from "vite"
import tailwind from "@tailwindcss/vite"
import { fileURLToPath } from "node:url"
export default defineConfig({
  base: "./",
  plugins: [tailwind()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "../static/auth", emptyOutDir: true, assetsInlineLimit: 0,
    rollupOptions: { input: "src/auth-client.ts", output: {
      entryFileNames: "login.js", assetFileNames: asset => asset.names?.some(n => n.endsWith(".css")) ? "login.css" : "[name][extname]"
    } }
  }
})
