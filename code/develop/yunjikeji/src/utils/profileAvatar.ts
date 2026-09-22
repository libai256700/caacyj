export const PROFILE_STORAGE_KEY = 'yunjikeji-profile-page-standard'
export const DEFAULT_PROFILE_AVATAR_ID = '/static/profile-settings/default-student-avatar-blue.png'

const legacyProfileAvatarIds = [
  'sky',
  'mint',
  'violet',
  '/static/profile-settings/default-student-avatar.png'
] as const

const readStoredProfile = () => {
  const stored = uni.getStorageSync(PROFILE_STORAGE_KEY)
  return stored && typeof stored === 'object' ? (stored as Record<string, unknown>) : {}
}

export const normalizeProfileAvatarId = (value?: string) => {
  const normalized = (value || '').trim()
  const isLegacyAvatar = legacyProfileAvatarIds.some(
    (avatarId) => avatarId === normalized || (avatarId.startsWith('/') && normalized.includes(avatarId))
  )
  return normalized && !isLegacyAvatar
    ? normalized
    : DEFAULT_PROFILE_AVATAR_ID
}

export const readStoredProfileAvatarId = () => {
  const stored = readStoredProfile()
  return normalizeProfileAvatarId(typeof stored.avatarId === 'string' ? stored.avatarId : '')
}

export const cacheProfileAvatarId = (avatarId?: string) => {
  const normalized = normalizeProfileAvatarId(avatarId)
  uni.setStorageSync(PROFILE_STORAGE_KEY, {
    ...readStoredProfile(),
    avatarId: normalized
  })
  return normalized
}
