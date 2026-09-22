import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { deflateRawSync } from 'node:zlib'

const workspaceRoot = path.resolve(import.meta.dirname, '../../..')
const apkDir = path.join(workspaceRoot, 'code/develop/yunjikeji/dist/release/apk')
const artifactDir = path.join(workspaceRoot, 'code/develop/安装包')
const sourceCandidates = [
  process.env.UNI_APP_ASSETS_DIR,
  path.join(workspaceRoot, 'code/develop/yunjikeji/dist/build/app'),
  path.join(workspaceRoot, 'code/develop/yunjikeji/dist/dev/app-plus'),
  path.join(workspaceRoot, 'code/develop/yunjikeji/dist/release/app-plus'),
].filter(Boolean)
const sourceDir = sourceCandidates.find((candidate) => fs.existsSync(candidate))
const baseDirectories = process.env.APK_BASE_DIR
  ? [process.env.APK_BASE_DIR]
  : [apkDir, artifactDir]
const keystore = path.join(workspaceRoot, 'doc/01-生产现状/02-开发现状/1fbc8fdaa7294ad6afc609326e2800f6.keystore')
const androidSdk = process.env.ANDROID_HOME
  || process.env.ANDROID_SDK_ROOT
  || path.join(process.env.LOCALAPPDATA || '', 'Android/Sdk')
const buildTools = process.env.ANDROID_BUILD_TOOLS || path.join(androidSdk, 'build-tools/35.0.0')
const zipalign = process.env.ZIPALIGN_PATH || path.join(buildTools, 'zipalign.exe')
const apksigner = process.env.APKSIGNER_PATH || path.join(buildTools, 'lib/apksigner.jar')
const java = process.env.JAVA_HOME ? path.join(process.env.JAVA_HOME, 'bin/java.exe') : 'java'

fs.mkdirSync(apkDir, { recursive: true })
fs.mkdirSync(artifactDir, { recursive: true })

const entries = baseDirectories
  .filter((directory) => fs.existsSync(directory))
  .flatMap((directory) => fs.readdirSync(directory)
    .filter((name) => name.toLowerCase().endsWith('.apk'))
    .map((name) => ({ name, file: path.join(directory, name), stat: fs.statSync(path.join(directory, name)) })))
  // The original HBuilderX base contains native libraries and resources.arsc.
  // Exclude incomplete artifacts from an interrupted local rewrite.
  .filter(({ stat }) => stat.size > 40_000_000)
  .sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs || b.stat.size - a.stat.size)
if (!entries.length) throw new Error(`No complete base APK found in: ${baseDirectories.join(', ')}`)
if (!sourceDir) throw new Error(`Build resources not found in: ${sourceCandidates.join(', ')}`)
for (const requiredFile of [keystore, zipalign, apksigner]) {
  if (!fs.existsSync(requiredFile)) throw new Error(`Required packaging file not found: ${requiredFile}`)
}

const now = new Date()
const stamp = [
  now.getFullYear(),
  String(now.getMonth() + 1).padStart(2, '0'),
  String(now.getDate()).padStart(2, '0'),
  String(now.getHours()).padStart(2, '0'),
  String(now.getMinutes()).padStart(2, '0'),
  String(now.getSeconds()).padStart(2, '0'),
].join('')
const preferredBaseName = '__UNI__F4DBB06__20260824160242.apk'
const base = entries.find(({ name }) => name === preferredBaseName)?.file || entries[0].file
const raw = path.join(apkDir, `__UNI__F4DBB06__${stamp}.raw.apk`)
const aligned = path.join(apkDir, `__UNI__F4DBB06__${stamp}.aligned.apk`)
const output = path.join(apkDir, `__UNI__F4DBB06__${stamp}.apk`)
const artifact = path.join(artifactDir, `yunjikeji-app-test-${stamp.slice(0, 8)}-${stamp.slice(8)}.apk`)

function crc32(data) {
  let crc = 0xffffffff
  for (const byte of data) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function findEndOfCentralDirectory(buffer) {
  for (let offset = buffer.length - 22; offset >= Math.max(0, buffer.length - 0xffff - 22); offset -= 1) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) return offset
  }
  throw new Error('ZIP end of central directory not found')
}

function isReplacedEntry(name) {
  return name.startsWith('assets/apps/__UNI__F4DBB06/www/')
    || /^META-INF\/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA))$/i.test(name)
}

function listFiles(directory, relative = '') {
  const files = []
  for (const entry of fs.readdirSync(path.join(directory, relative), { withFileTypes: true })) {
    const child = path.join(relative, entry.name)
    if (entry.isDirectory()) files.push(...listFiles(directory, child))
    else files.push({ absolute: path.join(directory, child), name: child.replaceAll(path.sep, '/') })
  }
  return files
}

