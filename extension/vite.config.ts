import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { crx } from "@crxjs/vite-plugin";
import manifest from "./manifest.json" with { type: "json" };

export default defineConfig({
  plugins: [react(), crx({ manifest })],
  server: {
    port: 5173,
    strictPort: true,
    hmr: { port: 5173 },
  },
  build: {
    rollupOptions: {
      input: {
        // Offscreen documents are created dynamically via chrome.offscreen.createDocument()
        // rather than declared in manifest.json, so crxjs can't discover this entry on its
        // own — it must be listed explicitly.
        offscreen: "src/offscreen/offscreen.html",
        // AudioWorklet modules are loaded via audioWorklet.addModule(url) at runtime, not
        // via a static import — Vite only special-cases `new Worker(new URL(...))` for
        // that pattern, so without an explicit entry this file would get inlined as a raw,
        // untranspiled asset instead of being compiled. Built to a fixed filename (see
        // entryFileNames below) so the runtime URL doesn't depend on a content hash.
        "pcm-processor": "src/offscreen/pcm-processor.worklet.ts",
        // Injected programmatically via chrome.scripting.executeScript({files:[...]}),
        // which requires a plain classic (non-module) script with a stable, known
        // path — same fixed-filename reasoning as pcm-processor above.
        "content-script": "src/content/content-script.ts",
      },
      output: {
        entryFileNames: (chunkInfo) =>
          ["pcm-processor", "content-script"].includes(chunkInfo.name ?? "")
            ? "assets/[name].js"
            : "assets/[name]-[hash].js",
      },
    },
  },
});
