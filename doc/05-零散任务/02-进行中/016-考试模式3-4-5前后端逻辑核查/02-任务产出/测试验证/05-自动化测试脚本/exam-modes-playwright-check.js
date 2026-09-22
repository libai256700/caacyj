const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const outputPath = path.join(__dirname, 'exam-modes-playwright-output.json');
const targetUrl = 'http://localhost:5173/yunjikeji/#/pages/practice/exam-modes';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const interceptedRequests = [];
  const visibleButtons = [];
  let bodyText = '';
  let finalUrl = '';
  let blocker = '';

  await page.route('**/app-api/yj/practices/**/start/**', (route) => {
    const request = route.request();
    interceptedRequests.push({
      method: request.method(),
      url: request.url(),
      postData: request.postData() || ''
    });
    return route.abort('blockedbyclient');
  });

  try {
    await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });
    finalUrl = page.url();
    bodyText = await page.locator('body').innerText();
    const buttons = await page.locator('button').allInnerTexts();
    for (const buttonText of buttons) {
      const normalized = buttonText.replace(/\s+/g, ' ').trim();
      if (normalized) {
        visibleButtons.push(normalized);
      }
    }
    if (!finalUrl.includes('/pages/practice/exam-modes')) {
      blocker = '页面未停留在考试模式页，访问被前端路由重定向。';
    }
  } catch (error) {
    blocker = error instanceof Error ? error.message : String(error);
  } finally {
    await browser.close();
  }

  const result = {
    checkedAt: '2026-08-19',
    targetUrl,
    finalUrl,
    blocker,
    interceptedRequests,
    visibleButtons,
    bodyTextPreview: bodyText.slice(0, 500)
  };

  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify(result, null, 2));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
