const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let notebookId = null;
let selectedSources = new Set();
let indexed = false;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body instanceof FormData || typeof opts.body === "string" ? opts.body : opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Lỗi API");
  }
  return res.json();
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2800);
}

function showLoading(v, message = "Đang xử lý...") {
  const el = $("#loading");
  el.classList.toggle("hidden", !v);
  const span = el.querySelector("span");
  if (span) span.textContent = message;
}

function showChatTyping(show) {
  const box = $("#chatMessages");
  let el = $("#chatTyping");
  if (show) {
    if (!el) {
      el = document.createElement("div");
      el.id = "chatTyping";
      el.className = "msg bot typing-indicator";
      el.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="typing-text">Đang suy nghĩ...</span>';
      box.appendChild(el);
    }
    scrollChat();
  } else {
    el?.remove();
  }
}

function showUploadBusy(show) {
  $("#uploadZone")?.classList.toggle("is-busy", show);
  $("#fileInput").disabled = show;
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
}

let confirmResolve = null;

function showConfirm({ title, message, confirmText = "Xóa", cancelText = "Hủy" }) {
  return new Promise((resolve) => {
    $("#confirmModalTitle").textContent = title;
    $("#confirmModalMessage").innerHTML = message;
    $("#confirmModalCancel").textContent = cancelText;
    const confirmBtn = $("#confirmModalConfirm");
    confirmBtn.textContent = confirmText;
    confirmBtn.disabled = false;
    $("#confirmModal").classList.remove("hidden");
    confirmResolve = resolve;
    setTimeout(() => $("#confirmModalCancel").focus(), 50);
  });
}

function closeConfirm(result) {
  $("#confirmModal").classList.add("hidden");
  if (confirmResolve) confirmResolve(result);
  confirmResolve = null;
}

$("#confirmModalCancel")?.addEventListener("click", () => closeConfirm(false));
$("#confirmModalBackdrop")?.addEventListener("click", () => closeConfirm(false));
$("#confirmModalConfirm")?.addEventListener("click", async () => {
  const btn = $("#confirmModalConfirm");
  btn.disabled = true;
  closeConfirm(true);
});
$("#confirmModal")?.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeConfirm(false);
});

function extBadge(name) {
  const ext = name.includes(".") ? name.split(".").pop().toUpperCase() : "FILE";
  return ext.slice(0, 4);
}

/* ── Home ── */
async function loadNotebooks() {
  const list = await api("/api/notebooks");
  const grid = $("#notebookGrid");
  const countEl = $("#nbCount");
  if (countEl) countEl.textContent = list.length ? `${list.length} notebook` : "";

  if (!list.length) {
    grid.innerHTML = `
      <div class="nb-empty">
        <div class="nb-empty-icon">📂</div>
        <p>Chưa có notebook nào.<br/>Nhấn <strong>Tạo Notebook mới</strong> ở trên để bắt đầu.</p>
      </div>`;
    return;
  }
  grid.innerHTML = list
    .map(
      (nb) => `
    <div class="nb-card" data-id="${nb.id}">
      <div class="nb-card-icon">📓</div>
      <h3>${esc(nb.name)}</h3>
      <p>${nb.source_count || 0} nguồn · cập nhật ${(nb.updated_at || "").slice(0, 10)}</p>
      <div class="nb-card-actions">
        <button class="btn-ghost open-nb" data-id="${nb.id}">Mở notebook</button>
        <button class="btn-del-sm del-nb" data-id="${nb.id}" data-name="${escAttr(nb.name)}" title="Xóa notebook">✕</button>
      </div>
    </div>`
    )
    .join("");
  $$(".open-nb").forEach((b) => b.onclick = () => openNotebook(b.dataset.id));
  $$(".del-nb").forEach((b) =>
    b.onclick = async (e) => {
      e.stopPropagation();
      const name = b.dataset.name || "notebook này";
      const ok = await showConfirm({
        title: "Xóa notebook?",
        message: `Bạn sắp xóa <strong>${esc(name)}</strong> cùng toàn bộ tài liệu, chat và ghi chú. Hành động này không thể hoàn tác.`,
        confirmText: "Xóa notebook",
      });
      if (!ok) return;
      await api(`/api/notebooks/${b.dataset.id}`, { method: "DELETE" });
      toast("Đã xóa notebook");
      loadNotebooks();
    }
  );
}

