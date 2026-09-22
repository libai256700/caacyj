export type UniverifyPreparationResult = {
  available: boolean
  reason?: 'unsupported' | 'network'
  preparedAt?: number
}

const UNIVERIFY_STABILITY_WINDOW_MS = 1_200

let preparationPromise: Promise<UniverifyPreparationResult> | null = null
let lastSuccessfulPreparation: UniverifyPreparationResult | null = null

const wait = (durationMs: number) => new Promise<void>((resolve) => {
  setTimeout(resolve, durationMs)
})

/**
 * Starts the carrier SDK before the user opens its authorization page. The
 * promise is shared so application launch and the login screen never make
 * competing pre-login calls.
 */
export const prepareUniverify = (options: { force?: boolean } = {}): Promise<UniverifyPreparationResult> => {
  // #ifdef APP-PLUS
  if (!options.force && lastSuccessfulPreparation) {
    return Promise.resolve(lastSuccessfulPreparation)
  }

  if (preparationPromise) {
    return preparationPromise
  }

  const preparation = new Promise<UniverifyPreparationResult>((resolve) => {
    uni.getProvider({
      service: 'oauth',
      success: (result) => {
        const providers = result.provider as unknown as string[]
        if (!providers.includes('univerify')) {
          resolve({ available: false, reason: 'unsupported' })
          return
        }

        uni.preLogin({
          provider: 'univerify',
          success: () => {
            const prepared = { available: true, preparedAt: Date.now() }
            lastSuccessfulPreparation = prepared
            resolve(prepared)
          },
          fail: () => {
            lastSuccessfulPreparation = null
            resolve({ available: false, reason: 'network' })
          }
        })
      },
      fail: () => {
        lastSuccessfulPreparation = null
        resolve({ available: false, reason: 'unsupported' })
      }
    })
  })

  preparationPromise = preparation
  return preparation.finally(() => {
    if (preparationPromise === preparation) {
      preparationPromise = null
    }
  })
  // #endif

  // #ifndef APP-PLUS
  return Promise.resolve({ available: false, reason: 'unsupported' })
  // #endif
}

/** Wait until a successful carrier pre-login has passed its cold-start window. */
export const waitForUniverifyStability = async (preparedAt?: number) => {
  if (!preparedAt) {
    return
  }

  const remaining = UNIVERIFY_STABILITY_WINDOW_MS - (Date.now() - preparedAt)
  if (remaining > 0) {
    await wait(remaining)
  }
}

/** Allows the carrier authorization page to close before a recovery pre-login. */
export const waitForUniverifyRecovery = () => wait(450)
