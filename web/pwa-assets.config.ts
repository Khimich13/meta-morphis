import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config';

// `npm run icons` turns public/icon.svg into the PNG sizes phones ask for
export default defineConfig({
  preset: minimal2023Preset,
  images: ['public/icon.svg'],
});
