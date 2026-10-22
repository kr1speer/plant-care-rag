// Optional real-browser acceptance suite. See README for installation/run commands.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const output = process.env.ARTIFACT_DIR || '/tmp/plant-care-evidence';
const questions = [
  ['Почему у монстеры мелкие листья без прорезей?', 'недостатком света', 'Монстера деликатесная'],
  ['Какая температура нужна фикусу Бенджамина летом и зимой?', '25–30 °C', 'Фикус бенджамина'],
  ['Когда и как пересаживать орхидею фаленопсис?', 'раз в год после цветения', 'Фаленопсис'],
];

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    const response = await page.goto(baseURL);
    assert.equal(response.status(), 200, 'Home must be reachable');
    await page.getByText('Демонстрационная версия: BM25 и LLM не подключены', { exact: true }).waitFor();
    const input = page.getByLabel('Ваш вопрос');
    const submit = page.getByRole('button', { name: 'Спросить', exact: true });
    async function waitDone() {
      await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    }
    async function ask(question) {
      await input.fill(question);
      await submit.click();
      await waitDone();
    }
    for (const [question, fact, title] of questions) {
      await page.getByRole('button', { name: question, exact: true }).click();
      assert.equal(await input.inputValue(), question);
      await input.press('Enter');
      await waitDone();
      assert.ok((await page.locator('#answer-text').textContent()).includes(fact));
      assert.ok((await page.locator('#sources-list').textContent()).includes(title));
      assert.equal(await page.locator('#sources-list a').count(), 1);
      const link = page.locator('#sources-list a');
      assert.match(await link.getAttribute('href'), /^https:\/\/ru\.wikipedia\.org\//);
      assert.equal(await link.getAttribute('rel'), 'noopener noreferrer');
    }
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
    for (const question of ['Как поливать орхидею?', 'Когда пересаживать фикус?', 'Как вырастить помидоры на балконе?']) {
      await ask(question);
      assert.ok((await page.locator('#answer-text').textContent()).includes('Выберите один из трёх примеров'));
      assert.equal(await page.locator('#sources').isVisible(), false);
      assert.equal(await page.locator('#sources-list').textContent(), '');
    }
    let requests = 0;
    const count = req => { if (new URL(req.url()).pathname === '/ask') requests++; };
    page.on('request', count);
    await ask('   ');
    assert.equal(requests, 0, 'Whitespace must not send a request');
    await input.fill('');
    await submit.click();
    assert.equal(requests, 0);

    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/ask', async route => { await gate; await route.continue(); });
    await input.fill(questions[0][0]);
    await submit.click();
    await page.waitForFunction(() => document.querySelector('#submit').disabled);
    await page.locator('#ask-form').evaluate(form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    assert.equal(await page.locator('#answer').isVisible(), false);
    assert.equal(await page.locator('#sources').isVisible(), false);
    release();
    await waitDone();
    assert.equal(requests, 1, 'Repeated submit must not send a second request');
    await page.unroute('**/ask');
    page.off('request', count);

    for (const status of [403, 500]) {
      await page.route('**/ask', route => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ error: `Ошибка ${status}` }) }));
      await ask(questions[0][0]);
      assert.ok((await page.locator('#error').textContent()).includes(`Ошибка ${status}`));
      assert.equal(await input.inputValue(), questions[0][0]);
      await page.unroute('**/ask');
    }
    for (const body of ['<html>bad response</html>', JSON.stringify({ answer: 'bad', sources: [{}] })]) {
      await page.route('**/ask', route => route.fulfill({ status: 200, contentType: 'application/json', body }));
      await ask(questions[0][0]);
      assert.equal(await page.locator('#error').isVisible(), true);
      assert.equal(await page.locator('#answer').isVisible(), false);
      await page.unroute('**/ask');
    }
    await page.context().setOffline(true);
    await ask(questions[0][0]);
    assert.equal(await page.locator('#error').isVisible(), true);
    await page.context().setOffline(false);

    const unsafe = '<img src=x onerror="window.injected=true">';
    await page.route('**/ask', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      answer: unsafe, sources: [{ title: unsafe, fragment: unsafe, url: 'javascript:alert(1)' }],
    }) }));
    await ask(questions[0][0]);
    assert.equal(await page.locator('#answer-text').textContent(), unsafe);
    assert.equal(await page.locator('#sources-list img').count(), 0);
    assert.equal(await page.locator('#sources-list a').count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.unroute('**/ask');

    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await ask(questions[1][0]);
      assert.ok((await page.locator('#answer-text').textContent()).includes('25–30 °C'));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `width-${width}.png`), fullPage: true });
    }
    assert.deepEqual(jsErrors, [], 'No uncaught browser errors');
    console.log('PASS: examples, sources, keyboard, unknown/empty questions, duplicate submit, HTTP/network/schema errors, recovery, safe text/links, 375/1280px.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
