const { test, expect } = require("@playwright/test");

const examples = [
  [
    "Почему у монстеры мелкие листья без прорезей?",
    "недостатком света",
    "Монстера деликатесная",
  ],
  [
    "Какая температура нужна фикусу Бенджамина летом и зимой?",
    "25–30 °C",
    "Фикус бенджамина",
  ],
  [
    "Когда и как пересаживать орхидею фаленопсис?",
    "раз в год после цветения",
    "Фаленопсис",
  ],
];

async function ask(page, question) {
  await page.getByLabel("Ваш вопрос").fill(question);
  await page.getByRole("button", { name: "Спросить", exact: true }).click();
  await expect(page.locator("#submit")).toBeEnabled();
}

async function expectRecovery(page) {
  await expect(page.locator("#error")).toBeVisible();
  await expect(page.locator("#answer")).toBeHidden();
  await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0][0]);
  await page.unroute("**/ask");
  await ask(page, examples[0][0]);
  await expect(page.locator("#answer-text")).toContainText(examples[0][1]);
}

const errorsByPage = new WeakMap();

test.beforeEach(async ({ page }) => {
  errorsByPage.set(page, []);
  page.on("pageerror", (error) => errorsByPage.get(page).push(error.message));
  const response = await page.goto("/");
  expect(response.status()).toBe(200);
  await expect(
    page.getByText("Демонстрационная версия: BM25 и LLM не подключены", {
      exact: true,
    }),
  ).toBeVisible();
});

test.afterEach(async ({ page }) => {
  // Intentional HTTP failures are distinct from uncaught JavaScript errors.
  expect(errorsByPage.get(page) || []).toEqual([]);
});

for (const [question, fact, title] of examples) {
  test(`example: ${title}`, async ({ page }) => {
    await page.getByRole("button", { name: question, exact: true }).click();
    await expect(page.getByLabel("Ваш вопрос")).toBeFocused();
    await page.getByLabel("Ваш вопрос").press("Enter");
    await expect(page.locator("#answer-text")).toContainText(fact);
    await expect(page.locator("#sources-list")).toContainText(title);
    const link = page.locator("#sources-list a");
    await expect(link).toHaveCount(1);
    await expect(link).toHaveAttribute("href", /^https:\/\/ru\.wikipedia\.org\//);
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
}

test("normalization and replacement of an earlier answer", async ({ page }) => {
  await ask(page, examples[0][0]);
  await ask(page, "  КАКАЯ  ТЕМПЕРАТУРА НУЖНА ФИКУСУ БЕНДЖАМИНА ЛЕТОМ И ЗИМОЙ!!!  ");
  await expect(page.locator("#answer-text")).toContainText("25–30 °C");
  await expect(page.locator("#sources-list")).not.toContainText("Монстера");
  await expect(page.locator("#sources-list a")).toHaveCount(1);
});

for (const question of [
  "Как поливать орхидею?",
  "Когда пересаживать фикус?",
  "Как вырастить помидоры на балконе?",
]) {
  test(`unsupported: ${question}`, async ({ page }) => {
    await ask(page, examples[0][0]);
    await ask(page, question);
    await expect(page.locator("#answer-text")).toContainText(
      "Выберите один из трёх примеров",
    );
    await expect(page.locator("#sources")).toBeHidden();
    await expect(page.locator("#sources-list")).toBeEmpty();
  });
}

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

test("pending request hides old results and blocks duplicate submission", async ({
  page,
}) => {
  await ask(page, examples[0][0]);
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let requests = 0;
  await page.route("**/ask", async (route) => {
    requests++;
    await gate;
    await route.continue();
  });
  try {
    await page.getByLabel("Ваш вопрос").fill(examples[1][0]);
    await page.locator("#submit").click();
    await expect(page.locator("#submit")).toBeDisabled();
    await expect(page.locator("#answer")).toBeHidden();
    await expect(page.locator("#sources")).toBeHidden();
    await page
      .locator("#ask-form")
      .evaluate((form) =>
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
      );
    release();
    await expect(page.locator("#answer-text")).toContainText(examples[1][1]);
    expect(requests).toBe(1);
  } finally {
    release();
  }
});

for (const status of [403, 500]) {
  test(`HTTP ${status} and recovery`, async ({ page }) => {
    await page.route("**/ask", (route) =>
      route.fulfill({ status, json: { error: `Ошибка ${status}` } }),
    );
    await ask(page, examples[0][0]);
    await expect(page.locator("#error")).toContainText(`Ошибка ${status}`);
    await expectRecovery(page);
  });
}

for (const [name, body] of [
  ["invalid JSON", "<html>bad response</html>"],
  ["invalid schema", JSON.stringify({ answer: "bad", sources: [{}] })],
]) {
  test(`${name} and recovery`, async ({ page }) => {
    await page.route("**/ask", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body }),
    );
    await ask(page, examples[0][0]);
    await expectRecovery(page);
  });
}

test("network failure keeps input and allows retry", async ({ page, context }) => {
  await context.setOffline(true);
  await ask(page, examples[0][0]);
  await expect(page.locator("#error")).toBeVisible();
  await expect(page.getByLabel("Ваш вопрос")).toHaveValue(examples[0][0]);
  await context.setOffline(false);
  await ask(page, examples[0][0]);
  await expect(page.locator("#answer-text")).toContainText(examples[0][1]);
});

test("HTML is rendered as text and unsafe links are omitted", async ({ page }) => {
  const unsafe = '<img src=x onerror="window.injected=true">';
  await page.route("**/ask", (route) =>
    route.fulfill({
      json: {
        answer: unsafe,
        sources: [{ title: unsafe, fragment: unsafe, url: "javascript:alert(1)" }],
      },
    }),
  );
  await ask(page, examples[0][0]);
  await expect(page.locator("#answer-text")).toHaveText(unsafe);
  await expect(page.locator("#sources-list")).toContainText(unsafe);
  await expect(page.locator("#sources-list img, #sources-list a")).toHaveCount(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
});

for (const width of [375, 1280]) {
  test(`layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await ask(page, examples[1][0]);
    await expect(page.locator("#answer-text")).toContainText(examples[1][1]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: test.info().outputPath(`layout-${width}.png`),
      fullPage: true,
    });
  });
}
