import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// THE ROOM builds to console/room/, which the gateway's stdlib static handler
// serves at /room/. Node is a BUILD-time dependency only — nothing in the running
// stack needs it, and pyproject.toml's `dependencies = []` stays true.
//
// base:'/room/' matters: without it the built index.html asks for /assets/*.js and
// the flat-filename handler refuses, which looks exactly like a broken build.
export default defineConfig({
  plugins: [react()],
  base: '/room/',
  build: {
    outDir: '../console/room',
    emptyOutDir: true,
    // one file each, so the whole room is two assets the handler can serve
    rollupOptions: { output: { manualChunks: undefined } },
  },
  server: { proxy: { '/v1': 'http://127.0.0.1:8800' } },
})
