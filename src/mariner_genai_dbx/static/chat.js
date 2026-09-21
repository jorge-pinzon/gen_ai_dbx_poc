const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const messages = document.querySelector("#messages");
const sendButton = document.querySelector("#send");
const statusText = document.querySelector("#status");
const newChatButton = document.querySelector("#new-chat");
const readyTopics = document.querySelectorAll(".topic-ready[data-command]");
const appLayout = document.querySelector("#app-layout");
const sourceWorkspace = document.querySelector("#source-workspace");
const citedSources = document.querySelector("#cited-sources");
const sourceCatalogs = document.querySelector("#source-catalogs");
const sourceTreeStatus = document.querySelector("#source-tree-status");
const sourceSearchForm = document.querySelector("#source-search-form");
const sourceSearchInput = document.querySelector("#source-search");
const sourceSearchResults = document.querySelector("#source-search-results");
const sourceSearchList = document.querySelector("#source-search-list");
const sourceSearchStatus = document.querySelector("#source-search-status");
const clearSourceSearchButton = document.querySelector("#clear-source-search");
const documentTitle = document.querySelector("#document-title");
let documentViewer = document.querySelector("#document-viewer");
const documentPlaceholder = document.querySelector("#document-placeholder");
const openSourceTab = document.querySelector("#open-source-tab");
const closeSourceButton = document.querySelector("#close-source");
const initialMessage = "Ask a question about branch operations, employee policies, or benefits.";

let conversationId = null;
let catalogsLoaded = false;
let documentLoadVersion = 0;
const conversationSources = new Map();
const catalogNodes = new Map();

function populateCommand(topic) {
  input.value = `${topic.dataset.command} `;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

for (const topic of readyTopics) {
  topic.addEventListener("click", () => populateCommand(topic));
  topic.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    populateCommand(topic);
  });
}

function sourceKey(source) {
  if (source.catalog) {
    return `${source.catalog.catalogId}:${source.catalog.path}:${source.page || ""}`;
  }
  return source.url || `${source.number}:${source.label}`;
}

function rememberSource(source) {
  const key = sourceKey(source);
  if (conversationSources.has(key)) return;
  conversationSources.set(key, source);

  const item = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "source-list-button";
  button.textContent = source.page
    ? `${source.label} — page ${source.page}`
    : source.label;
  button.addEventListener("click", () => openSource(source));
  item.appendChild(button);
  citedSources.appendChild(item);
}

function addMessage(role, text, sources = []) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.appendChild(paragraph);

  if (sources.length > 0) {
    const heading = document.createElement("h2");
    heading.textContent = "Sources";
    article.appendChild(heading);

    const list = document.createElement("ol");
    for (const source of sources) {
      if (source.url || source.catalog) rememberSource(source);
      const item = document.createElement("li");
      item.value = source.number;
      if (source.url || source.catalog) {
        const link = document.createElement("a");
        link.href = source.url || "#";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.page
          ? `${source.label} — page ${source.page}`
          : source.label;
        link.addEventListener("click", (event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          openSource(source);
        });
        item.appendChild(link);
      } else {
        item.textContent = source.page
          ? `${source.label} — page ${source.page}`
          : source.label;
      }
      list.appendChild(item);
    }
    article.appendChild(list);
  }

  messages.appendChild(article);
  messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
}

function setDocument(source) {
  const loadVersion = ++documentLoadVersion;
  const documentUrl = new URL(source.url, window.location.href);
  if (source.page) documentUrl.hash = `page=${encodeURIComponent(source.page)}`;
  const viewerUrl = documentUrl.href;
  documentTitle.textContent = source.page
    ? `${source.label} — page ${source.page}`
    : source.label;
  openSourceTab.href = viewerUrl;
  openSourceTab.hidden = false;

  const embeddable = source.embeddable !== false && /\.pdf$/i.test(source.label);
  if (embeddable) {
    documentViewer.hidden = true;
    documentPlaceholder.hidden = false;
    documentPlaceholder.textContent = "Loading document…";
    requestAnimationFrame(() => {
      if (loadVersion !== documentLoadVersion) return;
      const replacementViewer = documentViewer.cloneNode(false);
      replacementViewer.removeAttribute("src");
      replacementViewer.src = viewerUrl;
      replacementViewer.hidden = false;
      documentViewer.replaceWith(replacementViewer);
      documentViewer = replacementViewer;
      documentPlaceholder.hidden = true;
    });
  } else {
    documentViewer.hidden = true;
    documentPlaceholder.hidden = false;
    documentViewer.src = "about:blank";
    documentPlaceholder.textContent =
      "This document type cannot be previewed here. Use “Open in new tab” to view it.";
  }
}

