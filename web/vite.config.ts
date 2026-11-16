import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

// T-01 : une seule base de code, installable (PWA). Les appels /api partent vers FastAPI en développement.
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Mes collections de cartes",
        short_name: "Collections",
        description: "Suivez vos collections de cartes à partir des listes officielles.",
        lang: "fr",
        display: "standalone",
        start_url: "/collections",
        background_color: "#F4F5F0",
        theme_color: "#F4F5F0",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // Checklist d'une série, demandée avec sa version : ne change jamais.
            urlPattern: /\/api\/v1\/catalog\/series\/\d+\/cards\?v=\d+/,
            handler: "CacheFirst",
            options: { cacheName: "checklists", expiration: { maxEntries: 60 } },
          },
          {
            // ENF-06 : consultation hors ligne des collections déjà chargées.
            urlPattern: /\/api\/v1\/(collections|catalog|me$|isolated|purchases)/,
            method: "GET",
            handler: "NetworkFirst",
            options: { cacheName: "donnees", networkTimeoutSeconds: 4, expiration: { maxEntries: 120 } },
          },
          {
            urlPattern: /\/api\/v1\/photos\//,
            handler: "CacheFirst",
            options: { cacheName: "photos", expiration: { maxEntries: 400, maxAgeSeconds: 30 * 86400 } },
          },
        ],
      },
    }),
  ],
  test: { environment: "node" },
});
