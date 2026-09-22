export function activePageTree(source) {
  const xml = String(source || '')
  const pageRoots = [...xml.matchAll(/<android\.webkit\.WebView\b[^>]*\btext="pages\/[^"\[]+\[\d+\]"/g)]
  const activeRoot = pageRoots.at(-1)
  return activeRoot ? xml.slice(activeRoot.index) : xml
}

export function activePageRoute(source) {
  const match = activePageTree(source).match(/<android\.webkit\.WebView\b[^>]*\btext="pages\/([^"\[]+)\[\d+\]"/)
  return match?.[1] || ''
}

export function activePageMatches(source, pattern) {
  pattern.lastIndex = 0
  return pattern.test(activePageTree(source))
}
