export type SafeAreaInsets = {
  top: number
  right: number
  bottom: number
  left: number
}

// Some older uni-app Android bases report all safe-area fields as zero during
// the first WebView frame. Keep the first native frame below the status bar;
// later reads replace this conservative value with the real inset.
const NATIVE_SAFE_TOP_FALLBACK = 44

type PlusRuntime = {
  navigator?: {
    getStatusbarHeight?: () => number
  }
  android?: {
    invoke?: (object: unknown, method: string, ...args: unknown[]) => unknown
    runtimeMainActivity?: () => unknown
  }
}

const readWindowInsets = (): Partial<SafeAreaInsets> => {
  const getWindowInfo = (uni as typeof uni & {
    getWindowInfo?: () => {
      safeAreaInsets?: Partial<SafeAreaInsets>
    }
  }).getWindowInfo

  if (typeof getWindowInfo !== 'function') {
    return {}
  }

  return getWindowInfo().safeAreaInsets || {}
}

const readNativeCutoutTop = (density: number) => {
  const plusRuntime = (globalThis as typeof globalThis & { plus?: PlusRuntime }).plus
  const android = plusRuntime?.android
  if (!android?.invoke || !android.runtimeMainActivity) {
    return 0
  }

  try {
    const invoke = android.invoke
    const activity = android.runtimeMainActivity()
    const window = invoke(activity, 'getWindow')
    const decorView = invoke(window, 'getDecorView')
    const windowInsets = invoke(decorView, 'getRootWindowInsets')
    const displayCutout = invoke(windowInsets, 'getDisplayCutout')
    const safeInsetTop = Number(invoke(displayCutout, 'getSafeInsetTop') || 0)
    return safeInsetTop / density
  } catch {
    return 0
  }
}

const toInset = (value: unknown) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0
}

export const getSafeAreaInsets = (): SafeAreaInsets => {
  type ExtendedSystemInfo = {
    statusBarHeight?: number
    pixelRatio?: number
    platform?: string
    safeArea?: Partial<{ top: number; right: number; bottom: number; left: number }>
    safeAreaInsets?: Partial<SafeAreaInsets>
  }

  const systemInfo = uni.getSystemInfoSync() as unknown as ExtendedSystemInfo
  const windowInsets = readWindowInsets()
  const plusRuntime = (globalThis as typeof globalThis & { plus?: PlusRuntime }).plus
  const nativeStatusBarHeight = toInset(plusRuntime?.navigator?.getStatusbarHeight?.())
  const nativeCutoutTop = readNativeCutoutTop(toInset(systemInfo.pixelRatio) || 1)
  const systemSafeArea = systemInfo.safeArea || {}
  const systemSafeAreaInsets = systemInfo.safeAreaInsets || {}
  const isNativeApp = ['android', 'ios', 'harmony'].includes(String(systemInfo.platform || '').toLowerCase())

  try {
    const getWindowInfo = (uni as typeof uni & {
      getWindowInfo?: () => {
        statusBarHeight?: number
        windowWidth?: number
        windowHeight?: number
        safeArea?: Partial<{ top: number; right: number; bottom: number; left: number }>
        safeAreaInsets?: Partial<SafeAreaInsets>
      }
    }).getWindowInfo

    const windowInfo = typeof getWindowInfo === 'function' ? getWindowInfo() : {}
    const safeArea = windowInfo.safeArea || systemSafeArea
    const reportedInsets = windowInfo.safeAreaInsets || systemSafeAreaInsets
    const windowWidth = toInset(windowInfo.windowWidth)
    const windowHeight = toInset(windowInfo.windowHeight)
    const fallbackTop = isNativeApp ? NATIVE_SAFE_TOP_FALLBACK : 0

    return {
      top: Math.max(
        fallbackTop,
        toInset(systemInfo.statusBarHeight),
        toInset(windowInfo.statusBarHeight),
        toInset(reportedInsets?.top),
        toInset(safeArea?.top),
        toInset(windowInsets.top),
        nativeStatusBarHeight,
        nativeCutoutTop
      ),
      right: Math.max(
        toInset(reportedInsets?.right),
        toInset(windowInsets.right),
        safeArea && windowWidth ? toInset(windowWidth - safeArea.right) : 0
      ),
      bottom: Math.max(
        toInset(reportedInsets?.bottom),
        toInset(windowInsets.bottom),
        safeArea && windowHeight ? toInset(windowHeight - safeArea.bottom) : 0
      ),
      left: Math.max(toInset(reportedInsets?.left), toInset(safeArea?.left), toInset(windowInsets.left))
    }
  } catch {
    return {
      top: Math.max(
        toInset(systemInfo.statusBarHeight),
        toInset(systemSafeArea.top),
        toInset(systemSafeAreaInsets.top),
        toInset(windowInsets.top),
        nativeStatusBarHeight,
        nativeCutoutTop,
        isNativeApp ? NATIVE_SAFE_TOP_FALLBACK : 0
      ),
      right: Math.max(toInset(systemSafeAreaInsets.right), toInset(windowInsets.right)),
      bottom: Math.max(toInset(systemSafeAreaInsets.bottom), toInset(windowInsets.bottom)),
      left: Math.max(toInset(systemSafeAreaInsets.left), toInset(windowInsets.left))
    }
  }
}

export const applySafeAreaVariables = () => {
  const insets = getSafeAreaInsets()
  if (typeof document === 'undefined') {
    return insets
  }

  const rootStyle = document.documentElement.style
  rootStyle.setProperty('--app-safe-top', `${Math.ceil(insets.top)}px`)
  rootStyle.setProperty('--app-safe-area-top', `${Math.ceil(insets.top)}px`)
  rootStyle.setProperty('--app-safe-right', `${Math.ceil(insets.right)}px`)
  rootStyle.setProperty('--app-safe-bottom', `${Math.ceil(insets.bottom)}px`)
  rootStyle.setProperty('--app-safe-left', `${Math.ceil(insets.left)}px`)
  return insets
}
