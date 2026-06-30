// vite.config.js
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    outDir: 'static/dist',
    manifest: true,
    rollupOptions: {
      input: {
        admin_css: resolve(__dirname, 'static/css/design-tokens.css'),
        layout_css: resolve(__dirname, 'static/css/layout.css'),
        components_css: resolve(__dirname, 'static/css/components.css'),
        utilities_css: resolve(__dirname, 'static/css/utilities.css'),
        admin_js: resolve(__dirname, 'static/js/admin_components.js'),
        core_js: resolve(__dirname, 'static/js/core/dataFetcher.js')
      }
    }
  }
});
