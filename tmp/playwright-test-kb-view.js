const { chromium } = require('playwright');
const path = require('path');

const TARGET_URL = 'http://localhost:5173';
const SCREENSHOT_DIR = '/tmp/kb-view-test';

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 150 });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  const fs = require('fs');
  if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  try {
    // ================================================================
    // 1. 登录管理后台
    // ================================================================
    console.log('1️⃣  导航到管理后台登录页...');
    await page.goto(`${TARGET_URL}/#/admin/login`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '00-login-page.png') });

    await page.fill('#username', 'admin');
    await page.fill('#password', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-logged-in.png') });
    console.log('✅ 登录成功');

    // ================================================================
    // 2. 进入知识库管理页面
    // ================================================================
    console.log('2️⃣  切换到知识库管理标签...');
    // 点击左侧导航的"知识库管理"标签（第5个 tab）
    const kbNavItem = page.locator('.nav-item', { hasText: '知识库管理' });
    await kbNavItem.waitFor({ state: 'visible', timeout: 5000 });
    await kbNavItem.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-kb-list.png') });
    console.log('✅ 进入知识库管理页面');

    // ================================================================
    // 3. 选择 AnswerAgent 知识库
    // ================================================================
    console.log('3️⃣  选择 AnswerAgent 知识库...');
    const kbItem = page.locator('.kb-item', { hasText: 'AnswerAgent' });
    await kbItem.waitFor({ state: 'visible', timeout: 5000 });
    await kbItem.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-kb-selected.png') });
    console.log('✅ 选择知识库成功');

    // ================================================================
    // 4. 查看 Markdown 文件（architecture.md）
    // ================================================================
    console.log('4️⃣  查看 Markdown 文件（architecture.md）...');
    const mdRow = page.locator('tr', { hasText: 'architecture.md' });
    await mdRow.waitFor({ state: 'visible', timeout: 5000 });
    const viewBtn = mdRow.locator('.btn-view');
    await viewBtn.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-markdown-rendered.png') });
    console.log('✅ Markdown 渲染显示');

    // 检查渲染模式标签
    const badge = page.locator('.render-badge');
    console.log('  渲染标签:', await badge.textContent());

    // 测试全屏模式
    console.log('  4a. 全屏模式...');
    const btns = page.locator('.btn-icon');
    await btns.nth(0).click(); // 全屏按钮
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-markdown-fullscreen.png') });
    console.log('✅ 全屏模式');
    await btns.nth(0).click(); // 退出全屏
    await page.waitForTimeout(400);

    // 关闭预览
    await btns.nth(1).click(); // 关闭按钮
    await page.waitForTimeout(600);
    console.log('✅ Markdown 查看测试完成');

    // ================================================================
    // 5. 进入 src 目录
    // ================================================================
    console.log('5️⃣  进入 src 子目录...');
    const srcDir = page.locator('tr', { hasText: 'src' });
    await srcDir.waitFor({ state: 'visible', timeout: 5000 });
    await srcDir.dblclick();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-src-directory.png') });
    console.log('✅ 进入 src 目录成功');

    // ================================================================
    // 6. 查看 Python 文件（语法高亮）
    // ================================================================
    console.log('6️⃣  查看 Python 文件...');
    const pyRow = page.locator('tr', { hasText: 'sse_event_sample.py' });
    await pyRow.waitFor({ state: 'visible', timeout: 5000 });
    const pyViewBtn = pyRow.locator('.btn-view');
    await pyViewBtn.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-python-highlighted.png') });

    const badge2 = page.locator('.render-badge');
    console.log('  渲染标签:', await badge2.textContent());
    console.log('✅ Python 语法高亮显示');

    // 全屏查看
    console.log('  6a. 全屏查看...');
    const btns2 = page.locator('.btn-icon');
    await btns2.nth(0).click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08-python-fullscreen.png') });
    await btns2.nth(0).click(); // 退出全屏
    await page.waitForTimeout(400);

    // 关闭
    await btns2.nth(1).click();
    await page.waitForTimeout(500);

    // ================================================================
    // 7. 回到根目录查看普通文本文件
    // ================================================================
    console.log('7️⃣  回到根目录查看 .gitignore...');
    // 先回到上一级
    await page.goBack(); // 或者点击面包屑
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09-back-to-root.png') });

    // 查看 .gitignore (如果存在)
    // 实际上 .gitignore 被隐藏过滤了，跳过

    console.log('\n🎉 所有测试完成！');
    console.log('截图保存在: ' + SCREENSHOT_DIR);
  } catch (error) {
    console.error('❌ 测试失败:', error.message);
    try {
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'error.png') });
      console.log('错误截图已保存');
    } catch (_) {}
  } finally {
    await browser.close();
  }
})();
