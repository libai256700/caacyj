import path from 'node:path'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const workspaceRoot = path.resolve(testDir, '../..')

export default Object.freeze({
  app: {
    appId: '__UNI__F4DBB06',
    packageName: 'com.caacyj.app',
    activity: 'io.dcloud.PandoraEntry',
    homeActivity: 'io.dcloud.PandoraEntryActivity',
    projectDir: path.resolve(workspaceRoot, 'code/develop/yunjikeji'),
    apkDir: path.resolve(workspaceRoot, 'code/develop/yunjikeji/dist/release/apk'),
    apkPattern: /^__UNI__F4DBB06__\d+\.apk$/,
    // Appium's noReset:false login prerequisite may clear the external www
    // cache on Android 15. The self-test restores the built web assets before
    // starting its own session.
    webAssetsDir: path.resolve(workspaceRoot, 'code/develop/yunjikeji/dist/build/app'),
    webAssetsRemoteDir: '/sdcard/Android/data/com.caacyj.app/apps/__UNI__F4DBB06/www',
  },
  device: {
    // Leave empty to use the only connected Android device.
    serial: '',
    adbPath: 'D:/DevShared/DevSoft/HBuilderX/plugins/launcher-tools/tools/adbs/adb.exe',
  },
  hbuilderx: {
    cliPath: 'D:/DevShared/DevSoft/HBuilderX/cli.exe',
  },
  devtools: {
    // ADB forwards this local port to the active custom-base WebView only
    // while a source-selector interaction is being performed.
    localPort: 19023,
  },
  appium: {
    serverUrl: 'http://127.0.0.1:4723',
    command: 'appium.cmd',
    // Run Appium's Node entry directly. On Windows, spawning appium.cmd through
    // a shell can return before the child has bound its HTTP port.
    entryPath: 'C:\\Users\\13174\\AppData\\Roaming\\npm\\node_modules\\appium\\index.js',
    host: '127.0.0.1',
    port: 4723,
    autoStart: true,
    // The test console owns this local port. Restart a stale listener so a
    // service started with a different Java environment cannot be reused.
    restartExisting: true,
    allowInsecure: ['uiautomator2:chromedriver_autodownload'],
    // Use the DOS short path so apksigner can start reliably on Windows.
    javaHome: 'C:\\Progra~1\\Java\\jdk1.8.0_162',
  },
  test: {
    id: 'AUTH-002',
    role: 'student',
    timeoutMs: 45_000,
    // The end-to-end run is explicitly authorized to confirm the carrier page.
    autoConfirmAuthorization: true,
    reportDir: path.resolve(testDir, 'reports/auth-002'),
  },
  scenarios: {
    sms: {
      id: 'AUTH-003',
      phone: '18171171929',
      code: '897889',
      reportDir: path.resolve(testDir, 'reports/auth-003'),
    },
    agreement: {
      id: 'AGREEMENT-001',
      reportDir: path.resolve(testDir, 'reports/agreement-001'),
      timeoutMs: 45_000,
    },
    core: {
      id: 'CORE-001',
      reportDir: path.resolve(testDir, 'reports/core-001'),
      timeoutMs: 45_000,
    },
    layout: {
      id: 'LAYOUT-001',
      reportDir: path.resolve(testDir, 'reports/layout-001'),
      timeoutMs: 30_000,
    },
    jobs: {
      id: 'JOBS-001',
      reportDir: path.resolve(testDir, 'reports/jobs-001'),
      timeoutMs: 45_000,
    },
    jobsScrollRestore: {
      id: 'JOBS-002',
      reportDir: path.resolve(testDir, 'reports/jobs-002'),
      timeoutMs: 45_000,
    },
    jobsFilter: {
      id: 'JOBS-003',
      reportDir: path.resolve(testDir, 'reports/jobs-003'),
      timeoutMs: 45_000,
      // The current remote jobs page may not expose the filter contract yet.
      // Detect that mismatch quickly instead of waiting through every branch.
      filterControlTimeoutMs: 8_000,
    },
    practiceEntry: {
      id: 'PRACTICE-002',
      reportDir: path.resolve(testDir, 'reports/practice-002'),
      timeoutMs: 45_000,
    },
    selfTest: {
      id: 'SELF-TEST-001',
      reportDir: path.resolve(testDir, 'reports/self-test-001'),
      timeoutMs: 60_000,
    },
    profileAvatar: {
      id: 'PROFILE-001',
      reportDir: path.resolve(testDir, 'reports/profile-001'),
      timeoutMs: 60_000,
      // This scenario validates the custom base that HBuilderX has already
      // installed and launched. Do not let Appium replace it with a release APK.
      reuseInstalledCustomBase: true,
      testImage: {
        localPath: path.resolve(workspaceRoot, 'code/develop/yunjikeji/src/static/enterprise-students/avatar-02.png'),
        devicePath: '/sdcard/Pictures/HuiyiTechE2E/profile-avatar-test-02.png',
        displayName: 'profile-avatar-test-02.png',
      },
    },
  },
  selectors: {
    loginPage: '#auth-login-page, .login-page',
    studentRole: '#auth-role-student.login-role-tabs__item--active, .login-role-tabs__item--active',
    agreement: '#auth-agreement, .login-agreement',
    agreementChecked: '#auth-agreement .login-agreement__check--active, .login-agreement__check--active',
    oneClickPanel: '#auth-univerify-panel, .login-one-click-panel',
    oneClickButton: '#auth-univerify-submit, .login-one-click-panel__submit',
    homePage: '.phone-screen',
  },
  nativeSelectors: {
    // These labels are the accessible UI-tree representation of the
    // source-defined controls in src/pages/auth/login.vue.
    agreement: '//*[contains(@text,"我已阅读并同意")]',
    oneClickButton: '//*[contains(@text,"本机号码一键登录")]',
  },
  nativeAuthorizationTexts: ['本机号码一键登录', '中国移动'],
  nativePrivacyButtonId: 'com.caacyj.app:id/btn_custom_privacy_sure',
  nativeCoordinates: {
    // Reference coordinates captured on the 1080x2400 test phone; the script scales them to the actual display.
    referenceWidth: 1080,
    referenceHeight: 2400,
    authorizationButton: { x: 540, y: 900 },
    privacyButton: { x: 540, y: 1475 },
  },
})
