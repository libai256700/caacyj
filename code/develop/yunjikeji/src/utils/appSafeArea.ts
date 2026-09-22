import { getSafeAreaInsets } from './safeArea'

export type AppSafeAreaStyle = Record<string, string>

export const createAppSafeAreaStyle = (): AppSafeAreaStyle => {
  try {
    const roundedSafeAreaTop = Math.ceil(getSafeAreaInsets().top)

    return {
      '--app-safe-area-top': `${roundedSafeAreaTop}px`,
      '--app-safe-area-top-extra': `${Math.max(0, roundedSafeAreaTop - 22)}px`
    }
  } catch {
    return {
      '--app-safe-area-top': '0px',
      '--app-safe-area-top-extra': '0px'
    }
  }
}
