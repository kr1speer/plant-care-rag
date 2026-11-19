const { test, expect } = require("@playwright/test");

const REFUSAL = "В документах нет этой информации";
const examples = [
  "Почему у монстеры мелкие листья без прорезей?",
  "Какая температура нужна фикусу Бенджамина летом и зимой?",
  "Когда и как пересаживать орхидею фаленопсис?",
];
const source = (title) => ({
  doc_id: "D02",
  title,
  section: "Свет",
  fragment: `Фрагмент статьи «${title}»`,
  url: `https://ru.wikipedia.org/wiki/${title}`,
});
const answered = {
  answer: "Мелкие листья связаны с недостатком света. [D02]",
  refused: false,
  sources: [source("Монстера"), source("Фикус")],
};
const refused = { answer: REFUSAL, refused: true, sources: [] };

// The real /ask is replaced: these tests check the UI contract, not retrieval.
async function mockAsk(page, json, status = 200) {
  await page.unroute("**/ask");
  await page.route("**/ask", (route) => route.fulfill({ status, json }));
}

async function ask(page, question = examples[0]) {
  await page.getByLabel("Ваш вопрос").fill(question);
  await page.getByRole("button", { name: "Спросить", exact: true }).click();
  await expect(page.locator("#submit")).toBeEnabled();
}

const errorsByPage = new WeakMap();

test.beforeEach(async ({ page }) => {
  errorsByPage.set(page, []);
  page.on("pageerror", (error) => errorsByPage.get(page).push(error.message));
  const response = await page.goto("/");
  expect(response.status()).toBe(200);
  await expect(page.getByText("Демонстрационная версия")).toHaveCount(0);
});

test.afterEach(async ({ page }) => {
  // Intentional HTTP failures are distinct from uncaught JavaScript errors.
  expect(errorsByPage.get(page) || []).toEqual([]);
});

test("examples are only hints: they fill the field and send nothing", async ({
  page,
}) => {
  let requests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/ask") requests++;
  });
  for (const question of examples) {
    await page.getByRole("button", { name: question, exact: true }).click();
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue(question);
    await expect(page.getByLabel("Ваш вопрос")).toBeFocused();
  }
  expect(requests).toBe(0);
});

test("free-form question sends one request with the typed text", async ({ page }) => {
  await mockAsk(page, answered);
  const request = page.waitForRequest("**/ask");
  await ask(page, "Как часто поливать кактус зимой?");
  expect((await request).postDataJSON()).toEqual({
    question: "Как часто поливать кактус зимой?",
  });
});

test("answer shows text and every source with title, fragment and link", async ({
  page,
}) => {
  await mockAsk(page, answered);
  await ask(page);
  await expect(page.locator("#answer-text")).toContainText("недостатком света");
  await expect(page.locator("#refusal")).toBeHidden();
  const cards = page.locator("#sources-list .source");
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toContainText("[1] Монстера");
  await expect(cards.first()).toContainText("Фрагмент статьи «Монстера»");
  const link = cards.first().locator("a");
  await expect(link).toHaveAttribute("href", /^https:\/\/ru\.wikipedia\.org\//);
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
});

test("refusal is a separate state without sources", async ({ page }) => {
  await mockAsk(page, refused);
  await ask(page, "Как вырастить помидоры на балконе?");
  await expect(page.locator("#refusal-text")).toHaveText(REFUSAL);
  await expect(page.locator("#answer")).toBeHidden();
  await expect(page.locator("#sources")).toBeHidden();
  await expect(page.locator("#sources-list")).toBeEmpty();
});

test("each new result replaces the previous state", async ({ page }) => {
  await mockAsk(page, refused);
  await ask(page);
  await expect(page.locator("#refusal")).toBeVisible();
  await mockAsk(page, answered);
  await ask(page);
  await expect(page.locator("#refusal")).toBeHidden();
  await expect(page.locator("#answer-text")).toContainText("недостатком света");
  await mockAsk(page, refused);
  await ask(page);
  await expect(page.locator("#answer")).toBeHidden();
  await expect(page.locator("#sources")).toBeHidden();
  await expect(page.locator("#refusal")).toBeVisible();
});

test("empty input and whitespace do not send requests", async ({ page }) => {
  let requests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/ask") requests++;
  });
  await ask(page, "   ");
  await expect(page.locator("#error")).toContainText("Введите непустой вопрос");
  await page.getByLabel("Ваш вопрос").fill("");
  await page.locator("#submit").click();
  expect(requests).toBe(0);
});

test("pending request hides old results, blocks duplicates and reports slow reply", async ({
  page,
}) => {
  await mockAsk(page, answered);
  await ask(page);
  await page.unroute("**/ask");
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let requests = 0;
  await page.route("**/ask", async (route) => {
    requests++;
    await gate;
    await route.fulfill({ json: answered });
  });
  try {
    await page.getByLabel("Ваш вопрос").fill(examples[1]);
    await page.locator("#submit").click();
    await expect(page.locator("#submit")).toBeDisabled();
    await expect(page.locator("#answer")).toBeHidden();
    await expect(page.locator("#sources")).toBeHidden();
    await expect(page.locator("#status")).toContainText("Ищем в статьях");
    await page
      .locator("#ask-form")
      .evaluate((form) =>
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
      );
    await expect(page.locator("#status")).toContainText("дольше обычного", {
      timeout: 12000,
    });
    release();
    await expect(page.locator("#answer-text")).toContainText("недостатком света");
    expect(requests).toBe(1);
  } finally {
    release();
  }
});

