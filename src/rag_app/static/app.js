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
    appendMessage("bot", h.answer, h.sources);
  });
  scrollChat();
}

function appendMessage(role, text, sources) {
  const box = $("#chatMessages");
  $(".chat-welcome", box)?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const body = document.createElement("div");
  body.className = "msg-body md-content";
  body.innerHTML = renderMarkdown(text);
  div.appendChild(body);
  if (role === "bot" && sources?.length) {
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
  box.appendChild(div);
  scrollChat();
  return div;
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
  div.innerHTML = '<div class="msg-body md-content"></div>';
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

function autoGrowInput() {
  const input = $("#chatInput");
  const preview = $("#chatInputPreview");
  if (!input) return;
  input.style.height = "52px";
  const newHeight = Math.min(Math.max(input.scrollHeight, 52), 220);
  input.style.height = newHeight + "px";
  if (preview) preview.style.height = newHeight + "px";
  input.style.overflowY = input.scrollHeight > 220 ? "auto" : "hidden";
}

/** Claude-style live Markdown preview for the composer (keeps char widths for caret sync). */
function updateInputPreview() {
  const input = $("#chatInput");
  const preview = $("#chatInputPreview");
  if (!input || !preview) return;
  autoGrowInput();
  const text = input.value;
  if (!text) {
    preview.innerHTML = "";
    return;
  }

  const lines = text.split("\n");
  const parts = []; // { html, block?: true } — block chunks are full-width code cards
  let inFence = false;
  let fenceLang = "";
  let fenceRows = [];

  const highlightLine = (code, lang) => {
    if (!lang || typeof hljs === "undefined" || !code.trim()) return esc(code);
    try {
      if (hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
    } catch (_) { /* fall through */ }
    return esc(code);
  };

  const styleInline = (s) => {
    let h = esc(s);
    h = h.replace(/`([^`]+)`/g, (_m, code) =>
      `<span class="cip-inline"><span class="cip-hidden">\`</span><span class="cip-inline-code">${code}</span><span class="cip-hidden">\`</span></span>`
    );
    h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");
    return h;
  };

  const flushFence = () => {
    if (!fenceRows.length) return;
    parts.push({
      block: true,
      html: `<div class="cip-code-card">${fenceRows.join("")}</div>`,
    });
    fenceRows = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^(\s*)```([a-zA-Z0-9_+-]*)\s*$/);
    if (fence) {
      const indent = esc(fence[1]);
      const lang = (fence[2] || "").toLowerCase();
      if (!inFence) {
        inFence = true;
        fenceLang = lang;
        fenceRows.push(
          `<div class="cip-block cip-block-head">${indent}` +
            `<span class="cip-tick">\`\`\`</span>` +
            (lang ? `<span class="cip-lang">${esc(lang)}</span>` : "") +
            `</div>`
        );
      } else {
        fenceRows.push(
          `<div class="cip-block cip-block-foot">${indent}` +
            `<span class="cip-tick">${esc(line.slice(fence[1].length))}</span>` +
            `</div>`
        );
        inFence = false;
        fenceLang = "";
        flushFence();
      }
      continue;
    }
    if (inFence) {
      const hl = highlightLine(line, fenceLang);
      fenceRows.push(`<div class="cip-block cip-code-line hljs">${hl || "&nbsp;"}</div>`);
      continue;
    }
    const quote = line.match(/^(\s*)>(.*)$/);
    if (quote) {
      parts.push({
        html:
          `${esc(quote[1])}<span class="cip-quote"><span class="cip-qmark">&gt;</span>${styleInline(quote[2])}</span>`,
      });
      continue;
    }
    // Unordered list: keep "- "/"* " widths, draw a bullet on top (caret-safe)
    const ul = line.match(/^(\s*)([-*])(\s+)(.*)$/);
    if (ul) {
      parts.push({
        html:
          `${esc(ul[1])}<span class="cip-ul-mark">${esc(ul[2])}</span>${esc(ul[3])}` +
          `<span class="cip-li-body">${styleInline(ul[4])}</span>`,
      });
      continue;
    }
    // Ordered list: tint the "1." marker
    const ol = line.match(/^(\s*)(\d+\.)(\s+)(.*)$/);
    if (ol) {
      parts.push({
        html:
          `${esc(ol[1])}<span class="cip-ol-mark">${esc(ol[2])}</span>${esc(ol[3])}` +
          `<span class="cip-li-body">${styleInline(ol[4])}</span>`,
      });
      continue;
    }
    parts.push({ html: styleInline(line) });
  }
  // Unclosed fence still showing
  flushFence();

  // Join: normal lines with <br/>, code cards as block units (no extra br inside)
  let html = "";
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (i > 0) html += "<br/>";
    html += p.html;
  }
  preview.innerHTML = html;
  preview.scrollTop = input.scrollTop;
}

