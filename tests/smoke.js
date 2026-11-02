// Smoke test: boots the explorer from a URL (file:// for the embedded build, http://
// for the hosted build), waits for the first tessellation, checks the filter
// regression and that a region computes. Usage:
//   node tests/smoke.js <url> [screenshot.png]
const { chromium } = require('playwright');
const url = process.argv[2];
const shot = process.argv[3];
if (!url) { console.error('usage: node tests/smoke.js <url> [screenshot.png]'); process.exit(2); }

(async () => {
  const exe = process.env.CHROMIUM_PATH || undefined;
  const browser = await chromium.launch({
    executablePath: exe,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text().slice(0, 300)); });
  const t0 = Date.now();
  await page.goto(url);
  await page.waitForFunction('typeof globalIdxMap !== "undefined" && globalIdxMap !== null', { timeout: 240000 });
  const boot = ((Date.now() - t0) / 1000).toFixed(1);
  const state = await page.evaluate(() => ({
    nP: DATA.nP, nS: DATA.nS, version: MANIFEST.version || null,
    mode: EMBED.main ? 'embedded' : 'hosted', dataBase: CONFIG ? CONFIG.dataBase : null,
  }));
  // filter regression: every filled cell must hold a filtered source
  await page.evaluate(() => { filterState[0].lo = 30; pipelineFilterChanged(); });
  await page.waitForFunction(() => document.getElementById('progress').style.display !== 'block' && DATA.filterCount < DATA.nP, { timeout: 240000 });
  await page.waitForTimeout(300);
  const reg = await page.evaluate(() => {
    const f = new Set(DATA.filteredIdx); let bad = 0, n = 0;
    for (let t = 0; t < 5000 && n < 50; t++) {
      const s = globalIdxMap[Math.floor(Math.random() * globalIdxMap.length)];
      if (s === 0xFFFFFFFF) continue; n++; if (!f.has(s)) bad++;
    }
    return { checked: n, bad };
  });
  // region
  const region = await page.evaluate(() => {
    REGION.l = 285; REGION.b = -8; REGION.radius = 3; REGION.active = true;
    setRegionMembers(regionMembers());
    return REGION.idx.length;
  });
  if (shot) await page.screenshot({ path: shot });
  const ok = errors.length === 0 && reg.bad === 0 && state.nP > 0;
  console.log(JSON.stringify({ ok, boot_s: +boot, ...state, filterCheck: reg, regionSources: region, errors }, null, 1));
  await browser.close();
  process.exit(ok ? 0 : 1);
})();