$("#btnCreateNb")?.addEventListener("click", async () => {
  const nb = await api("/api/notebooks", { method: "POST", body: { name: "Notebook mới" } });
  openNotebook(nb.id);
});

/* ── Workspace ── */
async function openNotebook(id) {
  notebookId = id;
  location.hash = id;

  // Reset all panel state immediately before any async fetches
  indexed = false;
  selectedSources.clear();
  _invalidateStudioCache();
  $("#nbTitle").value = "";
  $("#statusText").textContent = "Đang tải…";
  $("#srcCount").textContent = "0";
  $("#sourcesList").innerHTML = "";
  $("#chatMessages").innerHTML = `<div class="chat-welcome"><div class="cw-icon">💬</div><h3>Bắt đầu hội thoại</h3><p>Upload tài liệu, chọn nguồn, rồi hỏi bất kỳ điều gì.</p></div>`;
  const saved = $("#studioSaved");
  saved.classList.add("hidden");
  saved.innerHTML = "";
  $("#notesList").innerHTML = "";

  showView("workspace");
  await refreshNotebook();
  await loadChatHistory();
  await loadSuggestions();
  await loadNotes();
  await loadStudioSaved();
}

async function refreshNotebook() {
  const data = await api(`/api/notebooks/${notebookId}`);
  $("#nbTitle").value = data.name;
  indexed = data.indexed;
  $("#statusText").textContent = data.indexed ? `${data.stats.chunks} chunks` : "chưa index";
  renderSources(data.sources || []);
}

function renderSources(sources) {
  $("#srcCount").textContent = sources.length;
  const list = $("#sourcesList");
  if (!sources.length) {
    list.innerHTML = `<p style="font-size:12px;color:var(--muted);text-align:center;padding:16px 8px;">Chưa có nguồn trong danh sách.</p>`;
    selectedSources.clear();
    updateSelCount();
    return;
  }
  if (selectedSources.size === 0) sources.forEach((s) => selectedSources.add(s));

  const allChecked = sources.every((s) => selectedSources.has(s));
  list.innerHTML = `
    <div class="select-all" id="chkAllRow">
      <input type="checkbox" id="chkAll" ${allChecked ? "checked" : ""}/>
      <span class="chk-box" id="chkAllBox"></span>
      Chọn tất cả
    </div>
    ${sources
      .map((s) => {
        const isNote = s.startsWith("[Ghi chú]");
        const label = isNote ? s.slice(10) : s;
        const checked = selectedSources.has(s);
        const del = isNote ? "" : `<button class="src-del" data-f="${escAttr(s)}" title="Xóa nguồn">✕</button>`;
        return `<div class="src-item${checked ? "" : " is-unchecked"}" data-src="${escAttr(s)}">
          <span class="chk-wrap src-chk-wrap" data-src="${escAttr(s)}">
            <input type="checkbox" class="src-chk" data-src="${escAttr(s)}" ${checked ? "checked" : ""}/>
            <span class="chk-box"></span>
          </span>
          <span class="src-badge">${isNote ? "NOTE" : extBadge(s)}</span>
          <span class="src-name" title="${escAttr(label)}">${esc(label)}</span>
          ${del}
        </div>`;
      })
      .join("")}
  `;

  const chkAllInput = $("#chkAll");

  // "Chọn tất cả" row click (excluding delete buttons)
  $("#chkAllRow").onclick = () => {
    const newState = !sources.every((s) => selectedSources.has(s));
    sources.forEach((s) => (newState ? selectedSources.add(s) : selectedSources.delete(s)));
    chkAllInput.checked = newState;
    // Update item visuals without full re-render
    $$(".src-item").forEach((item) => {
      const inp = item.querySelector(".src-chk");
      if (inp) { inp.checked = newState; item.classList.toggle("is-unchecked", !newState); }
    });
    updateSelCount();
    loadSuggestions();
  };

  $$(".src-chk-wrap").forEach((wrap) =>
    wrap.onclick = (e) => {
      e.stopPropagation();
      const src = wrap.dataset.src;
      const inp = wrap.querySelector(".src-chk");
      const newChecked = !inp.checked;
      inp.checked = newChecked;
      newChecked ? selectedSources.add(src) : selectedSources.delete(src);
      wrap.closest(".src-item").classList.toggle("is-unchecked", !newChecked);
      chkAllInput.checked = sources.every((s) => selectedSources.has(s));
      updateSelCount();
      loadSuggestions();
    }
  );
  $$(".src-del").forEach((b) =>
    b.onclick = async () => {
      const filename = b.dataset.f;
      const ok = await showConfirm({
        title: "Xóa nguồn?",
        message: `Xóa tài liệu <strong>${esc(filename)}</strong> khỏi notebook? Nội dung sẽ bị gỡ khỏi chỉ mục tìm kiếm.`,
        confirmText: "Xóa nguồn",
      });
      if (!ok) return;
      await api(`/api/notebooks/${notebookId}/sources/${encodeURIComponent(filename)}`, { method: "DELETE" });
      selectedSources.delete(filename);
      toast("Đã xóa nguồn");
      await refreshNotebook();
      loadSuggestions();
    }
  );
  updateSelCount();
}