function createNewZip(baseBuffer) {
  const eocdOffset = findEndOfCentralDirectory(baseBuffer)
  const centralDirectoryOffset = baseBuffer.readUInt32LE(eocdOffset + 16)
  const entryCount = baseBuffer.readUInt16LE(eocdOffset + 10)
  let centralOffset = centralDirectoryOffset
  let outputOffset = 0
  const localParts = []
  const centralParts = []

  for (let index = 0; index < entryCount; index += 1) {
    if (baseBuffer.readUInt32LE(centralOffset) !== 0x02014b50) throw new Error('Invalid ZIP central directory')
    const nameLength = baseBuffer.readUInt16LE(centralOffset + 28)
    const extraLength = baseBuffer.readUInt16LE(centralOffset + 30)
    const commentLength = baseBuffer.readUInt16LE(centralOffset + 32)
    const centralLength = 46 + nameLength + extraLength + commentLength
    const name = baseBuffer.subarray(centralOffset + 46, centralOffset + 46 + nameLength).toString()
    const localEntryOffset = baseBuffer.readUInt32LE(centralOffset + 42)
    const localNameLength = baseBuffer.readUInt16LE(localEntryOffset + 26)
    const localExtraLength = baseBuffer.readUInt16LE(localEntryOffset + 28)
    // Some HBuilderX APKs put sizes only in the central directory and leave
    // zeroes in the local header when a data descriptor is used.
    const compressedLength = baseBuffer.readUInt32LE(centralOffset + 20)
    const localDataEnd = localEntryOffset + 30 + localNameLength + localExtraLength + compressedLength
    const hasDataDescriptor = (baseBuffer.readUInt16LE(localEntryOffset + 6) & 0x08) !== 0
    const descriptorLength = hasDataDescriptor
      ? (baseBuffer.readUInt32LE(localDataEnd) === 0x08074b50 ? 16 : 12)
      : 0
    const localLength = 30 + localNameLength + localExtraLength + compressedLength + descriptorLength

    if (!isReplacedEntry(name) && !name.endsWith('/')) {
      localParts.push(baseBuffer.subarray(localEntryOffset, localEntryOffset + localLength))
      const centralEntry = Buffer.from(baseBuffer.subarray(centralOffset, centralOffset + centralLength))
      centralEntry.writeUInt32LE(outputOffset, 42)
      centralParts.push(centralEntry)
      outputOffset += localLength
    }
    centralOffset += centralLength
  }

  for (const file of listFiles(sourceDir)) {
    const name = `assets/apps/__UNI__F4DBB06/www/${file.name}`
    const nameBuffer = Buffer.from(name)
    const data = fs.readFileSync(file.absolute)
    const compressed = deflateRawSync(data, { level: 9 })
    const checksum = crc32(data)
    const local = Buffer.alloc(30 + nameBuffer.length)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0, 6)
    local.writeUInt16LE(8, 8)
    local.writeUInt32LE(0, 10)
    local.writeUInt32LE(checksum, 14)
    local.writeUInt32LE(compressed.length, 18)
    local.writeUInt32LE(data.length, 22)
    local.writeUInt16LE(nameBuffer.length, 26)
    local.writeUInt16LE(0, 28)
    nameBuffer.copy(local, 30)
    localParts.push(local, compressed)

    const central = Buffer.alloc(46 + nameBuffer.length)
    central.writeUInt32LE(0x02014b50, 0)
    central.writeUInt16LE(20, 4)
    central.writeUInt16LE(20, 6)
    central.writeUInt16LE(0, 8)
    central.writeUInt16LE(8, 10)
    central.writeUInt32LE(0, 12)
    central.writeUInt32LE(checksum, 16)
    central.writeUInt32LE(compressed.length, 20)
    central.writeUInt32LE(data.length, 24)
    central.writeUInt16LE(nameBuffer.length, 28)
    central.writeUInt32LE(outputOffset, 42)
    nameBuffer.copy(central, 46)
    centralParts.push(central)
    outputOffset += local.length + compressed.length
  }

  const localData = Buffer.concat(localParts)
  const centralData = Buffer.concat(centralParts)
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0)
  eocd.writeUInt16LE(0, 4)
  eocd.writeUInt16LE(0, 6)
  eocd.writeUInt16LE(centralParts.length, 8)
  eocd.writeUInt16LE(centralParts.length, 10)
  eocd.writeUInt32LE(centralData.length, 12)
  eocd.writeUInt32LE(localData.length, 16)
  return Buffer.concat([localData, centralData, eocd])
}

fs.writeFileSync(raw, createNewZip(fs.readFileSync(base)))

execFileSync(zipalign, ['-p', '-f', '4', raw, aligned], { stdio: 'inherit' })
execFileSync(java, [
  '-jar', apksigner, 'sign',
  '--ks', keystore,
  '--ks-key-alias', 'com.caacyj.app',
  '--ks-pass', 'pass:caacyj123456',
  '--key-pass', 'pass:caacyj123456',
  '--out', output,
  aligned,
], { stdio: 'inherit' })

fs.rmSync(raw, { force: true })
fs.rmSync(aligned, { force: true })
fs.copyFileSync(output, artifact)
console.log(artifact)
