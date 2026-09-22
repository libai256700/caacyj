# Android 真机自动化测试

这里是独立于业务工程的 Android 真机测试目录。当前脚本覆盖认证主流程 `AUTH-002`、`AUTH-003` 和登录后核心导航 `CORE-001`，使用 Appium 3 + UiAutomator2 驱动发行 APK，并在 Uni-app WebView 与运营商原生授权页之间切换。

元素定位以源码契约和 UI 树为主：关键交互控件在 `src/pages/auth/login.vue` 中使用稳定的语义化 `id`（如 `auth-phone-input`、`auth-submit`）。当 APK 暴露 `WEBVIEW_*` 时优先使用 `#id`；发行包只暴露 WebView 容器时，使用同一页面的可访问文本从 UiAutomator UI 树定位，并根据元素边界计算点击点。截图和 XML 只作为证据，不参与元素识别。

## 元素定位契约

- ID 使用 `auth-`、`home-` 等业务区域前缀，保持唯一且不随样式类名变化。
- UniAutomator/WebView 使用 `#id`；Appium 原生模式优先使用 `resource-id`，没有资源 ID 时使用源码对应的可访问文本。
- 不把 `data-testid` 作为真机主选择器：当前发行 APK 的 Android UI 树不会稳定暴露它。
- 新增或修改交互控件时，同步补充稳定 ID 和测试配置映射；禁止用元素序号或截图像素作为主定位方式。

## 运行前提

- Android SDK 的 `adb` 已加入 PATH，或在 [config.mjs](./config.mjs) 的 `device.adbPath` 中填写绝对路径。
- 手机已经通过 ADB 配对并处于 `device` 状态：`adb devices` 应能看到设备。
- 已安装 Appium 3 和 UiAutomator2 驱动：

  ```powershell
  appium driver install uiautomator2
  ```

- `code/develop/yunjikeji/dist/release/apk` 中存在包名为 `com.caacyj.app` 的发行 APK。脚本会自动选择该目录内最新的 `__UNI__F4DBB06__*.apk`。
- 普通发行 APK 不一定暴露 `WEBVIEW_*` context；脚本会使用 UiAutomator UI 树中的可访问文本继续执行。只有需要直接查询 WebView DOM 时，才需要带 WebView 调试能力的自定义基座或测试包。

## 执行

### 从测试列表点击运行

这是一个独立的本地控制台。启动后打开 `http://127.0.0.1:8765/`，每个已绑定脚本的功能点都会显示测试编号和“运行”按钮。点击后由本机 Node 控制服务启动登记过的脚本，脚本通过 Appium/ADB 控制当前 Android 真机；页面不会执行任意命令，也不会连接业务服务。

```powershell
cd tests/mobile-e2e
npm start
```

控制台会显示设备状态、运行中的脚本输出和最终 `result.json` 报告。一次只能运行一个脚本，避免多个脚本同时操作同一台手机。设备没有处于 `device` 状态时，运行按钮会暂时禁用。

在仓库根目录运行：

 ```powershell
node tests/mobile-e2e/scripts/auth-002-univerify.main.mjs
```

短信登录主流程：

```powershell
node tests/mobile-e2e/scripts/auth-003-sms.main.mjs
```

登录后主流程导航：

```powershell
node tests/mobile-e2e/scripts/core-001-navigation.main.mjs
```

包体内置的用户服务协议与隐私政策阅读：

```powershell
node tests/mobile-e2e/scripts/agreement-001-bundled-content.main.mjs
```

逐题练习选题与答题入口：

```powershell
node tests/mobile-e2e/scripts/practice-001-start.main.mjs
```

岗位招聘列表与详情访问分支：

```powershell
node tests/mobile-e2e/scripts/jobs-001-list-detail.main.mjs
```

岗位外部详情返回后保持列表位置：

```powershell
node tests/mobile-e2e/scripts/jobs-002-external-return-scroll.main.mjs
```

岗位类型和工作省份筛选：

```powershell
# 先在 HBuilderX 选择“运行 -> 运行到手机或模拟器 -> 运行基座选择 -> 自定义调试基座”，
# 再执行“运行到 Android App 基座”，让设备上的自定义基座加载 dist/dev/app-plus。
node tests/mobile-e2e/scripts/jobs-003-filter.main.mjs
```

JOBS-003 保留教员、工程师和省份筛选规格；如果当前 APK 的岗位页面没有对应控件，脚本会在 8 秒内失败并指出实现缺口，不会把旧 APK 或无筛选页面判定为通过。

章节测试、考试和评测结果入口轻量检查：