async function openSource(source) {
  sourceWorkspace.hidden = false;
  appLayout.classList.add("source-open");
  await loadCatalogs();
  if (source.catalog) {
    const catalogNode = catalogNodes.get(source.catalog.catalogId);
    if (catalogNode) catalogNode.open = true;
  }
  if (source.url) {
    setDocument(source);
  } else if (source.catalog) {
    await openCatalogDocument(
      source.catalog.catalogId,
      source.catalog.path,
      source.page,
    );
  }
}

function closeSourceWorkspace() {
  documentLoadVersion += 1;
  appLayout.classList.remove("source-open");
  sourceWorkspace.hidden = true;
  documentViewer.src = "about:blank";
}

async function loadCatalogs() {
  if (catalogsLoaded) return;
  catalogsLoaded = true;
  sourceTreeStatus.textContent = "Loading folders…";
  try {
    const response = await fetch("/api/v1/sources");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Folders are unavailable.");
    if (data.catalogs.length === 0) {
      sourceTreeStatus.textContent = "No document folders are configured.";
      return;
    }
    sourceTreeStatus.textContent = "";
    for (const catalog of data.catalogs) renderCatalog(catalog);
  } catch (error) {
    catalogsLoaded = false;
    sourceTreeStatus.textContent = error.message || "Folders are unavailable.";
  }
}

sourceSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = sourceSearchInput.value.trim();
  if (query.length < 2) {
    sourceSearchInput.focus();
    return;
  }
  sourceSearchResults.hidden = false;
  sourceSearchList.replaceChildren();
  sourceSearchStatus.textContent = "Searching…";
  try {
    const parameters = new URLSearchParams({ q: query });
    const response = await fetch(`/api/v1/sources/search?${parameters}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Search is unavailable.");
    for (const result of data.results) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "source-list-button source-search-result";
      const name = document.createElement("span");
      name.textContent = result.name;
      const catalog = document.createElement("span");
      catalog.className = "source-result-catalog";
      catalog.textContent = result.catalogLabel;
      button.append(name, catalog);
      button.addEventListener("click", () =>
        openCatalogDocument(result.catalogId, result.path),
      );
      item.appendChild(button);
      sourceSearchList.appendChild(item);
    }
    if (data.results.length === 0) {
      sourceSearchStatus.textContent = `No documents match “${data.query}”.`;
    } else if (data.truncated) {
      sourceSearchStatus.textContent = "Showing the first 50 matches.";
    } else {
      sourceSearchStatus.textContent = `${data.results.length} document${data.results.length === 1 ? "" : "s"} found.`;
    }
  } catch (error) {
    sourceSearchStatus.textContent = error.message || "Search is unavailable.";
  }
});

clearSourceSearchButton.addEventListener("click", () => {
  sourceSearchInput.value = "";
  sourceSearchList.replaceChildren();
  sourceSearchStatus.textContent = "";
  sourceSearchResults.hidden = true;
  sourceSearchInput.focus();
});

function renderCatalog(catalog) {
  const details = document.createElement("details");
  details.className = "source-node source-catalog";
  const summary = document.createElement("summary");
  summary.textContent = catalog.label;
  const children = document.createElement("ul");
  children.className = "source-tree-children";
  details.append(summary, children);
  catalogNodes.set(catalog.id, details);
  details.addEventListener("toggle", () => {
    if (details.open && !details.dataset.loaded) {
      details.dataset.loaded = "true";
      loadChildren(catalog.id, "", children);
    }
  });
  sourceCatalogs.appendChild(details);
}

async function loadChildren(catalogId, path, container, cursor = null) {
  const loading = document.createElement("li");
  loading.className = "source-loading";
  loading.textContent = "Loading…";
  container.appendChild(loading);
  const query = new URLSearchParams({ path });
  if (cursor) query.set("cursor", cursor);
  try {
    const response = await fetch(
      `/api/v1/sources/${encodeURIComponent(catalogId)}/children?${query}`,
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Folder unavailable.");
    loading.remove();
    for (const entry of data.entries) {
      container.appendChild(renderTreeEntry(catalogId, entry));
    }
    if (data.entries.length === 0 && !cursor) {
      const empty = document.createElement("li");
      empty.className = "source-loading";
      empty.textContent = "Empty folder";
      container.appendChild(empty);
    }
    if (data.cursor) {
      const moreItem = document.createElement("li");
      const moreButton = document.createElement("button");
      moreButton.type = "button";
      moreButton.className = "source-tree-button";
      moreButton.textContent = "Load more";
      moreButton.addEventListener("click", () => {
        moreItem.remove();
        loadChildren(catalogId, path, container, data.cursor);
      });
      moreItem.appendChild(moreButton);
      container.appendChild(moreItem);
    }
  } catch (error) {
    loading.textContent = error.message || "Folder unavailable.";
  }
}

function renderTreeEntry(catalogId, entry) {
  const item = document.createElement("li");
  if (entry.type === "folder") {
    const details = document.createElement("details");
    details.className = "source-node";
    const summary = document.createElement("summary");
    summary.textContent = entry.name;
    const children = document.createElement("ul");
    children.className = "source-tree-children";
    details.append(summary, children);
    details.addEventListener("toggle", () => {
      if (details.open && !details.dataset.loaded) {
        details.dataset.loaded = "true";
        loadChildren(catalogId, entry.path, children);
      }
    });
    item.appendChild(details);
    return item;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "source-tree-button source-document-button";
  button.textContent = entry.name;
  button.addEventListener("click", () => openCatalogDocument(catalogId, entry.path));
  item.appendChild(button);
  return item;
}

async function openCatalogDocument(catalogId, path, page = null) {
  documentTitle.textContent = "Loading document…";
  documentViewer.hidden = true;
  documentPlaceholder.hidden = false;
  documentPlaceholder.textContent = "Preparing a secure document link…";
  try {
    const response = await fetch(
      `/api/v1/sources/${encodeURIComponent(catalogId)}/open`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Document unavailable.");
    const source = {
      label: data.label,
      url: data.url,
      embeddable: data.embeddable,
      catalog: { catalogId, path },
      ...(page ? { page } : {}),
    };
    rememberSource(source);
    setDocument(source);
  } catch (error) {
    documentTitle.textContent = "Document unavailable";
    openSourceTab.hidden = true;
    documentPlaceholder.textContent = error.message || "Document unavailable.";
  }
}

closeSourceButton.addEventListener("click", closeSourceWorkspace);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !sourceWorkspace.hidden) closeSourceWorkspace();
});

addMessage("assistant", initialMessage);

function setBusy(isBusy) {
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  statusText.textContent = isBusy ? "Routing your question…" : "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  setBusy(true);

  const payload = { message };
  if (conversationId) payload.conversationId = conversationId;

  try {
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "The request failed.");

    conversationId = data.conversationId;
    addMessage("assistant", data.answer, data.sources || []);
  } catch (error) {
    addMessage("error", error.message || "The request failed.");
  } finally {
    setBusy(false);
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!input.disabled) form.requestSubmit();
});

newChatButton.addEventListener("click", () => {
  conversationId = null;
  conversationSources.clear();
  citedSources.replaceChildren();
  clearSourceSearchButton.click();
  closeSourceWorkspace();
  messages.replaceChildren();
  addMessage("assistant", initialMessage);
  input.focus();
});
