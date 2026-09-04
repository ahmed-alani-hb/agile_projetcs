import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true, // dev-only proxy for /api, /assets, /login → bench port
      lucideIcons: true,
      jinjaBootData: true, // injects window["<key>"] = {{ boot[key] | tojson }} into the BUILT html
      buildConfig: {
        indexHtmlPath: '../agile_projects/www/agile.html',
        outDir: '../agile_projects/public/frontend',
        baseUrl: '/assets/agile_projects/frontend/',
        emptyOutDir: true,
        sourcemap: true,
      },
    }),
    vue(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // frappe-gantt's package exports map blocks deep imports, so the
      // stylesheet is aliased rather than vendored into src/
      'frappe-gantt-css': path.resolve(
        __dirname,
        'node_modules/frappe-gantt/dist/frappe-gantt.css'
      ),
    },
  },
})
