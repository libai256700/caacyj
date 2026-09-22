const encodeFormComponent = (value: string) => encodeURIComponent(value).replace(/%20/g, '+')

export const buildQueryString = (payload: Record<string, unknown>) => {
  const pairs: string[] = []

  const appendValue = (key: string, value: unknown) => {
    if (value === undefined || value === null) {
      return
    }
    if (Array.isArray(value)) {
      value.forEach((item, index) => appendValue(`${key}[${index}]`, item))
      return
    }
    if (value instanceof Date) {
      pairs.push(`${encodeFormComponent(key)}=${encodeFormComponent(value.toISOString())}`)
      return
    }
    if (typeof value === 'object') {
      Object.entries(value).forEach(([childKey, childValue]) => {
        appendValue(`${key}.${childKey}`, childValue)
      })
      return
    }
    pairs.push(`${encodeFormComponent(key)}=${encodeFormComponent(String(value))}`)
  }

  Object.entries(payload).forEach(([key, value]) => appendValue(key, value))
  return pairs.join('&')
}

export const appendQueryString = (url: string, payload: Record<string, unknown>) => {
  const query = buildQueryString(payload)
  if (!query) {
    return url
  }
  return `${url}${url.includes('?') ? '&' : '?'}${query}`
}

export const buildAbsoluteWebSocketUrl = (baseUrl: string, path: string, query?: Record<string, unknown>) => {
  const normalizedBase = baseUrl.replace(/\/$/, '')
  const protocol = normalizedBase.startsWith('https://') ? 'wss://' : 'ws://'
  const withoutProtocol = normalizedBase.replace(/^https?:\/\//, '')
  const slashIndex = withoutProtocol.indexOf('/')
  const host = slashIndex >= 0 ? withoutProtocol.slice(0, slashIndex) : withoutProtocol
  const basePath = slashIndex >= 0 ? withoutProtocol.slice(slashIndex).replace(/\/$/, '') : ''
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return appendQueryString(`${protocol}${host}${basePath}${normalizedPath}`, query || {})
}
