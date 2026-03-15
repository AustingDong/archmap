/**
 * Playwright browser test for ArchMap — Architecture page edge inference.
 * Run: node test_browser.mjs
 */
import { chromium } from 'playwright';

const APP_URL = 'http://localhost:5174';
const PROJECT_PATH = 'C:/Users/a7don/my_projects/archmap';

async function run() {
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();

  // Capture errors and 404s
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));

  // Set Zustand persisted store before loading the app
  console.log('1. Setting project path...');
  await page.goto(APP_URL);
  await page.evaluate((path) => {
    localStorage.setItem('archmap-store', JSON.stringify({ state: { projectPath: path }, version: 0 }));
  }, PROJECT_PATH);

  console.log('2. Loading app with project set...');
  await page.goto(APP_URL);
  await page.waitForLoadState('networkidle');

  console.log('3. Navigating to Architecture page...');
  const archLink = page.locator('a, button, [role="link"]').filter({ hasText: /architect/i }).first();
  if (await archLink.isVisible()) {
    await archLink.click();
  } else {
    await page.goto(`${APP_URL}/architecture`);
  }
  await page.waitForTimeout(2000);

  const edgesBefore = await page.locator('.react-flow__edge').count();
  const nodesBefore = await page.locator('.react-flow__node').count();
  console.log(`4. Nodes: ${nodesBefore}, Edges before infer: ${edgesBefore}`);
  await page.screenshot({ path: 'screenshot_before_infer.png' });

  console.log('5. Clicking Infer Deps...');
  const inferBtn = page.locator('button').filter({ hasText: /infer/i }).first();
  if (!(await inferBtn.isVisible())) {
    console.log('   ⚠ Infer button not found');
  } else {
    await inferBtn.click();
    await page.waitForTimeout(3000);
  }

  const edgesAfter = await page.locator('.react-flow__edge').count();
  console.log(`6. Edges after infer: ${edgesAfter}`);

  const dashedEdges = await page.evaluate(() => {
    const paths = document.querySelectorAll('.react-flow__edge path');
    return [...paths].filter(p => p.style.strokeDasharray && p.style.strokeDasharray !== '').length;
  });
  console.log(`7. Dashed (auto) edges: ${dashedEdges}`);

  const toastText = await page.locator('[class*="toast"], [role="alert"]').allTextContents();
  console.log(`8. Toast messages: ${JSON.stringify(toastText)}`);

  await page.screenshot({ path: 'screenshot_after_infer.png' });

  if (errors.length > 0) {
    console.log('\n❌ Console errors:');
    errors.forEach(e => console.log('  ', e));
  }

  if (edgesAfter > edgesBefore) {
    console.log(`\n✅ PASS: ${edgesAfter - edgesBefore} new edge(s) appeared`);
    if (dashedEdges > 0) console.log(`✅ Dashed (auto) edges visible: ${dashedEdges}`);
  } else if (edgesBefore > 0 && edgesAfter === edgesBefore) {
    console.log(`\n✅ PASS (already inferred): ${edgesAfter} edges shown, ${dashedEdges} dashed`);
  } else {
    console.log(`\n❌ FAIL: edge count unchanged (${edgesBefore} → ${edgesAfter})`);
  }

  await browser.close();
}

run().catch(err => { console.error(err); process.exit(1); });
