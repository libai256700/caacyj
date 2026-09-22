const DEFAULT_DEV_API_BASE_URL = '/dev-api'
const DEFAULT_PROD_API_BASE_URL = 'https://xiaojiapp.caacyj.com/yunjikeji-api'
const DEFAULT_PROD_YJ_APP_API_BASE_URL = 'https://xiaojiapp.caacyj.com/yunjikeji-admin-api'
const DEFAULT_DEV_YJ_APP_API_BASE_URL = '/yj-app-api'
const LOCAL_PROXY_BASE_URL_PATTERN = /^\/(?!\/)/

export const getApiBaseUrl = () => {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

  if (configuredBaseUrl && !LOCAL_PROXY_BASE_URL_PATTERN.test(configuredBaseUrl)) {
    return configuredBaseUrl.replace(/\/$/, '')
  }

  // #ifdef H5
  if (configuredBaseUrl) {
    return configuredBaseUrl.replace(/\/$/, '')
  }

  if (import.meta.env.DEV) {
    return DEFAULT_DEV_API_BASE_URL
  }
  // #endif

  return DEFAULT_PROD_API_BASE_URL
}

export const getYjAppApiBaseUrl = () => {
  const configuredBaseUrl = import.meta.env.VITE_YJ_APP_API_BASE_URL?.trim()

  if (configuredBaseUrl && !LOCAL_PROXY_BASE_URL_PATTERN.test(configuredBaseUrl)) {
    return configuredBaseUrl.replace(/\/$/, '')
  }

  // #ifdef H5
  if (configuredBaseUrl) {
    return configuredBaseUrl.replace(/\/$/, '')
  }

  if (import.meta.env.DEV) {
    return DEFAULT_DEV_YJ_APP_API_BASE_URL
  }
  // #endif

  return DEFAULT_PROD_YJ_APP_API_BASE_URL
}
