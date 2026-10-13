import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  // The app is served from /meta-morphis/ on GitHub Pages, not from the
  // site root, so it must find its files relative to its own address
  base: './',
  plugins: [react()],
});