```powershell
node tests/mobile-e2e/scripts/practice-002-entry.main.mjs
```

自测完整主流程（短信验证码登录前置）：

```powershell
node tests/mobile-e2e/scripts/self-test-001-sms.main.mjs
```

个人中心头像上传、保存与重启后持久化验证：

```powershell
node tests/mobile-e2e/scripts/profile-001-avatar-upload.main.mjs
```

顶部安全区、顶部导航固定、底部导航固定和中间区域滚动：

```powershell
node tests/mobile-e2e/scripts/layout-001-fixed-navigation.main.mjs
```

短信登录和自测脚本使用测试配置中的固定手机号和验证码，不点击“获取验证码”，不会向真实手机号发送短信。自测脚本不会调用一键登录。

`AUTH-003` 会在执行前清空应用数据以验证干净的短信登录流程，并在通过后保留登录态，供 `CORE-001`、练习、岗位和头像上传等登录后场景继续使用。因此需要刷新登录态时先运行 `AUTH-003`，随后再运行这些场景。

Appium 未启动时脚本会按 [config.mjs](./config.mjs) 自动启动本机服务。当前配置已启用 `test.autoConfirmAuthorization`，脚本会自动点击运营商授权并继续验证登录结果；如需人工审核授权页，可将该配置改回 `false`。

## 流程范围

认证脚本覆盖一键登录和短信登录主流程；`AGREEMENT-001` 先检查协议源码不含网络请求，再以自定义基座从登录页打开用户服务协议和隐私政策，核对标题、正文片段及无加载、失败或重试状态，保证协议内容随包体提供；`SELF-TEST-001` 使用短信验证码登录后完整填写并提交当前自测会话的全部答案，验证资料提交、题目操作区、任意答案输入、下一题、上一题、最终提交和返回首页等功能，不校验题干、选项含义、答案对错或题库内容；`CORE-001` 覆盖登录后首页、岗位、客服、AI 中心、我的和逐题练习分类页的交互；`PROFILE-001` 覆盖个人中心编辑入口、专用测试图片选择、上传、保存及重启后持久化；`PRACTICE-001` 覆盖逐题练习入口、题目主题选择、批次详情、第一题加载、任意选项提交后的结果态、下一题和上一题推进，不判断题目内容或答案对错；`JOBS-001` 覆盖岗位列表 ready/empty 状态和首个岗位详情的组织绑定或外部详情分支；`JOBS-002` 覆盖岗位列表滚动、离开应用后返回以及列表位置保持；`JOBS-003` 覆盖岗位标题关键词筛选、全部省份与省份选项展示、湖北省工作地点筛选，结果为空时验证明确空态；`LAYOUT-001` 覆盖顶部安全区、顶部导航固定、底部导航固定和中间区域独立滚动，并按 UI 树元素边界进行真机滑动前后对比；`PRACTICE-002` 保留章节测试、考试和评测结果入口的轻量状态检查。发行 APK 未暴露目标 WebView 调试通道时，脚本会按 UI 树文本定位并从元素边界执行真机点击；系统文件选择器同样按文件名、content-desc 或 UI 树边界定位，不使用固定坐标。设备不支持、用户取消、授权失败、云函数失败和网络超时等异常分支在场景清单中列为后续 P1；快速重复点击列为 P2。

## 报告

每次执行写入 `tests/mobile-e2e/reports/auth-002/<时间戳>/`，包含：

- `result.json`：步骤状态、错误和设备信息；
- 关键节点截图与页面 XML；
- `logcat-filtered.txt`：仅保留一键登录、WebView 和崩溃相关日志；
- Appium 启动失败时的 `appium-startup.log`。

授权点击后的截图命名为 `03-carrier-confirm-clicked.*`，用于记录刚点击授权按钮时的过渡状态；最终是否完成登录以 `04-home-after-login.*`、首页 Activity 和 `result.json` 第 8 步为准。

日志和 XML 会脱敏手机号、`accessToken`、`openid`、密钥和密码。没有连接设备时，脚本会明确失败并生成报告，不会继续启动 Appium 或业务应用。

## 快速查看 UI 树

在需要为新场景找定位依据时，运行独立检查器：

```powershell
powershell -ExecutionPolicy Bypass -File tests/mobile-e2e/scripts/inspect-ui-tree.ps1 -Serial 192.168.1.134:43265
```

它会生成 `window.xml` 原始 UI 树和 `nodes.csv` 节点表。优先选择 `resource-id` 或源码中定义的语义化 `id`，其次选择稳定的 `text/content-desc`；不要使用 `index`、屏幕坐标或截图像素。
