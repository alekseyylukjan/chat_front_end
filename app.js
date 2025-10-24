// ====== Конфиг окружения (подставляется в env.js) ======
const API_URL = (window.__ENV && window.__ENV.API_URL) || "http://localhost:8000/ask";
const ACCESS_CODE = (window.__ENV && window.__ENV.ACCESS_CODE) || "";

// ====== DOM ======
const chatDiv = document.getElementById("chat");
const questionInput = document.getElementById("question");
const sendBtn = document.getElementById("sendBtn");
const spinner = document.getElementById("spinner");
const downloadBtn = document.getElementById("downloadBtn");
const clearBtn = document.getElementById("clearBtn");
const historyList = document.getElementById("historyList");

// ====== История (сохранение в localStorage) ======
let conversationHistory = loadHistory();

function loadHistory(){
  try{
    const raw = localStorage.getItem("hr_chat_history");
    return raw ? JSON.parse(raw) : [];
  }catch{ return []; }
}
function saveHistory(){
  localStorage.setItem("hr_chat_history", JSON.stringify(conversationHistory));
  renderHistorySidebar();
}
function clearHistory(){
  conversationHistory = [];
  saveHistory();
  chatDiv.innerHTML = "";
}

function addMessageToChat(text, sender='user', meta={}){
  const msg = document.createElement("div");
  msg.className = `message ${sender}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  msg.appendChild(bubble);

  if (meta && (meta.sql_text_raw || meta.sql_text_expanded)){
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = "См. SQL ниже в истории";
    msg.appendChild(m);
  }

  chatDiv.appendChild(msg);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}

function addPreviewTableToChat(rowsInput, columnsInput) {
  if (!rowsInput || (Array.isArray(rowsInput) && rowsInput.length === 0)) return;

  // нормализуем формат
  let rows = rowsInput;
  if (typeof rows === "string") {
    try { rows = JSON.parse(rows); } catch { rows = []; }
  }
  if (!Array.isArray(rows) || !rows.length || typeof rows[0] !== "object" || Array.isArray(rows[0])) return;

  const columns = (columnsInput && columnsInput.length)
    ? columnsInput.map(String)
    : Object.keys(rows[0]);

  const msg = document.createElement("div");
  msg.className = "message bot";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const details = document.createElement("details");
  details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = "Предварительный просмотр строк";

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");

  // thead
  const trHead = document.createElement("tr");
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c;
    trHead.appendChild(th);
  }
  thead.appendChild(trHead);

  // tbody
  for (const r of rows) {
    const tr = document.createElement("tr");
    for (const c of columns) {
      const td = document.createElement("td");
      const v = r?.[c];
      td.textContent = (v === null || v === undefined) ? "" : String(v);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  table.appendChild(thead);
  table.appendChild(tbody);

  details.appendChild(summary);
  details.appendChild(table);
  bubble.appendChild(details);
  msg.appendChild(bubble);

  chatDiv.appendChild(msg);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}

function appendBotMarkdown(markdownText, meta={}) {
  const msg = document.createElement("div");
  msg.className = "message bot";
  const bubble = document.createElement("div");
  bubble.className = "bubble";

  // markdown -> HTML, потом санитайзим
  const html = DOMPurify.sanitize(marked.parse(markdownText, { breaks: true }));
  bubble.innerHTML = html;

  msg.appendChild(bubble);

  if (meta && (meta.sql_text_raw || meta.sql_text_expanded)){
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = "См. SQL ниже в истории";
    msg.appendChild(m);
  }

  chatDiv.appendChild(msg);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}

function renderHistorySidebar(){
  historyList.innerHTML = "";
  conversationHistory.forEach((item, idx) => {
    const card = document.createElement("div");
    card.className = "hist-item";

    const q = document.createElement("div");
    q.className = "hist-q";
    q.textContent = item.role === "user"
      ? `Вы: ${item.content}`
      : `Бот: ${truncate(item.content, 120)}`;
    card.appendChild(q);

    // SQL секция, если есть
    if (item.sql_text_raw || item.sql_text_expanded){
      const sqls = document.createElement("div");
      sqls.className = "sqls";

      const detailsRaw = document.createElement("details");
      const sumRaw = document.createElement("summary");
      sumRaw.textContent = "SQL (raw)";
      const preRaw = document.createElement("code");
      preRaw.textContent = item.sql_text_raw || "—";
      detailsRaw.appendChild(sumRaw);
      detailsRaw.appendChild(preRaw);

      const detailsExp = document.createElement("details");
      const sumExp = document.createElement("summary");
      sumExp.textContent = "SQL (expanded)";
      const preExp = document.createElement("code");
      preExp.textContent = item.sql_text_expanded || "—";
      detailsExp.appendChild(sumExp);
      detailsExp.appendChild(preExp);

      sqls.appendChild(detailsRaw);
      sqls.appendChild(detailsExp);
      card.appendChild(sqls);
    }

    // Таблица (если есть)
    if (item.rows_preview) {
      const preview = document.createElement("div");
      preview.className = "preview";

      const detailsPreview = document.createElement("details");
      detailsPreview.open = true; // сразу открыто

      const summaryPreview = document.createElement("summary");
      summaryPreview.textContent = "Предварительный просмотр строк";

      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const tbody = document.createElement("tbody");

      // Нормализация формата (вдруг строка)
      let rows = item.rows_preview;
      if (typeof rows === "string") {
        try { rows = JSON.parse(rows); } catch { rows = []; }
      }

      // Ожидаем массив объектов
      if (Array.isArray(rows) && rows.length && typeof rows[0] === "object" && !Array.isArray(rows[0])) {
        const columns = (item.columns && item.columns.length)
          ? item.columns.map(String)
          : Object.keys(rows[0]);

        // thead
        const trHead = document.createElement("tr");
        for (const c of columns) {
          const th = document.createElement("th");
          th.textContent = c;
          trHead.appendChild(th);
        }
        thead.appendChild(trHead);

        // tbody
        for (const r of rows) {
          const tr = document.createElement("tr");
          for (const c of columns) {
            const td = document.createElement("td");
            const v = r?.[c];
            td.textContent = (v === null || v === undefined) ? "" : String(v);
            tr.appendChild(td);
          }
          tbody.appendChild(tr);
        }

        table.appendChild(thead);
        table.appendChild(tbody);
        detailsPreview.appendChild(summaryPreview);
        detailsPreview.appendChild(table);
        preview.appendChild(detailsPreview);
        card.appendChild(preview);
      } else {
        // Пусто или неожиданный формат — понятная заметка
        const noteWrap = document.createElement("div");
        noteWrap.className = "meta";
        noteWrap.textContent = "Нет данных для превью (rows_preview пустой или в неожиданном формате).";
        detailsPreview.appendChild(summaryPreview);
        detailsPreview.appendChild(noteWrap);
        preview.appendChild(detailsPreview);
        card.appendChild(preview);
      }
    }

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${item.timestamp || ""}${item.rows_count != null ? ` • rows: ${item.rows_count}` : ""}`;
    card.appendChild(meta);

    historyList.appendChild(card);
  });
}
renderHistorySidebar();

