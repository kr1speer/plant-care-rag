// Примерные данные для прототипа. Потом ask() заменим на запрос к API.
const SAMPLES = [
  {
    keywords: ["монстер", "полив"],
    answer: "Зимой монстеру поливают реже — примерно раз в 7–10 дней, когда верхний слой почвы просохнет на 2–3 см. Избыток воды в холодное время приводит к загниванию корней. [1], [2]",
    sources: [
      { title: "Монстера: уход в домашних условиях", fragment: "…в период покоя полив сокращают, ориентируясь на просыхание верхнего слоя почвы…", url: "https://example.com/monstera-care" },
      { title: "Полив комнатных растений зимой", fragment: "…переувлажнение при низкой температуре — частая причина корневой гнили…", url: "https://example.com/winter-watering" },
    ],
  },
  {
    keywords: ["фикус", "желте"],
    answer: "Листья фикуса чаще всего желтеют и опадают из-за переувлажнения, сквозняков или резкой смены места. Проверьте почву и не переставляйте растение. [1]",
    sources: [
      { title: "Почему фикус сбрасывает листья", fragment: "…фикус болезненно реагирует на перестановку и холодный воздух…", url: "https://example.com/ficus-leaves" },
    ],
  },
  {
    keywords: ["орхиде", "пересад"],
    answer: "Орхидею пересаживают раз в 2–3 года после цветения, в прозрачный горшок со свежей корой. Повреждённые корни удаляют. [1]",
    sources: [
      { title: "Пересадка орхидеи фаленопсис", fragment: "…лучшее время для пересадки — после окончания цветения…", url: "https://example.com/orchid-repot" },
    ],
  },
];

async function ask(question) {
  const q = question.toLowerCase();
  return SAMPLES.find((s) => s.keywords.some((k) => q.includes(k))) || null;
}

const answerBox = document.getElementById("answer");
const answerText = document.getElementById("answer-text");
const sourcesBox = document.getElementById("sources");
const sourcesList = document.getElementById("sources-list");

document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const result = await ask(document.getElementById("question").value);

  answerBox.hidden = false;
  sourcesList.innerHTML = "";

  if (!result) {
    answerText.textContent = "Не удалось найти ответ в базе статей.";
    sourcesBox.hidden = true;
    return;
  }

  answerText.textContent = result.answer;
  result.sources.forEach((s, i) => {
    const card = document.createElement("div");
    card.className = "card source";
    card.innerHTML = `<p><b>[${i + 1}] </b></p><p class="fragment"></p><a target="_blank"></a>`;
    card.querySelector("b").append(s.title);
    card.querySelector(".fragment").textContent = s.fragment;
    card.querySelector("a").href = card.querySelector("a").textContent = s.url;
    sourcesList.append(card);
  });
  sourcesBox.hidden = false;
});
