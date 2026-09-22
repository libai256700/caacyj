import { defineConfig, loadEnv } from "vite";
import uni from "@dcloudio/vite-plugin-uni";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const uniPlatform = process.env.UNI_PLATFORM || env.UNI_PLATFORM || ''
  const devHost = env.VITE_DEV_HOST || process.env.VITE_DEV_HOST || '0.0.0.0'
  const devProxyTarget = env.VITE_DEV_PROXY_TARGET || process.env.VITE_DEV_PROXY_TARGET || 'https://xiaojiapp.caacyj.com'
  const devProxyPrefix = env.VITE_DEV_PROXY_PREFIX
    ?? process.env.VITE_DEV_PROXY_PREFIX
    ?? (devProxyTarget.includes('127.0.0.1') || devProxyTarget.includes('localhost') ? '' : '/yunjikeji-api')
  const yjAppDevProxyTarget = env.VITE_YJ_APP_DEV_PROXY_TARGET || process.env.VITE_YJ_APP_DEV_PROXY_TARGET || 'https://xiaojiapp.caacyj.com'
  const yjAppDevProxyPrefix = env.VITE_YJ_APP_DEV_PROXY_PREFIX
    ?? process.env.VITE_YJ_APP_DEV_PROXY_PREFIX
    ?? (yjAppDevProxyTarget.includes('127.0.0.1') || yjAppDevProxyTarget.includes('localhost') ? '' : '/yunjikeji-admin-api')
  const publicBase = env.VITE_APP_PUBLIC_BASE
    || process.env.VITE_APP_PUBLIC_BASE
    || (uniPlatform === 'h5' ? (env.VITE_H5_PUBLIC_BASE || process.env.VITE_H5_PUBLIC_BASE || '/yunjikeji/') : './')
  const createProxy = (localPrefix: string, target: string, targetPrefix: string, ws = false) => ({
    target,
    changeOrigin: true,
    secure: true,
    ws,
    rewrite: (path: string) => path.replace(new RegExp(`^${localPrefix}`), targetPrefix)
  })

  return {
    base: publicBase,
    css: {
      preprocessorOptions: {
        scss: {
          silenceDeprecations: ['legacy-js-api', 'import', 'global-builtin']
        }
      }
    },
    server: {
      host: devHost,
      proxy: {
        '/local-question-api': createProxy('/local-question-api', 'http://127.0.0.1:48080', ''),
        '/dev-api': createProxy('/dev-api', devProxyTarget, devProxyPrefix),
        '/yunjikeji-api': createProxy('/yunjikeji-api', devProxyTarget, devProxyPrefix),
        '/yj-app-api': createProxy('/yj-app-api', yjAppDevProxyTarget, yjAppDevProxyPrefix, true),
        '/yunjikeji-admin-api': createProxy('/yunjikeji-admin-api', yjAppDevProxyTarget, yjAppDevProxyPrefix, true)
      }
    },
    plugins: [uni()]
  }
});