function updateSelCount() {
  $("#selCount").textContent = `${selectedSources.size} nguồn`;
}

/* Upload */
$("#fileInput")?.addEventListener("change", async (e) => uploadFiles(e.target.files));
const uploadZone = $("#uploadZone");
if (uploadZone) {
  uploadZone.ondragover = (e) => { e.preventDefault(); uploadZone.classList.add("is-dragover"); };
  uploadZone.ondragleave = (e) => {
    if (!uploadZone.contains(e.relatedTarget)) uploadZone.classList.remove("is-dragover");
  };
  uploadZone.ondrop = (e) => {
    e.preventDefault();
    uploadZone.classList.remove("is-dragover");
    uploadFiles(e.dataTransfer.files);
  };
}

async function uploadFiles(files) {
  if (!files.length) return;
  showUploadBusy(true);
  try {
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    const res = await fetch(`/api/notebooks/${notebookId}/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    data.added.forEach((s) => selectedSources.add(s));
    indexed = data.indexed;
    $("#statusText").textContent = `${data.stats.chunks} chunks`;
    toast(`Đã thêm ${data.added.length} tài liệu`);
    renderSources(data.sources);
    await loadSuggestions();
  } catch (err) {
    toast(err.message);
  } finally {
    showUploadBusy(false);
    $("#fileInput").value = "";
  }
}

/* Chat */
async function loadChatHistory() {
  const history = await api(`/api/notebooks/${notebookId}/chat`);
  const box = $("#chatMessages");
  if (!history.length) {
    box.innerHTML = `<div class="chat-welcome"><div class="cw-icon">💬</div><h3>Bắt đầu hội thoại</h3><p>Upload tài liệu, chọn nguồn, rồi hỏi bất kỳ điều gì.</p></div>`;
    return;
  }
  box.innerHTML = "";
  history.forEach((h) => {
    appendMessage("user", h.query);
    appendMessage("bot", h.answer_html || h.answer, h.sources);
  });
  scrollChat();
}

function appendMessage(role, text, sources) {
  const box = $("#chatMessages");
  $(".chat-welcome", box)?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "bot") {
    div.innerHTML = typeof text === "string" && text.includes("<sup") ? text : formatCites(text);
    if (sources?.length) {
      const tags = document.createElement("div");
      tags.className = "msg-tags";
      [...new Set(sources.map((s) => (typeof s === "string" ? s : s.source)))].forEach((s) => {
        const t = document.createElement("span");
        t.className = "msg-tag";
        t.textContent = s;
        tags.appendChild(t);
      });
      div.appendChild(tags);
    }
  } else {
    div.textContent = text;
  }
  box.appendChild(div);
  return true;
}

function formatCites(text) {
  return text.replace(/\[(\d+)\]/g, '<sup class="cite" title="Nguồn $1">$1</sup>');
}

function scrollChat() {
  const el = $("#chatMessages");
  el.scrollTop = el.scrollHeight;
}

async function loadSuggestions() {
  // Suggestions temporarily disabled
}

function appendStreamingMessage() {
  const box = $("#chatMessages");
  $(".chat-welcome", box)?.remove();
  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = '<div class="msg-body"></div>';
  box.appendChild(div);
  return div;
}

function finalizeStreamingMessage(div, sources) {
  if (!sources?.length) return;
  const tags = document.createElement("div");
  tags.className = "msg-tags";
  [...new Set(sources.map((s) => (typeof s === "string" ? s : s.source)))].forEach((s) => {
    const t = document.createElement("span");
    t.className = "msg-tag";
    t.textContent = s;
    tags.appendChild(t);
  });
  div.appendChild(tags);
}

async function sendChat(query) {
  query = (query || $("#chatInput").value).trim();
  if (!query) return;
  if (!indexed) return toast("Upload tài liệu trước");
  if (!selectedSources.size) return toast("Chọn ít nhất 1 nguồn");

  appendMessage("user", query);
  scrollChat();
  $("#chatInput").value = "";
  $("#btnSend").disabled = true;
  showChatTyping(true);

  let botDiv = null;
  let accumulated = "";
  let sources = [];

  try {
    const res = await fetch(`/api/notebooks/${notebookId}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, sources: [...selectedSources] }),
    });
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: "Lỗi API" }));
      throw new Error(err.detail || "Lỗi API");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (payload.type === "sources") {
          sources = payload.sources || [];
        } else if (payload.type === "token") {
          if (!botDiv) {
            showChatTyping(false);
            botDiv = appendStreamingMessage();
          }
          accumulated += payload.text;
          botDiv.querySelector(".msg-body").innerHTML = formatCites(accumulated);
          scrollChat();
        } else if (payload.type === "replace" || payload.type === "done") {
          accumulated = payload.answer || accumulated;
          if (!botDiv) {
            showChatTyping(false);
            botDiv = appendStreamingMessage();
          }
          botDiv.querySelector(".msg-body").innerHTML = formatCites(accumulated);
          if (payload.type === "done") finalizeStreamingMessage(botDiv, sources);
        }
      }
    }
    scrollChat();
  } catch (err) {
    showChatTyping(false);
    toast(err.message);
  } finally {
    showChatTyping(false);
    $("#btnSend").disabled = false;
  }
}

