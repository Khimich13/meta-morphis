import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  // The app is served from /meta-morphis/ on GitHub Pages, not from the
  // site root, so it must find its files relative to its own address
  base: './',
  plugins: [
    react(),
    // Makes the app installable and usable offline: writes the manifest
    // and generates the service worker during `npm run build`
    VitePWA({
      // A new version replaces the saved one by itself, with no prompt
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'icon.svg', 'apple-touch-icon-180x180.png'],
      // What the phone shows when the app is installed
      manifest: {
        name: 'MetaMorphis',
        short_name: 'MetaMorphis',
        description: 'Learn the most played Magic: The Gathering cards of a format.',
        start_url: './',
        scope: './',
        // Full screen, without the browser's address bar
        display: 'standalone',
        background_color: '#1f2a44',
        theme_color: '#1f2a44',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'maskable-icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // The app itself: saved on the first visit, then always served
        // from the saved copy
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        runtimeCaching: [
          {
            // The card list: fresh from the network when there is one,
            // otherwise the copy saved last time
            urlPattern: /\/data\/[^/]+\.json$/,
            handler: 'NetworkFirst',
            options: { cacheName: 'card-data', networkTimeoutSeconds: 3 },
          },
          {
            // Card pictures: the saved copy if there is one. The cache
            // name must match PICTURE_CACHE in src/offline.ts, which
            // fills this cache ahead of time.
            urlPattern: /^https:\/\/cards\.scryfall\.io\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'card-pictures',
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],
});