async function sendChat(query) {
  query = (query || $("#chatInput").value).trim();
  if (!query) return;
  if (!indexed) return toast("Upload tài liệu trước");
  if (!selectedSources.size) return toast("Chọn ít nhất 1 nguồn");

  appendMessage("user", query);
  scrollChat();
  $("#chatInput").value = "";
  updateInputPreview();
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
          botDiv.querySelector(".msg-body").innerHTML = renderMarkdown(accumulated);
          scrollChat();
        } else if (payload.type === "replace" || payload.type === "done") {
          accumulated = payload.answer || accumulated;
          if (!botDiv) {
            showChatTyping(false);
            botDiv = appendStreamingMessage();
          }
          botDiv.querySelector(".msg-body").innerHTML = renderMarkdown(accumulated);
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
  if (e.key === "Tab") {
    e.preventDefault();
    const el = e.target;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const val = el.value;
    const indent = "  ";
    el.value = val.substring(0, start) + indent + val.substring(end);
    el.selectionStart = el.selectionEnd = start + indent.length;
    updateInputPreview();
    return;
  }
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendChat();
    return;
  }
  if (e.key === "Enter" && e.shiftKey) {
    const el = e.target;
    const val = el.value;
    const start = el.selectionStart;
    const lineStart = val.lastIndexOf("\n", start - 1) + 1;
    const currentLine = val.substring(lineStart, start);

    const fenceMatch = currentLine.match(/^(\s*)```([a-zA-Z0-9_-]*)\s*$/);
    if (fenceMatch) {
      const lang = fenceMatch[2];
      let isOpening = lang.length > 0;
      if (!isOpening) {
        const textBefore = val.substring(0, lineStart);
        const previousFences = (textBefore.match(/```/g) || []).length;
        if (previousFences % 2 === 0) {
          isOpening = true;
        }
      }
      if (isOpening) {
        e.preventDefault();
        const indent = fenceMatch[1];
        const insertion = "\n" + indent + "\n" + indent + "```";
        el.value = val.substring(0, start) + insertion + val.substring(el.selectionEnd);
        el.selectionStart = el.selectionEnd = start + 1 + indent.length;
        updateInputPreview();
        return;
      }
    }

    const bulletMatch = currentLine.match(/^(\s*)[-*]\s+(.*)$/);
    if (bulletMatch) {
      e.preventDefault();
      if (!bulletMatch[2].trim()) {
        el.value = val.substring(0, lineStart) + val.substring(start);
        el.selectionStart = el.selectionEnd = lineStart;
      } else {
        const insertion = "\n" + bulletMatch[1] + "- ";
        el.value = val.substring(0, start) + insertion + val.substring(el.selectionEnd);
        el.selectionStart = el.selectionEnd = start + insertion.length;
      }
      updateInputPreview();
      return;
    }

    const numberMatch = currentLine.match(/^(\s*)(\d+)\.\s+(.*)$/);
    if (numberMatch) {
      e.preventDefault();
      if (!numberMatch[3].trim()) {
        el.value = val.substring(0, lineStart) + val.substring(start);
        el.selectionStart = el.selectionEnd = lineStart;
      } else {
        const nextNum = parseInt(numberMatch[2], 10) + 1;
        const insertion = "\n" + numberMatch[1] + nextNum + ". ";
        el.value = val.substring(0, start) + insertion + val.substring(el.selectionEnd);
        el.selectionStart = el.selectionEnd = start + insertion.length;
      }
      updateInputPreview();
      return;
    }
  }
});
$("#chatInput")?.addEventListener("input", updateInputPreview);
$("#chatInput")?.addEventListener("scroll", () => {
  const preview = $("#chatInputPreview");
  if (preview) preview.scrollTop = $("#chatInput").scrollTop;
});
$("#chatInput")?.addEventListener("focus", updateInputPreview);

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
let editingNoteId = null;

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
      return `<div class="note-item" data-id="${esc(n.id)}">
        <div class="note-item-hd">
          <strong>${esc(n.title)}</strong>
          <div class="note-actions">
            <button type="button" class="btn-note-action btn-note-to-source" data-id="${esc(n.id)}" title="Chuyển thành Nguồn tài liệu">📥</button>
            <button type="button" class="btn-note-action btn-note-del" data-id="${esc(n.id)}" title="Xóa ghi chú">🗑️</button>
          </div>
        </div>
        ${previewHtml}
      </div>`;
    })
    .join("");

  list.querySelectorAll(".note-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.closest(".btn-note-to-source")) {
        e.stopPropagation();
        convertNoteToSource(el.dataset.id);
        return;
      }
      if (e.target.closest(".btn-note-del")) {
        e.stopPropagation();
        removeNote(el.dataset.id);
        return;
      }
      const note = notes.find((n) => n.id === el.dataset.id);
      if (note) openNoteModal(note);
    });
  });
}