$("#btnSend")?.addEventListener("click", () => sendChat());
$("#chatInput")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

/* Header */
$("#btnHome")?.addEventListener("click", () => {
  notebookId = null;
  selectedSources.clear();
  location.hash = "";
  showView("home");
  loadNotebooks();
});
$("#nbTitle")?.addEventListener("change", async (e) => {
  await api(`/api/notebooks/${notebookId}`, { method: "PATCH", body: { name: e.target.value } });
});

/* Notes */
function notePreview(content, maxLen = 72) {
  const text = (content || "").trim();
  if (!text) return "";
  if (text.length <= maxLen) return esc(text);
  return `${esc(text.slice(0, maxLen))}…`;
}

async function loadNotes() {
  const notes = await api(`/api/notebooks/${notebookId}/notes`);
  const list = $("#notesList");
  if (!notes.length) {
    list.innerHTML = `<p style="font-size:11px;color:var(--muted);text-align:center;padding:8px 4px;">Chưa có ghi chú nào.</p>`;
    return;
  }
  list.innerHTML = notes
    .map((n) => {
      const preview = notePreview(n.content);
      const previewHtml = preview ? `<span>${preview}</span>` : "";
      return `<div class="note-item"><strong>${esc(n.title)}</strong>${previewHtml}</div>`;
    })
    .join("");
}

function openNoteModal() {
  const modal = $("#noteModal");
  $("#noteTitleInput").value = "";
  $("#noteContentInput").value = "";
  const err = $("#noteModalError");
  err.textContent = "";
  err.classList.add("hidden");
  modal.classList.remove("hidden");
  setTimeout(() => $("#noteTitleInput").focus(), 50);
}

function closeNoteModal() {
  $("#noteModal").classList.add("hidden");
}

