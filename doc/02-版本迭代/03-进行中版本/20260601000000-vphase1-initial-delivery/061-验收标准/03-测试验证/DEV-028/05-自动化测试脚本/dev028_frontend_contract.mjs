import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repositoryRoot = process.argv[2]
assert.ok(repositoryRoot, 'usage: node dev028_frontend_contract.mjs <code/develop>')

const read = (path) => readFileSync(resolve(repositoryRoot, path), 'utf8')

const chat = read('yunjikeji/src/pages/service/customer-service-chat.vue')
const listPage = read('yunjikeji/src/pages/service/customer-service.vue')
const service = read('yunjikeji/src/services/customerService.ts')
const socket = read('yunjikeji/src/services/customerServiceWebSocket.ts')
const backendService = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/message/service/CustomerMessageServiceImpl.java')
const repository = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/message/dal/CustomerMessageRepository.java')
const controller = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/message/controller/FrontCustomerServiceSessionController.java')
const sendRequest = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/message/controller/vo/AppCustomerServiceSendReqVO.java')
const realtimeRequest = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/message/controller/vo/AppCustomerServiceRealtimeSendReqVO.java')
const websocketListener = read('yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/app/message/websocket/AppCustomerServiceMessageWebSocketListener.java')

assert.match(chat, /typeof uni\.onKeyboardHeightChange === ['"]function['"]/, 'H5 must guard the missing keyboard subscribe API')
assert.match(chat, /typeof uni\.offKeyboardHeightChange === ['"]function['"]/, 'H5 must guard the missing keyboard unsubscribe API')
assert.match(chat, /fetchAllEnterpriseStudentMessages\(/, 'enterprise chat must load every history page')
assert.match(chat, /startEnterpriseStudentConversation\(/, 'an unstarted enterprise student must use explicit start')
assert.match(chat, /await ensureEnterpriseConversation\(\)/,
  'enterprise first send must start or resolve a real conversation before sending')
assert.match(chat, /message\.studentId === Number\(studentId\.value\)[\s\S]{0,240}message\.sessionId === resolveEnterpriseConversationId\(\)/,
  'enterprise realtime receive must match both studentId and conversationId')
assert.doesNotMatch(chat, /fetchAllEnterpriseStudentMessages\([\s\S]{0,80}tenantId/,
  'enterprise history must not require a teacher or student tenant')
assert.doesNotMatch(listPage, /if \(!tenantId\)/, 'enterprise list must not be gated by the teacher tenant')

const enterprisePageSizeMatch = listPage.match(/const ENTERPRISE_PAGE_SIZE = (\d+)/)
assert.ok(enterprisePageSizeMatch, 'enterprise list must declare one fixed, visible-page size')
const enterprisePageSize = Number(enterprisePageSizeMatch[1])
assert.equal(enterprisePageSize, 50, 'enterprise visible pagination must show exactly 50 students per page')
const approvedStudentFixture = Array.from({ length: 101 }, (_, index) => index + 1)
const approvedStudentPageLengths = [1, 2, 3]
  .map((pageNo) => approvedStudentFixture.slice((pageNo - 1) * enterprisePageSize, pageNo * enterprisePageSize).length)
assert.deepEqual(approvedStudentPageLengths, [50, 50, 1],
  '101 approved students must remain reachable as 50, 50 and 1 rows across three visible pages')
assert.match(listPage, /const enterprisePageNo = ref\(1\)/,
  'enterprise pagination must track the current successful page')
assert.match(listPage, /fetchEnterpriseStudentConversations\(targetPageNo, ENTERPRISE_PAGE_SIZE\)/,
  'each visible page must request its own pageNo and fixed pageSize')
assert.match(listPage, /loadEnterpriseStudents\(enterprisePageNo\.value \+ 1\)/,
  'next-page interaction must request pageNo + 1')
assert.match(listPage, /loadEnterpriseStudents\(enterprisePageNo\.value - 1\)/,
  'previous-page interaction must request pageNo - 1')
assert.match(listPage, /:disabled="!canGoPreviousEnterprisePage"/,
  'the previous-page control must be disabled on the first page or while loading')
assert.match(listPage, /:disabled="!canGoNextEnterprisePage"/,
  'the next-page control must be disabled on the known last page or while loading')
assert.match(listPage, /\u7b2c\s*\{\{\s*enterprisePageNo\s*\}\}\s*\u9875/,
  'enterprise pagination must expose stable current-page state')
assert.match(listPage, /enterpriseHasNextPage\.value = conversations\.length === ENTERPRISE_PAGE_SIZE/,
  'a short page must be recognized as the last page')
assert.match(listPage, /if \(!conversations\.length && targetPageNo > enterprisePageNo\.value\)[\s\S]{0,180}enterpriseHasNextPage\.value = false[\s\S]{0,80}return/,
  'an empty look-ahead page must keep the last non-empty page and disable next')
assert.doesNotMatch(listPage, /enterpriseConversations\.value\s*=\s*\[\.\.\.enterpriseConversations\.value/,
  'visible pagination must replace page rows instead of mixing adjacent pages')
assert.match(listPage, /onShow\(\(\) => \{[\s\S]{0,260}loadEnterpriseStudents\(1\)/,
  'showing or refreshing the enterprise list must explicitly reset it to page one')
assert.match(listPage, /function openEnterpriseConversation\(item: EnterpriseStudentConversation\)[\s\S]{0,420}item\.studentId[\s\S]{0,420}item\.conversationId[\s\S]{0,420}uni\.navigateTo/,
  'clicking a paged student must preserve studentId and the optional real conversationId')

assert.doesNotMatch(service, /tenant-\$\{tenantId\}-student-\$\{studentId\}/, 'synthetic conversations are forbidden')
assert.match(service, /conversationId: string \| null/, 'an unstarted student must remain visible with a null conversation id')
assert.match(service, /tenantId: number \| null/, 'an approved student without an organization tenant must remain visible')
assert.match(service, /startEnterpriseStudentConversation\s*=\s*\(studentId: number\)/,
  'enterprise first contact must expose an explicit start request')
assert.match(service, /fetchEnterpriseStudentMessages\s*=\s*\(conversationId: number, studentId: number/,
  'enterprise history HTTP contract must carry conversationId and studentId')
assert.match(service, /fetchAllEnterpriseStudentMessages/, 'enterprise history must expose an all-pages loader')
assert.match(service, /fetchEnterpriseStudentConversations = async \(pageNo = 1, pageSize = 50\)/,
  'enterprise student visibility must use the same 50-row default page size without a teacher tenant')
assert.match(service, /sendEnterpriseStudentTextMessage\s*=\s*\(conversationId: number, studentId: number/,
  'enterprise text send must carry conversationId and studentId')
assert.match(service, /sendEnterpriseStudentMediaMessage\s*=\s*\(conversationId: number, studentId: number/,
  'enterprise media send must carry conversationId and studentId')
assert.match(service, /const CUSTOMER_SERVICE_BASE = ['"]\/app-api\/yj\/customer-service['"]/, 'student API base must remain unchanged')
assert.match(service, /path: ['"]\/session['"]/, 'student session create/reuse path must remain unchanged')
assert.match(service, /path: ['"]\/messages['"]/, 'student history/send path must remain unchanged')

assert.match(socket, /sendTextMessage\s*=\s*\(payload: \{ conversationId\?: number; studentId\?: number; content: string \}\)/,
  'websocket send contract must carry conversationId with studentId')
assert.match(socket, /conversationId: payload\.conversationId/, 'websocket envelope must transmit conversationId')

assert.doesNotMatch(backendService, /tenant-" \+ tenantId \+ "-student-/, 'backend must not synthesize a conversation')
assert.match(backendService, /getCurrentCompanyStudentMessages\(Long studentId, Long conversationId/,
  'backend history contract must require conversationId and studentId')
assert.match(backendService, /getCurrentCompanyStudentMessages\(Long studentId, Long conversationId[\s\S]{0,700}requireCompanyStudentSession\(studentId, conversationId\)[\s\S]{0,700}bindSessionReceiver\(/,
  'validated existing history may retain receiver binding for websocket delivery')
assert.doesNotMatch(backendService, /getCurrentCompanyStudentMessages\(Long studentId, Long conversationId[\s\S]{0,900}(?:createSession|startCurrentCompanyStudentConversation)\(/,
  'enterprise history must not create or start a session')
assert.match(backendService, /startCurrentCompanyStudentConversation\(Long studentId\)/,
  'backend must expose an explicit enterprise start operation')
assert.match(repository, /LEFT JOIN yj_session_message sm ON sm\.session_from = ca\.id/,
  'enterprise list must keep approved students before their first session')
assert.doesNotMatch(repository, /sm\.tenant_id = ca\.tenant_id/, 'enterprise session association must ignore tenant_id')
assert.match(repository, /getApprovedStudentConversations\(int pageNo, int pageSize\)/,
  'enterprise list repository must not accept the current teacher tenant')
assert.match(repository, /ca\.tenant_id IS NULL AND ci\.tenant_id IS NULL/,
  'approved students without an organization tenant must remain queryable')
assert.match(repository, /lockApprovedStudentTenantId\(Long studentId\)/,
  'explicit start must lock the target student and may read a nullable account tenant')
assert.match(backendService, /resolveCustomerServiceTenantId\(Long accountTenantId\)/,
  'student and enterprise first contact must share the unbound tenant storage rule')
assert.match(repository, /findLatestSessionByStudent\(Long studentId\)/,
  'explicit start must recheck an existing session after locking the student relation')
assert.match(repository, /getSessionByConversationAndStudent\(Long conversationId, Long studentId\)/,
  'repository must expose exact conversation/student validation')
assert.match(repository, /WHERE id = \? AND session_from = \? AND deleted = b'0'/,
  'conversation/student validation must not filter by tenant_id')
assert.match(controller, /@RequestParam\("conversationId"\) Long conversationId/,
  'enterprise HTTP history must receive conversationId')
assert.match(controller, /\/yj\/company-students\/conversations\/start/,
  'enterprise first contact must use a dedicated start endpoint')
assert.match(sendRequest, /private Long conversationId;/, 'enterprise HTTP send VO must receive conversationId')
assert.match(realtimeRequest, /private Long conversationId;/, 'enterprise websocket send VO must receive conversationId')
assert.match(websocketListener, /message\.getConversationId\(\)/, 'websocket listener must forward conversationId')

console.log('DEV-028 frontend/backend contract checks passed')
