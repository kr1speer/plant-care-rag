(() => {
  "use strict";

  const form = document.getElementById("ask-form");
  const question = document.getElementById("question");
  const submit = document.getElementById("submit");
  const status = document.getElementById("status");
  const error = document.getElementById("error");
  const answerBox = document.getElementById("answer");
  const answerText = document.getElementById("answer-text");
  const sourcesBox = document.getElementById("sources");
  const sourcesList = document.getElementById("sources-list");
  const examples = [...document.querySelectorAll("[data-question]")];
  let busy = false;

  examples.forEach((button) => {
    button.addEventListener("click", () => {
      question.value = button.dataset.question;
      question.focus();
    });
  });

  function validResult(result) {
    return (
      result &&
      typeof result.answer === "string" &&
      Array.isArray(result.sources) &&
      result.sources.every(
        (source) =>
          source &&
          ["title", "fragment", "url"].every((key) => typeof source[key] === "string"),
      )
    );
  }

  function sourceCard(source, index) {
    const card = document.createElement("div");
    card.className = "card source";
    const title = document.createElement("p");
    const bold = document.createElement("b");
    bold.textContent = `[${index + 1}] ${source.title}`;
    title.append(bold);
    const fragment = document.createElement("p");
    fragment.className = "fragment";
    fragment.textContent = source.fragment;
    card.append(title, fragment);
    try {
      const url = new URL(source.url);
      if (["http:", "https:"].includes(url.protocol)) {
        const link = document.createElement("a");
        link.href = url.href;
        link.textContent = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        card.append(link);
      }
    } catch {
      // Keep the source text, but never render an invalid URL as a link.
    }
    return card;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    error.hidden = true;
    answerBox.hidden = true;
    sourcesBox.hidden = true;
    sourcesList.replaceChildren();
    status.textContent = "";
    const value = question.value.trim();
    if (!value) {
      error.textContent = "Введите непустой вопрос.";
      error.hidden = false;
      question.focus();
      return;
    }

    busy = true;
    submit.disabled = true;
    question.readOnly = true;
    examples.forEach((button) => {
      button.disabled = true;
    });
    form.setAttribute("aria-busy", "true");
    status.textContent = "Готовим демонстрационный ответ…";
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify({ question: value }),
      });
      let result;
      try {
        result = await response.json();
      } catch {
        throw new Error("Сервер вернул некорректный ответ. Попробуйте ещё раз.");
      }
      if (!response.ok) {
        throw new Error(
          typeof result?.error === "string"
            ? result.error
            : `Ошибка сервера (${response.status}). Попробуйте ещё раз.`,
        );
      }
      if (!validResult(result)) {
        throw new Error("Сервер вернул некорректный ответ. Попробуйте ещё раз.");
      }
      answerText.textContent = result.answer;
      result.sources.forEach((source, index) => {
        sourcesList.append(sourceCard(source, index));
      });
      answerBox.hidden = false;
      sourcesBox.hidden = result.sources.length === 0;
      status.textContent = "Ответ готов.";
    } catch (failure) {
      error.textContent =
        failure instanceof TypeError
          ? "Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз."
          : failure.message;
      error.hidden = false;
      status.textContent = "";
    } finally {
      busy = false;
      submit.disabled = false;
      question.readOnly = false;
      examples.forEach((button) => {
        button.disabled = false;
      });
      form.setAttribute("aria-busy", "false");
    }
  });
})();