async function saveNote() {
  const title = $("#noteTitleInput").value.trim();
  const content = $("#noteContentInput").value.trim();
  const err = $("#noteModalError");

  if (!title || !content) {
    err.textContent = "Vui lòng nhập đầy đủ tiêu đề và nội dung.";
    err.classList.remove("hidden");
    return;
  }

  const saveBtn = $("#noteModalSave");
  saveBtn.disabled = true;
  err.classList.add("hidden");

  try {
    const notes = await api(`/api/notebooks/${notebookId}/notes`, {
      method: "POST",
      body: { title, content },
    });
    const newNote = notes[notes.length - 1];
    if (newNote) selectedSources.add(`[Ghi chú] ${newNote.title}`);
    closeNoteModal();
    toast("Đã thêm ghi chú");
    await refreshNotebook();
    await loadNotes();
    await loadSuggestions();
  } catch (e) {
    err.textContent = e.message || "Không thể lưu ghi chú.";
    err.classList.remove("hidden");
  } finally {
    saveBtn.disabled = false;
  }
}

$("#btnAddNote")?.addEventListener("click", openNoteModal);
$("#noteModalClose")?.addEventListener("click", closeNoteModal);
$("#noteModalCancel")?.addEventListener("click", closeNoteModal);
$("#noteModalBackdrop")?.addEventListener("click", closeNoteModal);
$("#noteModalSave")?.addEventListener("click", saveNote);
$("#noteModal")?.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeNoteModal();
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    saveNote();
  }
});

/* Studio */
const STUDIO_LABELS = {
  summary: "Tóm tắt",
  quiz: "Quiz",
  flashcards: "Flashcards",
  mindmap: "Mind Map",
  report: "Report",
  audio: "Audio Overview",
  video: "Video Overview",
  infographic: "Infographic",
  slides: "Slide Deck",
  datatable: "Data Table",
};

const STUDIO_ICONS = {
  summary: "📝", quiz: "❓", flashcards: "📇", mindmap: "🧠",
  report: "📄", audio: "🎙️", video: "🎬", infographic: "📊",
  slides: "🖥️", datatable: "📋",
};

function _timeAgo(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (diff < 60) return "Vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return `${Math.floor(diff / 86400)} ngày trước`;
}

async function loadStudioSaved() {
  const el = $("#studioSaved");
  if (!el || !notebookId) return;
  try {
    const outputs = await api(`/api/notebooks/${notebookId}/studio`);
    renderStudioSaved(outputs);
  } catch (_) { /* silent */ }
}

function renderStudioSaved(outputs) {
  const el = $("#studioSaved");
  if (!el) return;
  if (!outputs || !outputs.length) { el.classList.add("hidden"); el.innerHTML = ""; return; }
  el.classList.remove("hidden");
  el.innerHTML = outputs.map((o) => `
    <div class="studio-saved-item" data-oid="${escAttr(o.id)}" data-tool="${escAttr(o.tool)}" style="position:relative">
      <span class="ssi-icon">${STUDIO_ICONS[o.tool] || "📄"}</span>
      <div class="ssi-info">
        <div class="ssi-title">${esc(o.label)}</div>
        <div class="ssi-meta">${o.source_count} nguồn · ${_timeAgo(o.created_at)}</div>
      </div>
      <button class="ssi-menu" title="Tùy chọn" aria-label="menu">⋮</button>
    </div>`).join("");

  el.querySelectorAll(".studio-saved-item").forEach((item) => {
    item.addEventListener("click", async (e) => {
      if (e.target.closest(".ssi-menu")) return;
      const oid = item.dataset.oid;
      const tool = item.dataset.tool;
      const label = STUDIO_LABELS[tool] || tool;
      openStudioModal(label, `<div class="studio-loading">⏳ Đang tải...</div>`, tool);
      try {
        const data = await api(`/api/notebooks/${notebookId}/studio/${oid}`);
        openStudioModal(label, renderStudioResult(tool, data.result), tool);
      } catch (_) {
        $("#studioModalBody").innerHTML = `<p class="studio-error">Không tải được kết quả.</p>`;
      }
    });

    item.querySelector(".ssi-menu").addEventListener("click", (e) => {
      e.stopPropagation();
      document.querySelectorAll(".ssi-dropdown").forEach((d) => d.remove());
      const dropdown = document.createElement("div");
      dropdown.className = "ssi-dropdown";
      dropdown.innerHTML = `<button data-action="delete">🗑 Xóa</button>`;
      item.appendChild(dropdown);
      dropdown.querySelector("[data-action=delete]").onclick = async () => {
        dropdown.remove();
        await api(`/api/notebooks/${notebookId}/studio/${item.dataset.oid}`, { method: "DELETE" });
        loadStudioSaved();
      };
      setTimeout(() => document.addEventListener("click", () => dropdown.remove(), { once: true }), 0);
    });
  });
}

