async function restoreWebAssets(adb, app) {
  if (!app.webAssetsDir || !app.webAssetsRemoteDir) return

  const entryPoint = `${app.webAssetsRemoteDir}/__uniappview.html`
  const existing = await adb(['shell', 'ls', entryPoint], true)
  if (existing.stdout.trim()) return

  // Release APKs and a cleared custom base can leave the external www
  // directory with only manifest.json. Restore the compiled app files before
  // starting the activity so a clean login run never opens a blank/error page.
  await adb(['shell', 'mkdir', '-p', app.webAssetsRemoteDir])
  await adb(['push', `${app.webAssetsDir}/.`, `${app.webAssetsRemoteDir}/`])
}

export async function launchCleanAppTask(adb, app) {
  // A crashed Appium session can leave UiAutomation registered on Android.
  // Clear both runner processes before the next scenario creates a session.
  await adb(['shell', 'am', 'force-stop', 'io.appium.uiautomator2.server'], true)
  await adb(['shell', 'am', 'force-stop', 'io.appium.uiautomator2.server.test'], true)
  await adb(['shell', 'am', 'force-stop', app.packageName], true)
  await restoreWebAssets(adb, app)
  await adb([
    'shell',
    'am',
    'start',
    '-f',
    '0x10008000',
    '-n',
    `${app.packageName}/${app.activity}`,
  ])
}
