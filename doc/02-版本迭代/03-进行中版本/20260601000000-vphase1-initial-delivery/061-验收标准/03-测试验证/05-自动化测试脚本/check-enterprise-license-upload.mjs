import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptPath = fileURLToPath(import.meta.url)
const scriptDir = path.dirname(scriptPath)
const repoRoot = path.resolve(scriptDir, '..', '..', '..', '..', '..', '..', '..')
const outputFile = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve(scriptDir, '..', 'DEV-024', 'front-static-check.json')

const customerAuthPath = path.resolve(repoRoot, 'code', 'develop', 'yunjikeji', 'src', 'services', 'customerAuth.ts')
const registerPath = path.resolve(repoRoot, 'code', 'develop', 'yunjikeji', 'src', 'pages', 'enterprise', 'register.vue')

const customerAuth = readFileSync(customerAuthPath, 'utf8')
const registerVue = readFileSync(registerPath, 'utf8')

const enterpriseUploadConst = "const ENTERPRISE_LICENSE_UPLOAD_PATH = '/app-api/yj/enterprise-audit/license/upload'"
const enterpriseUploadStart = customerAuth.indexOf('export const uploadEnterpriseLicenseImage')
const enterpriseUploadEnd = customerAuth.indexOf('export const submitStudentAudit', enterpriseUploadStart)
const enterpriseUploadBlock = customerAuth.slice(enterpriseUploadStart, enterpriseUploadEnd)

const submitStart = registerVue.indexOf('const submitRegistration = async () => {')
const ensureUploadIndex = registerVue.indexOf('await ensureLicenseUploaded()', submitStart)
const saveIndex = registerVue.indexOf('saveEnterpriseAudit(', submitStart)
const submitIndex = registerVue.indexOf('submitEnterpriseAudit(', saveIndex)
const catchIndex = registerVue.indexOf('} catch (error) {', submitStart)
const catchReturnIndex = registerVue.indexOf('return', catchIndex)
const stateCommitIndex = registerVue.indexOf('setEnterpriseRegistration(', submitStart)

const result = {
  checkedAt: new Date().toISOString(),
  customerAuthPath,
  registerPath,
  enterpriseUploadPathConfigured: customerAuth.includes(enterpriseUploadConst),
  enterpriseUploadUsesDedicatedPath: enterpriseUploadBlock.includes('requestPath: ENTERPRISE_LICENSE_UPLOAD_PATH'),
  enterpriseUploadAvoidsInfraPath: !enterpriseUploadBlock.includes('/app-api/infra/file/upload'),
  genericInfraUploadStillIsolated: (customerAuth.match(/\/app-api\/infra\/file\/upload/g) || []).length >= 1,
  uploadHappensBeforeSave: ensureUploadIndex !== -1 && ensureUploadIndex < saveIndex,
  saveHappensBeforeSubmit: saveIndex !== -1 && saveIndex < submitIndex,
  uploadFailureReturnsBeforeStateCommit:
    catchIndex !== -1 && catchReturnIndex !== -1 && stateCommitIndex !== -1 && catchReturnIndex < stateCommitIndex
}

result.passed = Object.entries(result)
  .filter(([key, value]) => key !== 'checkedAt' && key !== 'customerAuthPath' && key !== 'registerPath' && typeof value === 'boolean')
  .every(([, value]) => value)

mkdirSync(path.dirname(outputFile), { recursive: true })
writeFileSync(outputFile, `${JSON.stringify(result, null, 2)}\n`, 'utf8')

if (!result.passed) {
  console.error(JSON.stringify(result, null, 2))
  process.exit(1)
}

console.log(JSON.stringify(result, null, 2))
