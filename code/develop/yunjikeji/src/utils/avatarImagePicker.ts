export type PickedAvatarImage = {
  filePath: string
  fileName: string
  rawFile?: File | Blob
}

type PickedImageFile = {
  name?: string
  path?: string
  tempFilePath?: string
}

const firstPickedFile = (tempFiles: unknown): unknown => {
  if (Array.isArray(tempFiles)) {
    return tempFiles[0]
  }
  return tempFiles
}

const readPickedImageFile = (value: unknown) => value as PickedImageFile | undefined

// #ifdef H5
const isBrowserUploadSource = (value: unknown): value is File | Blob =>
  (typeof File !== 'undefined' && value instanceof File) ||
  (typeof Blob !== 'undefined' && value instanceof Blob)
// #endif

/**
 * Normalizes only the selected platform's image-picker result. App-Plus
 * supplies a native local path, while H5 retains the browser File/Blob.
 */
export const chooseAvatarImageFile = () =>
  new Promise<PickedAvatarImage>((resolve, reject) => {
    uni.chooseImage({
      count: 1,
      sourceType: ['album', 'camera'],
      success: (result) => {
        // #ifdef APP-PLUS
        {
          const pickedFile = readPickedImageFile(firstPickedFile(result.tempFiles))
          const filePath = result.tempFilePaths?.[0] || pickedFile?.tempFilePath || pickedFile?.path || ''
          if (!filePath) {
            reject(new Error('未选择头像图片'))
            return
          }
          resolve({
            filePath,
            fileName: pickedFile?.name || 'avatar.jpg'
          })
          return
        }
        // #endif

        // #ifdef H5
        {
          const pickedFile = firstPickedFile(result.tempFiles)
          let rawFile: File | Blob | undefined
          if (isBrowserUploadSource(pickedFile)) {
            rawFile = pickedFile as File | Blob
          }
          const fileMetadata = readPickedImageFile(pickedFile)
          const filePath = result.tempFilePaths?.[0] || fileMetadata?.path || ''
          if (!filePath && !rawFile) {
            reject(new Error('未选择头像图片'))
            return
          }
          resolve({
            filePath,
            fileName: fileMetadata?.name || 'avatar.jpg',
            rawFile
          })
          return
        }
        // #endif

        reject(new Error('当前平台不支持头像选择'))
      },
      fail: () => reject(new Error('未选择头像图片'))
    })
  })
