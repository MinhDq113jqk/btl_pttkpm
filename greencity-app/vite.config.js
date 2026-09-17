import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export function resolveDevProxyTarget(env = {}) {
  const configured = typeof env.VITE_DEV_API_PROXY_TARGET === 'string'
    ? env.VITE_DEV_API_PROXY_TARGET.trim()
    : '';
  const target = configured || 'http://127.0.0.1:8000';
  let parsed;
  try {
    parsed = new URL(target);
  } catch {
    throw new Error('VITE_DEV_API_PROXY_TARGET must be an absolute http(s) URL');
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('VITE_DEV_API_PROXY_TARGET must be an absolute http(s) URL');
  }
  return target;
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  return {
    plugins: [react()],
    server: {
      port: 3000,
      open: false,
      proxy: {
        '/api/v1': {
          target: resolveDevProxyTarget(env),
          changeOrigin: false
        }
      }
    }
  };
});
