// Usage: NODE_PATH=$(npm root -g) node run.js <url> <out.png> [frames]
const { chromium } = require('playwright');
(async () => {
  const [url, out, framesArg] = process.argv.slice(2);
  const wantFrames = +framesArg || 60;
  const browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'] });
  const page = await browser.newPage({ viewport: { width: 660, height: 500 } });
  const logs = [];
  page.on('console', m => logs.push(m.type() + ': ' + m.text()));
  page.on('pageerror', e => logs.push('PAGEERROR: ' + e.message));
  const t0 = Date.now();
  for (let attempt = 0; ; attempt++) {
    try { await page.goto(url); break; } catch (e) { if (attempt >= 10) throw e; await page.waitForTimeout(500); }
  }
  try {
    await page.waitForFunction(() => window.__ready === true || window.__error, { timeout: 180000 });
    const err = await page.evaluate(() => window.__error);
    if (err) throw new Error('page error: ' + err);
    const tReady = Date.now() - t0;
    await page.waitForFunction(n => window.__Module.getFrames() >= n, wantFrames, { timeout: 180000 });
    const tFrames = Date.now() - t0;
    const frames = await page.evaluate(() => window.__Module.getFrames());
    // let a couple more frames land, then capture
    await page.waitForTimeout(500);
    await page.locator('#outputCanvas').screenshot({ path: out });
    const frames2 = await page.evaluate(() => window.__Module.getFrames());
    const initMs = await page.evaluate(() => window.__initMs);
    const gl = await page.evaluate(() => ({ total: window.__gl.total, counts: window.__gl.counts, frames: window.__Module.getFrames() }));
    const top = Object.entries(gl.counts).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([k, v]) => k + '=' + v).join(' ');
    console.log('gl calls: total=' + gl.total + ' frames=' + gl.frames + ' perFrame=' + (gl.total / gl.frames).toFixed(1) + ' | ' + top);
    const disc = await page.evaluate(() => window.__discStats || null);
    if (disc) console.log('disc device: ' + JSON.stringify(disc));
    console.log(JSON.stringify({ ok: true, readyMs: tReady, framesMs: tFrames, frames, frames2, initMs: Math.round(initMs) }));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: String(e) }));
  }
  const inner = await page.evaluate(() => window.__log || []);
  console.log('--- module log ---'); for (const l of inner.slice(0, 60)) console.log(l);
  console.log('--- console ---'); for (const l of logs.slice(0, 60)) console.log(l);
  await browser.close();
})();