function truncate(s, n){ return s && s.length>n ? s.slice(0,n)+"…" : (s||""); }
function nowStr(){
  const d = new Date();
  return d.toLocaleString();
}

// ====== Отправка ======
async function sendQuestion(){
  const questionText = questionInput.value.trim();
  if(!questionText) return;

  addMessageToChat(questionText, 'user');

  // формируем последние 4 сообщения (как в исходнике)
  const recentHistory = conversationHistory.slice(-4).map(({role, content}) => ({role, content}));
  recentHistory.push({role:"user", content:questionText});

  const payload = { question: questionText, history: recentHistory };

  // UI — загрузка
  sendBtn.classList.add("loading");
  sendBtn.setAttribute("disabled","true");

  try{
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Access-Code": ACCESS_CODE
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    const answerText = data.answer || "Нет ответа.";
    // Плавный вывод
    appendBotMarkdown(answerText, { sql_text_raw: data.sql_text_raw, sql_text_expanded: data.sql_text_expanded });
    // Таблица прямо в чат
    if (data.rows_preview) {
      addPreviewTableToChat(data.rows_preview, data.columns);
    }

    // Запоминаем обмен. Храним SQL, если они были.
    conversationHistory.push({
      role: "user",
      content: questionText,
      timestamp: nowStr()
    });

    const botRecord = {
      role: "bot",
      content: answerText,
      timestamp: nowStr(),
      rows_count: data.rows_count ?? null,
      mode: data.mode || null
    };

    // если бэк вернул SQL — кладём в историю
    if (data.sql_text_raw || data.sql_text_expanded || data.rows_preview) {  
      botRecord.sql_text_raw = data.sql_text_raw || null;  
      botRecord.sql_text_expanded = data.sql_text_expanded || null;  
      botRecord.rows_preview = data.rows_preview || null;
      botRecord.columns = data.columns || null;
    }

    conversationHistory.push(botRecord);
    saveHistory();
  }catch(e){
    addMessageToChat("Ошибка при отправке запроса: " + (e.message||e), 'bot');
  }finally{
    sendBtn.classList.remove("loading");
    sendBtn.removeAttribute("disabled");
  }

  questionInput.value = "";
}

sendBtn.onclick = sendQuestion;
questionInput.addEventListener("keydown", e=>{
  if (e.key === "Enter" && !e.shiftKey){
    e.preventDefault();
    sendQuestion();
  }
});

downloadBtn.onclick = () => {
  let text = "";
  for (const msg of conversationHistory){
    if (msg.role === "user"){
      text += `Пользователь [${msg.timestamp||""}]: ${msg.content}\n`;
    } else {
      text += `Бот [${msg.timestamp||""}]: ${msg.content}\n`;
      if (msg.sql_text_raw) {
        text += `--- SQL (raw) ---\n${msg.sql_text_raw}\n`;
      }
      if (msg.sql_text_expanded) {
        text += `--- SQL (expanded) ---\n${msg.sql_text_expanded}\n`;
      }
      if (msg.rows_count!=null){
        text += `rows_count: ${msg.rows_count}\n`;
      }
    }
    text += `\n`;
  }
  const blob = new Blob([text], {type:"text/plain"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "история_общения.txt"; a.click();
  URL.revokeObjectURL(url);
};

clearBtn.onclick = () => {
  if (confirm("Очистить историю переписки?")) clearHistory();
};