function openNoteModal(note = null) {
  const modal = $("#noteModal");
  const delBtn = $("#noteModalDelete");
  const toSourceBtn = $("#noteModalToSource");
  const saveBtn = $("#noteModalSave");

  if (note && note.id) {
    editingNoteId = note.id;
    $("#noteModalTitle").textContent = "Xem / Sửa Ghi chú";
    $("#noteTitleInput").value = note.title || "";
    $("#noteContentInput").value = note.content || "";
    saveBtn.textContent = "Cập nhật";
    delBtn?.classList.remove("hidden");
    toSourceBtn?.classList.remove("hidden");
  } else {
    editingNoteId = null;
    $("#noteModalTitle").textContent = "Thêm ghi chú";
    $("#noteTitleInput").value = "";
    $("#noteContentInput").value = "";
    saveBtn.textContent = "Lưu ghi chú";
    delBtn?.classList.add("hidden");
    toSourceBtn?.classList.add("hidden");
  }

  const err = $("#noteModalError");
  err.textContent = "";
  err.classList.add("hidden");
  modal.classList.remove("hidden");
  setTimeout(() => $("#noteTitleInput").focus(), 50);
}

function closeNoteModal() {
  $("#noteModal").classList.add("hidden");
}

async function removeNote(id) {
  if (!confirm("Bạn có chắc muốn xóa ghi chú này?")) return;
  try {
    await api(`/api/notebooks/${notebookId}/notes/${id}`, { method: "DELETE" });
    toast("Đã xóa ghi chú");
    closeNoteModal();
    await loadNotes();
    await refreshNotebook();
  } catch (e) {
    toast(e.message || "Lỗi khi xóa ghi chú");
  }
}

async function convertNoteToSource(id) {
  try {
    toast("Đang chuyển ghi chú thành file nguồn...");
    await api(`/api/notebooks/${notebookId}/notes/${id}/to_source`, { method: "POST" });
    toast("Đã thêm ghi chú vào Sources!");
    closeNoteModal();
    await refreshNotebook();
  } catch (e) {
    toast(e.message || "Lỗi khi chuyển thành nguồn");
  }
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
    if (editingNoteId) {
      await api(`/api/notebooks/${notebookId}/notes/${editingNoteId}`, {
        method: "PUT",
        body: { title, content },
      });
      toast("Đã cập nhật ghi chú");
    } else {
      const notes = await api(`/api/notebooks/${notebookId}/notes`, {
        method: "POST",
        body: { title, content },
      });
      const newNote = notes[notes.length - 1];
      if (newNote) selectedSources.add(`[Ghi chú] ${newNote.title}`);
      toast("Đã thêm ghi chú");
    }
    closeNoteModal();
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

$("#btnAddNote")?.addEventListener("click", () => openNoteModal(null));
$("#noteModalClose")?.addEventListener("click", closeNoteModal);
$("#noteModalCancel")?.addEventListener("click", closeNoteModal);
$("#noteModalDelete")?.addEventListener("click", () => editingNoteId && removeNote(editingNoteId));
$("#noteModalToSource")?.addEventListener("click", () => editingNoteId && convertNoteToSource(editingNoteId));
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

function formatCodeBlocks(html) {
  if (!html) return html;
  return html.replace(/<pre><code(?:\s+class="([^"]*)")?>([\s\S]*?)<\/code><\/pre>/g, (match, classAttr, codeContent) => {
    const langMatch = (classAttr || "").match(/language-([a-zA-Z0-9_+-]+)/);
    const l = (langMatch ? langMatch[1] : "text").toLowerCase();
    let highlighted = codeContent;
    if (typeof hljs !== "undefined" && langMatch) {
      try {
        const rawCode = codeContent
          .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&")
          .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#x27;/g, "'");
        if (hljs.getLanguage(l)) {
          highlighted = hljs.highlight(rawCode, { language: l }).value;
        }
      } catch (_) { /* keep plain escaped html from marked */ }
    }
    return `<div class="code-block-wrapper">` +
      `<div class="code-header"><span class="code-lang">${esc(l)}</span><button type="button" class="btn-copy-code" onclick="navigator.clipboard.writeText(this.closest('.code-block-wrapper').querySelector('code').innerText); toast('Đã sao chép');">Copy</button></div>` +
      `<pre><code class="hljs language-${esc(l)}">${highlighted}</code></pre>` +
      `</div>`;
  });
}

