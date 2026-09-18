import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The site is served from the root of its own domain (conectoma.fasl-work.com), so assets and artifacts use
// absolute paths. A relative base breaks on deep routes: /methodology/ would resolve ./assets against itself.
export default defineConfig({
  base: '/',
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1500 },
  test: { environment: 'node', globals: true },
});