function inlineMd(s) {
  let out = esc(String(s ?? ""));
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*(.+?)\*/g, "<em>$1</em>");
  out = out.replace(/\[(\d+)\]/g, '<sup class="cite">$1</sup>');
  return out;
}

function renderMarkdown(md) {
  if (!md) return "<p>(Không có nội dung)</p>";
  const lines = String(md).split("\n");
  let html = "";
  let inList = false;
  for (const raw of lines) {
    const trimmed = raw.trim();
    if (!trimmed) {
      if (inList) { html += "</ul>"; inList = false; }
      continue;
    }
    if (/^-{3,}$/.test(trimmed)) {
      if (inList) { html += "</ul>"; inList = false; }
      html += "<hr/>";
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      if (inList) { html += "</ul>"; inList = false; }
      const level = Math.min(heading[1].length + 2, 6);
      html += `<h${level}>${inlineMd(heading[2])}</h${level}>`;
      continue;
    }
    const listItem = raw.match(/^(\s*)[-*]\s+(.*)$/);
    if (listItem) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inlineMd(listItem[2])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    html += `<p>${inlineMd(trimmed)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}

function renderQuiz(items) {
  if (!items.length) return "<p>Chưa tạo được câu hỏi nào.</p>";
  return `<div class="quiz-list">${items
    .map(
      (q, qi) => `
    <div class="quiz-card" data-qi="${qi}" data-answer="${Number(q.answer_idx) || 0}">
      <p class="quiz-q">${qi + 1}. ${esc(q.question || "")}</p>
      <div class="quiz-opts">
        ${(q.options || [])
          .map((o, oi) => `<button type="button" class="quiz-opt" data-oi="${oi}">${esc(o)}</button>`)
          .join("")}
      </div>
      <p class="quiz-explain hidden">${esc(q.explanation || "")}${
        q.source ? ` <span class="quiz-src">(Nguồn: ${esc(q.source)})</span>` : ""
      }</p>
    </div>`
    )
    .join("")}</div>`;
}

function renderFlashcards(items) {
  if (!items.length) return "<p>Chưa tạo được flashcard nào.</p>";
  return `<div class="flash-grid">${items
    .map(
      (c, i) => `
    <div class="flash-card" data-i="${i}" title="Bấm để lật thẻ">
      <div class="flash-inner">
        <div class="flash-front">${esc(c.front || "")}</div>
        <div class="flash-back">${esc(c.back || "")}${
          c.source ? `<span class="flash-src">Nguồn: ${esc(c.source)}</span>` : ""
        }</div>
      </div>
    </div>`
    )
    .join("")}</div>`;
}

function renderAudio(dialogue) {
  if (!dialogue.length) return "<p>Chưa tạo được kịch bản audio.</p>";
  return `<div class="audio-script">${dialogue
    .map(
      (d) => `
    <div class="audio-line">
      <span class="audio-role">${esc(d.role || "")}</span>
      <p>${esc(d.text || "")}</p>
    </div>`
    )
    .join("")}</div>`;
}

function renderSlides(slides) {
  if (!slides.length) return "<p>Chưa tạo được slide nào.</p>";
  return `<div class="slide-deck">${slides
    .map(
      (s) => `
    <div class="slide-card">
      <h4>${esc(s.title || "")}</h4>
      <ul>${(s.points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
    </div>`
    )
    .join("")}</div>`;
}

function renderDataTable(rows) {
  if (!rows.length) return "<p>Không có dữ liệu.</p>";
  const cols = Object.keys(rows[0]);
  return `<table class="studio-table">
    <thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows
      .map((r) => `<tr>${cols.map((c) => `<td>${esc(String(r[c] ?? ""))}</td>`).join("")}</tr>`)
      .join("")}</tbody>
  </table>`;
}

function renderStudioResult(tool, res) {
  switch (tool) {
    case "summary":
    case "report":
    case "video":
    case "infographic":
      return `<div class="studio-md">${renderMarkdown(res.markdown)}</div>`;
    case "quiz":
      return renderQuiz(res.items || []);
    case "flashcards":
      return renderFlashcards(res.items || []);
    case "mindmap":
      return `<div class="studio-md">${renderMarkdown(res.markdown)}</div><details class="mermaid-src"><summary>Xem sơ đồ Mermaid</summary><pre>${esc(res.mermaid || "")}</pre></details>`;
    case "audio":
      return renderAudio(res.dialogue || []);
    case "slides":
      return renderSlides(res.slides || []);
    case "datatable":
      return renderDataTable(res.rows || []);
    default:
      return `<pre>${esc(JSON.stringify(res, null, 2))}</pre>`;
  }
}

function attachStudioHandlers(tool, root) {
  if (tool === "quiz") {
    $$(".quiz-card", root).forEach((card) => {
      $$(".quiz-opt", card).forEach((opt) => {
        opt.addEventListener("click", () => {
          if (card.classList.contains("answered")) return;
          card.classList.add("answered");
          const correct = Number(card.dataset.answer);
          $$(".quiz-opt", card).forEach((o, idx) => {
            if (idx === correct) o.classList.add("correct");
            else if (o === opt && idx !== correct) o.classList.add("wrong");
          });
          $(".quiz-explain", card)?.classList.remove("hidden");
        });
      });
    });
  }
  if (tool === "flashcards") {
    $$(".flash-card", root).forEach((c) => c.addEventListener("click", () => c.classList.toggle("flipped")));
  }
}

// Cache studio results per tool per source-set so switching tools is instant.
const _studioCache = new Map();
let _studioCacheKey = "";

function _studioKey() {
  return [...selectedSources].sort().join("|");
}

function _invalidateStudioCache() {
  _studioCache.clear();
  _studioCacheKey = _studioKey();
}

function openStudioModal(title, html, tool) {
  $("#studioModalTitle").textContent = title;
  const body = $("#studioModalBody");
  body.innerHTML = html;
  attachStudioHandlers(tool, body);
  $("#studioModal").classList.remove("hidden");
}

function closeStudioModal() {
  $("#studioModal").classList.add("hidden");
  $("#studioModalBody").innerHTML = "";
}

$("#studioModalClose")?.addEventListener("click", closeStudioModal);
$("#studioModalBackdrop")?.addEventListener("click", closeStudioModal);

$("#studioGrid")?.addEventListener("click", async (e) => {
  const btn = e.target.closest(".studio-item");
  if (!btn) return;
  if (!indexed) return toast("Upload tài liệu trước");

  const tool = btn.dataset.tool;
  const label = STUDIO_LABELS[tool] || tool;

  // Invalidate cache when sources changed
  const currentKey = _studioKey();
  if (currentKey !== _studioCacheKey) _invalidateStudioCache();

  if (_studioCache.has(tool)) {
    openStudioModal(label, _studioCache.get(tool).html, tool);
    return;
  }

  // Show modal with loading state
  openStudioModal(label, `<div class="studio-loading">⏳ Đang tạo ${esc(label)}...</div>`, tool);
  $$(".studio-item").forEach((b) => (b.disabled = true));

  try {
    const res = await api(`/api/notebooks/${notebookId}/studio/${tool}`, {
      method: "POST",
      body: { sources: [...selectedSources] },
    });
    const html = renderStudioResult(tool, res);
    _studioCache.set(tool, { html });
    _studioCacheKey = currentKey;
    openStudioModal(label, html, tool);
    loadStudioSaved();
  } catch (err) {
    $("#studioModalBody").innerHTML = `<p class="studio-error">${esc(err.message || "Không thể tạo nội dung Studio.")}</p>`;
  } finally {
    $$(".studio-item").forEach((b) => (b.disabled = false));
  }
});

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  return s.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* Init — restore notebook from URL hash on page load */
if ($("#notebookGrid")) {
  const initId = location.hash.slice(1);
  if (initId) {
    openNotebook(initId).catch(() => {
      location.hash = "";
      loadNotebooks();
    });
  } else {
    loadNotebooks();
  }
}