function inlineMd(s) {
  let out = esc(String(s ?? ""));
  out = out.replace(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (match, lang, codeContent) => {
    const l = (lang || "code").toLowerCase();
    return `<div class="code-block-wrapper"><div class="code-header"><span class="code-lang">${esc(l)}</span><button class="btn-copy-code" onclick="navigator.clipboard.writeText(this.closest('.code-block-wrapper').querySelector('code').innerText); toast('Đã sao chép');">📋 Copy</button></div><pre><code class="language-${esc(l)}">${esc(codeContent.trimEnd())}</code></pre></div>`;
  });
  out = out.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*(.+?)\*/g, "<em>$1</em>");
  out = out.replace(/\[(\d+)\]/g, '<sup class="cite" title="Nguồn $1">$1</sup>');
  return out;
}

function renderMarkdown(md) {
  if (!md) return "<p>(Không có nội dung)</p>";
  // Strip server-side cite HTML if history accidentally stored/returned HTML
  const raw = String(md).replace(/<sup class="cite"[^>]*>\d+<\/sup>/g, (m) => {
    const n = m.match(/\d+/);
    return n ? `[${n[0]}]` : m;
  });
  if (typeof marked !== "undefined" && typeof marked.parse === "function") {
    try {
      if (typeof marked.setOptions === "function") {
        marked.setOptions({ breaks: true, gfm: true });
      }
      let html = marked.parse(raw, { breaks: true, gfm: true });
      html = formatCodeBlocks(html);
      html = formatCites(html);
      return html;
    } catch (_) { /* fallback to custom renderer */ }
  }
  const lines = raw.split("\n");
  let html = "";
  let inList = false;
  let inCode = false;
  let codeBuffer = "";
  let codeLang = "";
  for (const rawLine of lines) {
    if (rawLine.trim().startsWith("```")) {
      if (!inCode) {
        inCode = true;
        codeLang = rawLine.trim().slice(3).trim() || "code";
        codeBuffer = "";
      } else {
        inCode = false;
        html += `<pre><code class="language-${esc(codeLang)}">${esc(codeBuffer.trimEnd())}</code></pre>`;
      }
      continue;
    }
    if (inCode) {
      codeBuffer += rawLine + "\n";
      continue;
    }
    const trimmed = rawLine.trim();
    if (!trimmed) {
      if (inList) { html += `</${inList}>`; inList = false; }
      continue;
    }
    if (/^-{3,}$/.test(trimmed)) {
      if (inList) { html += `</${inList}>`; inList = false; }
      html += "<hr/>";
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      if (inList) { html += `</${inList}>`; inList = false; }
      const level = Math.min(heading[1].length + 1, 6);
      html += `<h${level}>${inlineMd(heading[2])}</h${level}>`;
      continue;
    }
    const listItem = rawLine.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (listItem) {
      const isNum = /\d+\./.test(listItem[2]);
      const tag = isNum ? "ol" : "ul";
      if (inList && inList !== tag) { html += `</${inList}>`; inList = false; }
      if (!inList) { html += `<${tag}>`; inList = tag; }
      html += `<li>${inlineMd(listItem[3])}</li>`;
      continue;
    }
    if (inList) { html += `</${inList}>`; inList = false; }
    const blockquote = rawLine.match(/^>\s?(.*)$/);
    if (blockquote) {
      html += `<blockquote><p>${inlineMd(blockquote[1])}</p></blockquote>`;
      continue;
    }
    html += `<p>${inlineMd(trimmed)}</p>`;
  }
  if (inList) html += `</${inList}>`;
  if (inCode) {
    html += `<pre><code class="language-${esc(codeLang)}">${esc(codeBuffer.trimEnd())}</code></pre>`;
  }
  return formatCodeBlocks(html);
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
      return `<div class="studio-md md-content">${renderMarkdown(res.markdown)}</div>`;
    case "quiz":
      return renderQuiz(res.items || []);
    case "flashcards":
      return renderFlashcards(res.items || []);
    case "mindmap":
      return `<div class="studio-md md-content">${renderMarkdown(res.markdown)}</div><details class="mermaid-src"><summary>Xem sơ đồ Mermaid</summary><pre>${esc(res.mermaid || "")}</pre></details>`;
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