for (const [status, text] of [
  [403, "Ошибка 403"],
  [502, "Сервис LLM отклонил запрос"],
  [503, "Сервис LLM временно недоступен"],
]) {
  test(`HTTP ${status} shows its message and allows retry`, async ({ page }) => {
    await mockAsk(page, { error: text }, status);
    await ask(page);
    await expect(page.locator("#error")).toContainText(text);
    await expect(page.locator("#answer")).toBeHidden();
    await expect(page.locator("#refusal")).toBeHidden();
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0]);
    await mockAsk(page, answered);
    await ask(page);
    await expect(page.locator("#error")).toBeHidden();
    await expect(page.locator("#answer-text")).toContainText("недостатком света");
  });
}

for (const [status, text] of [
  [502, "некорректный ответ"],
  [503, "временно недоступен"],
]) {
  test(`HTTP ${status} without a message uses a clear fallback`, async ({ page }) => {
    await mockAsk(page, {}, status);
    await ask(page);
    await expect(page.locator("#error")).toContainText(text);
  });
}

for (const [status, body, message] of [
  [502, "", "Сервис LLM вернул некорректный ответ"],
  [503, "<html>Unavailable</html>", "Сервис LLM временно недоступен"],
]) {
  test(`HTTP ${status} with a non-JSON body uses the status`, async ({ page }) => {
    await page.route("**/ask", (route) =>
      route.fulfill({ status, contentType: "text/html", body }),
    );
    await ask(page);
    await expect(page.locator("#error")).toContainText(message);
  });
}

for (const [name, body] of [
  ["invalid JSON", "<html>bad response</html>"],
  ["missing refused", JSON.stringify({ answer: "bad", sources: [] })],
  ["invalid source", JSON.stringify({ answer: "bad", refused: false, sources: [{}] })],
]) {
  test(`${name} is reported and recoverable`, async ({ page }) => {
    await page.route("**/ask", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body }),
    );
    await ask(page);
    await expect(page.locator("#error")).toContainText("некорректный ответ");
    await expect(page.locator("#answer")).toBeHidden();
    await expect(page.locator("#refusal")).toBeHidden();
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0]);
  });
}

test("network failure keeps input and allows retry", async ({ page, context }) => {
  await context.setOffline(true);
  await ask(page);
  await expect(page.locator("#error")).toBeVisible();
  await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0]);
  await context.setOffline(false);
  await mockAsk(page, answered);
  await ask(page);
  await expect(page.locator("#answer-text")).toContainText("недостатком света");
});

test("request timeout shows a message and allows retry", async ({ page }) => {
  // Shorten the 90 s limit so the timeout branch runs in test time.
  await page.addInitScript(() => {
    const timeout = AbortSignal.timeout.bind(AbortSignal);
    AbortSignal.timeout = () => timeout(200);
  });
  await page.reload();
  await page.route("**/ask", () => {}); // never answers
  await ask(page);
  await expect(page.locator("#error")).toContainText("Ответ не пришёл за 90 секунд");
  await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0]);
  await mockAsk(page, answered);
  await ask(page);
  await expect(page.locator("#answer-text")).toContainText("недостатком света");
});

test("HTML is rendered as text and unsafe links are omitted", async ({ page }) => {
  const unsafe = '<img src=x onerror="window.injected=true">';
  await mockAsk(page, {
    answer: unsafe,
    refused: false,
    sources: [{ title: unsafe, fragment: unsafe, url: "javascript:alert(1)" }],
  });
  await ask(page);
  await expect(page.locator("#answer-text")).toHaveText(unsafe);
  await expect(page.locator("#sources-list")).toContainText(unsafe);
  await expect(page.locator("#sources-list img, #sources-list a")).toHaveCount(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
});

for (const width of [375, 1280]) {
  test(`layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockAsk(page, answered);
    await ask(page);
    await expect(page.locator("#answer-text")).toContainText("недостатком света");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: test.info().outputPath(`layout-${width}.png`),
      fullPage: true,
    });
  });
}

// One real pass through BM25 and the stub LLM keeps the end-to-end path honest.
test("real /ask answers with sources and refuses off-topic questions", async ({
  page,
}) => {
  await ask(page, examples[1]);
  await expect(page.locator("#answer-text")).toContainText("25–30 °C");
  await expect(page.locator("#sources-list a").first()).toBeVisible();
  await ask(page, "Как вырастить помидоры на балконе?");
  await expect(page.locator("#refusal-text")).toHaveText(REFUSAL);
  await expect(page.locator("#sources")).toBeHidden();
});
