// Keeping the UI on the FastAPI origin avoids a separate CORS configuration.
const API_BASE_URL = window.location.origin;
const PAGE_SIZE = 8;

const CATEGORIES = [
  "Artificial Intelligence",
  "Agentic AI",
  "Quantum Computing",
  "Cloud Computing",
  "Software Architecture",
  "Cybersecurity",
  "Programming and Developer Tools",
  "Startups and Tech Business",
  "Global Tech Companies and Trends",
];

const state = {
  category: "",
  keyword: "",
  news: [],
  total: 0,
  skip: 0,
  newsLoading: false,
  briefingLoading: false,
  newsRequestId: 0,
  newsAbortController: null,
  articleRequestId: 0,
  articleLoadingId: "",
};

const elements = {
  articleCount: document.querySelector("#article-count"),
  categoryFilters: document.querySelector("#category-filters"),
  connectionButton: document.querySelector("#connection-status"),
  connectionLabel: document.querySelector("#connection-label"),
  dialog: document.querySelector("#article-dialog"),
  dialogClose: document.querySelector("#dialog-close"),
  dialogContent: document.querySelector("#dialog-content"),
  feedContext: document.querySelector("#feed-context"),
  feedHeading: document.querySelector("#feed-heading"),
  briefingContent: document.querySelector("#briefing-content"),
  briefingDateBadge: document.querySelector("#briefing-date-badge"),
  briefingMessage: document.querySelector("#briefing-message"),
  heroBriefingDate: document.querySelector("#hero-briefing-date"),
  heroBriefingSummary: document.querySelector("#hero-briefing-summary"),
  heroBriefingTitle: document.querySelector("#hero-briefing-title"),
  latestBriefingDate: document.querySelector("#latest-briefing-date"),
  loadMore: document.querySelector("#load-more"),
  loadMoreWrap: document.querySelector("#load-more-wrap"),
  menuToggle: document.querySelector("#menu-toggle"),
  newsGrid: document.querySelector("#news-grid"),
  newsMessage: document.querySelector("#news-message"),
  overviewStatusLabel: document.querySelector("#overview-status-label"),
  resultCount: document.querySelector("#result-count"),
  searchForm: document.querySelector("#search-form"),
  searchInput: document.querySelector("#search-input"),
  navigation: document.querySelector("#primary-navigation"),
  overviewConnection: document.querySelector("#overview-connection"),
  announcer: document.querySelector("#announcer"),
};

function makeElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined && text !== null) {
    element.textContent = String(text);
  }
  return element;
}

function safeText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function safeArticleUrl(value) {
  if (typeof value !== "string") {
    return "";
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.href
      : "";
  } catch {
    return "";
  }
}

function formatDate(value, includeTime = false) {
  if (typeof value !== "string" || !value.trim()) {
    return "Date not available";
  }

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  const parsed = dateOnly
    ? new Date(
        Number(dateOnly[1]),
        Number(dateOnly[2]) - 1,
        Number(dateOnly[3]),
      )
    : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Date not available";
  }

  const options = {
    day: "numeric",
    month: "short",
    year: "numeric",
  };
  if (includeTime) {
    options.hour = "numeric";
    options.minute = "2-digit";
  }
  return new Intl.DateTimeFormat(undefined, options).format(parsed);
}

async function fetchJson(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
      ...options,
    });
  } catch (error) {
    console.error("TechPulse could not reach the API:", error);
    throw new Error("The server could not be reached. Check that the backend is running.");
  }

  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    console.error("TechPulse received a response that was not valid JSON:", error);
    throw new Error("The server returned an unexpected response. Please try again.");
  }

  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}.`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setConnectionStatus(status) {
  const connected = status === "connected";
  const disconnected = status === "disconnected";

  elements.connectionButton.classList.toggle("is-connected", connected);
  elements.connectionButton.classList.toggle("is-disconnected", disconnected);
  elements.connectionButton.classList.toggle("is-checking", !connected && !disconnected);
  elements.connectionButton.setAttribute(
    "aria-label",
    connected
      ? "Backend connected. Check connection again."
      : disconnected
        ? "Backend disconnected. Check connection again."
        : "Checking backend connection.",
  );

  const label = connected ? "Connected" : disconnected ? "Disconnected" : "Checking connection";
  elements.connectionLabel.textContent = label;
  elements.overviewStatusLabel.textContent = connected
    ? "Connected"
    : disconnected
      ? "Disconnected"
      : "Checking…";
}

async function checkConnection() {
  setConnectionStatus("checking");
  try {
    const health = await fetchJson("/health");
    if (health.status === "ok" && health.database === "connected") {
      setConnectionStatus("connected");
      return true;
    }
    throw new Error("Health response did not confirm database connectivity.");
  } catch (error) {
    console.error("TechPulse health check failed:", error);
    setConnectionStatus("disconnected");
    return false;
  }
}

function renderCategoryFilters() {
  for (const category of CATEGORIES) {
    const button = makeElement("button", "category-chip", category);
    button.type = "button";
    button.dataset.category = category;
    button.setAttribute("aria-pressed", "false");
    elements.categoryFilters.append(button);
  }
  updateCategorySelection();
}

function updateCategorySelection() {
  for (const button of elements.categoryFilters.querySelectorAll("[data-category]")) {
    const active = button.dataset.category === state.category;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function makeMessage(title, detail, retryLabel, retryAction) {
  const wrapper = makeElement("div", "message-content");
  wrapper.append(makeElement("p", "message-title", title));
  if (detail) {
    wrapper.append(makeElement("p", "message-detail", detail));
  }
  if (retryAction) {
    const retry = makeElement("button", "message-retry", retryLabel || "Try again");
    retry.type = "button";
    retry.addEventListener("click", retryAction);
    wrapper.append(retry);
  }
  return wrapper;
}

function showNewsLoading(append) {
  elements.newsGrid.setAttribute("aria-busy", "true");
  elements.newsMessage.hidden = true;
  if (!append) {
    elements.newsGrid.replaceChildren();
    elements.newsMessage.hidden = false;
    elements.newsMessage.replaceChildren();
    const spinner = makeElement("span", "loading-spinner");
    spinner.setAttribute("aria-hidden", "true");
    elements.newsMessage.append(spinner, makeElement("span", "", "Finding the latest stories…"));
  }
}

function showNewsError(message, append) {
  elements.newsGrid.setAttribute("aria-busy", "false");
  elements.newsMessage.hidden = false;
  elements.newsMessage.replaceChildren(
    makeMessage(
      "We couldn't load these stories.",
      message,
      "Retry",
      () => loadNews(append),
    ),
  );
}

function updateFeedLabels() {
  if (state.keyword) {
    elements.feedHeading.textContent = "Search results";
    elements.feedContext.textContent = `Stories matching “${state.keyword}”.`;
  } else if (state.category) {
    elements.feedHeading.textContent = state.category;
    elements.feedContext.textContent = "Stories saved with this technology category.";
  } else {
    elements.feedHeading.textContent = "Latest stories";
    elements.feedContext.textContent =
      "Fresh perspectives from the technology world.";
  }
}

function articleCard(article) {
  const card = makeElement("article", "news-card");
  const top = makeElement("div", "news-card-topline");
  const category = safeText(article.category);
  top.append(makeElement("span", "category-label", category || "Uncategorized"));

  if (Number.isFinite(article.importance_score)) {
    top.append(
      makeElement(
        "span",
        "importance-score",
        `Importance ${article.importance_score}/100`,
      ),
    );
  }
  card.append(top);

  const title = safeText(article.title) || "Title not available";
  const details = makeElement("button", "news-headline-button", title);
  details.type = "button";
  details.addEventListener("click", () => openArticleDetails(article._id));
  card.append(details);

  const description = safeText(article.description);
  if (description) {
    card.append(makeElement("p", "news-summary", description));
  }

  const metadata = makeElement("div", "news-card-meta");
  const source = safeText(article.source);
  const published = safeText(article.published_at);
  if (source) {
    metadata.append(makeElement("span", "", source));
  }
  if (published) {
    metadata.append(makeElement("span", "", formatDate(published)));
  }
  if (metadata.childElementCount) {
    card.append(metadata);
  }

  const actions = makeElement("div", "news-card-actions");
  const url = safeArticleUrl(article.url);
  if (url) {
    const readLink = makeElement("a", "card-link", "Read Article");
    readLink.href = url;
    readLink.target = "_blank";
    readLink.rel = "noopener noreferrer";
    readLink.append(externalLinkIcon());
    actions.append(readLink);
  } else {
    actions.append(makeElement("span", "importance-score", "Source link unavailable"));
  }

  const detailsButton = makeElement("button", "details-button", "Details");
  detailsButton.type = "button";
  detailsButton.addEventListener("click", () => openArticleDetails(article._id));
  actions.append(detailsButton);
  card.append(actions);
  return card;
}

function externalLinkIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 20 20");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M7 5H5.5A1.5 1.5 0 0 0 4 6.5v8A1.5 1.5 0 0 0 5.5 16h8a1.5 1.5 0 0 0 1.5-1.5V13M10 4h6v6m0-6-7 7");
  icon.append(path);
  return icon;
}

function updateLoadMoreVisibility() {
  const hasMore = state.news.length < state.total;
  elements.loadMoreWrap.hidden = !hasMore;
}

async function loadNews(append = false) {
  if (state.newsLoading && append) {
    return;
  }
  if (state.newsAbortController) {
    state.newsAbortController.abort();
  }
  state.newsLoading = true;
  state.newsAbortController = new AbortController();
  const requestId = ++state.newsRequestId;
  const requestSkip = append ? state.skip : 0;
  updateFeedLabels();
  showNewsLoading(append);
  elements.resultCount.textContent = "";
  elements.loadMore.disabled = true;

  const params = new URLSearchParams({
    skip: String(requestSkip),
    limit: String(PAGE_SIZE),
  });
  let path = `/news?${params}`;
  if (state.keyword) {
    params.set("keyword", state.keyword);
    path = `/news/search?${params}`;
  } else if (state.category) {
    path = `/news/category/${encodeURIComponent(state.category)}?${params}`;
  }

  try {
    const result = await fetchJson(path, { signal: state.newsAbortController.signal });
    if (requestId !== state.newsRequestId) {
      return;
    }
    if (!result || !Array.isArray(result.items) || !Number.isFinite(result.total)) {
      throw new Error("The news response is missing the expected list information.");
    }

    state.news = append ? state.news.concat(result.items) : result.items;
    state.total = result.total;
    state.skip = state.news.length;
    elements.newsGrid.replaceChildren(...state.news.map(articleCard));
    elements.newsGrid.setAttribute("aria-busy", "false");
    elements.newsMessage.hidden = true;
    elements.resultCount.textContent =
      `${state.news.length} of ${state.total} ${state.total === 1 ? "story" : "stories"}`;
    elements.articleCount.textContent = result.total.toLocaleString();
    elements.loadMore.disabled = false;
    updateLoadMoreVisibility();

    if (!state.news.length) {
      elements.newsMessage.hidden = false;
      elements.newsMessage.replaceChildren(
        makeMessage(
          "No stories found",
          state.keyword || state.category
            ? "Try another keyword or choose a different topic."
            : "There are no saved news articles yet. Check back after the scheduled news run.",
        ),
      );
    }
  } catch (error) {
    if (requestId !== state.newsRequestId) {
      return;
    }
    console.error("TechPulse could not load news:", error);
    showNewsError(error.message, append);
    elements.loadMore.disabled = false;
  } finally {
    if (requestId === state.newsRequestId) {
      state.newsLoading = false;
      state.newsAbortController = null;
    }
  }
}

async function loadOverview() {
  try {
    const result = await fetchJson("/news?skip=0&limit=1");
    if (result && Number.isFinite(result.total)) {
      elements.articleCount.textContent = result.total.toLocaleString();
    }
  } catch (error) {
    console.error("TechPulse could not load the article count:", error);
    elements.articleCount.textContent = "Not available";
  }
}

function suggestionCard(title, value) {
  if (!value || typeof value !== "object" || !safeText(value.text)) {
    return null;
  }
  const card = makeElement("section", "suggestion-card");
  card.append(makeElement("h4", "", title));
  card.append(makeElement("p", "", value.text));
  if (value.type === "generated_suggestion") {
    card.append(makeElement("span", "suggestion-note", "Generated suggestion · not a reported fact"));
  }
  return card;
}

function makeBriefingStory(story) {
  if (!story || typeof story !== "object") {
    return null;
  }
  const section = makeElement("section", "briefing-story");
  const title = safeText(story.title);
  if (title) {
    section.append(makeElement("h4", "", title));
  }
  const summary = safeText(story.summary);
  if (summary) {
    const summaryParagraph = makeElement("p", "briefing-story-summary");
    summaryParagraph.append(makeElement("strong", "", "What happened: "));
    summaryParagraph.append(document.createTextNode(summary));
    section.append(summaryParagraph);
  }
  const why = safeText(story.why_it_matters);
  if (why) {
    const whyParagraph = makeElement("p", "briefing-story-why");
    whyParagraph.append(makeElement("strong", "", "Why it matters: "));
    whyParagraph.append(document.createTextNode(why));
    section.append(whyParagraph);
  }
  const sourceUrl = safeArticleUrl(story.url);
  if (sourceUrl) {
    const sourceLink = makeElement("a", "briefing-story-source", "Read original article");
    sourceLink.href = sourceUrl;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    section.append(sourceLink);
  }
  return section.childElementCount ? section : null;
}

function renderBriefing(briefing) {
  elements.briefingContent.replaceChildren();
  const dateValue = safeText(briefing.briefing_date);
  const readableDate = dateValue ? formatDate(dateValue) : "Date not available";
  elements.briefingDateBadge.textContent = readableDate;

  const header = makeElement("header", "briefing-paper-header");
  header.append(makeElement("p", "eyebrow", "DAILY TECHNOLOGY EDITION"));
  header.append(makeElement("h3", "", `Briefing for ${readableDate}`));
  elements.briefingContent.append(header);

  const categories = briefing.news && typeof briefing.news === "object"
    ? Object.entries(briefing.news)
    : [];
  if (categories.length) {
    const groups = makeElement("div", "briefing-groups");
    groups.append(
      makeElement(
        "h4",
        "briefing-developments-heading",
        "Today's important technology developments",
      ),
    );
    for (const [category, stories] of categories) {
      if (!Array.isArray(stories) || !stories.length) {
        continue;
      }
      const group = makeElement("section", "briefing-category");
      group.append(makeElement("h4", "briefing-category-heading", category));
      const storyList = makeElement("div", "briefing-story-list");
      for (const story of stories) {
        const storyElement = makeBriefingStory(story);
        if (storyElement) {
          storyList.append(storyElement);
        }
      }
      if (storyList.childElementCount) {
        group.append(storyList);
        groups.append(group);
      }
    }
    if (groups.childElementCount) {
      elements.briefingContent.append(groups);
    }
  }

  const suggestions = makeElement("div", "briefing-suggestions");
  const learning = suggestionCard("Learning of the Day", briefing.learning_of_the_day);
  const career = suggestionCard("Career Opportunity", briefing.career_opportunity);
  if (learning) {
    suggestions.append(learning);
  }
  if (career) {
    suggestions.append(career);
  }
  if (suggestions.childElementCount) {
    elements.briefingContent.append(suggestions);
  }

  const createdAt = safeText(briefing.created_at);
  if (createdAt) {
    elements.briefingContent.append(
      makeElement("p", "briefing-created", `Saved ${formatDate(createdAt, true)}`),
    );
  }

  elements.briefingMessage.hidden = true;
  elements.briefingContent.hidden = false;

  const firstStory = categories
    .flatMap(([, stories]) => Array.isArray(stories) ? stories : [])
    .find((story) => safeText(story.summary));
  elements.heroBriefingDate.textContent = readableDate;
  if (firstStory) {
    elements.heroBriefingTitle.textContent =
      safeText(firstStory.title) || "A clearer view of today's technology";
    elements.heroBriefingSummary.textContent = safeText(firstStory.summary);
  } else {
    elements.heroBriefingTitle.textContent = "A little more context. A lot less noise.";
    elements.heroBriefingSummary.textContent =
      "This saved edition does not include a story summary.";
  }
}

async function loadBriefing() {
  if (state.briefingLoading) {
    return;
  }
  state.briefingLoading = true;
  elements.briefingContent.hidden = true;
  elements.briefingMessage.hidden = false;
  elements.briefingMessage.replaceChildren();
  const spinner = makeElement("span", "loading-spinner");
  spinner.setAttribute("aria-hidden", "true");
  elements.briefingMessage.append(spinner, makeElement("span", "", "Looking for the latest daily briefing…"));

  try {
    const list = await fetchJson("/briefings?skip=0&limit=1");
    if (!list || !Array.isArray(list.items)) {
      throw new Error("The briefing response is missing the expected list.");
    }
    const latest = list.items[0];
    if (!latest || !safeText(latest.briefing_date)) {
      elements.briefingMessage.replaceChildren(
        makeMessage(
          "No daily briefing yet",
          "A briefing appears here after the scheduled news workflow has generated and saved one.",
          "Check again",
          loadBriefing,
        ),
      );
      elements.latestBriefingDate.textContent = "Not available";
      elements.briefingDateBadge.textContent = "No edition yet";
      elements.heroBriefingDate.textContent = "No saved edition yet";
      elements.heroBriefingTitle.textContent = "Your briefing will be ready after the daily run.";
      elements.heroBriefingSummary.textContent =
        "The scheduler does not run immediately when the API starts.";
      return;
    }

    const briefing = await fetchJson(
      `/briefings/${encodeURIComponent(latest.briefing_date)}`,
    );
    if (!briefing || typeof briefing !== "object") {
      throw new Error("The briefing details could not be read.");
    }
    elements.latestBriefingDate.textContent = formatDate(briefing.briefing_date);
    renderBriefing(briefing);
  } catch (error) {
    console.error("TechPulse could not load the daily briefing:", error);
    elements.briefingMessage.replaceChildren(
      makeMessage(
        "The briefing is temporarily unavailable",
        "Check the backend connection, then try loading the briefing again.",
        "Retry briefing",
        loadBriefing,
      ),
    );
    elements.latestBriefingDate.textContent = "Not available";
    elements.briefingDateBadge.textContent = "Unavailable";
    elements.heroBriefingDate.textContent = "Briefing unavailable";
    elements.heroBriefingTitle.textContent = "We couldn't load the latest edition.";
    elements.heroBriefingSummary.textContent = "Use the retry button to check again.";
  } finally {
    state.briefingLoading = false;
  }
}

function renderArticleDetails(article) {
  elements.dialogContent.replaceChildren();
  const category = safeText(article.category);
  if (category) {
    elements.dialogContent.append(makeElement("span", "category-label", category));
  }
  elements.dialogContent.append(
    makeElement("h2", "", safeText(article.title) || "Article details"),
  );

  const metadata = makeElement("div", "dialog-meta");
  if (safeText(article.source)) {
    metadata.append(makeElement("span", "", safeText(article.source)));
  }
  if (safeText(article.published_at)) {
    metadata.append(makeElement("span", "", formatDate(article.published_at, true)));
  }
  if (metadata.childElementCount) {
    elements.dialogContent.append(metadata);
  }

  for (const [label, value] of [
    ["Summary", article.description],
    ["Importance score", Number.isFinite(article.importance_score)
      ? `${article.importance_score} out of 100`
      : ""],
    ["Saved in TechPulse", safeText(article.fetched_at)
      ? formatDate(article.fetched_at, true)
      : ""],
  ]) {
    if (safeText(value)) {
      const field = makeElement("div", "dialog-field");
      field.append(makeElement("strong", "", label));
      field.append(makeElement("p", "", safeText(value)));
      elements.dialogContent.append(field);
    }
  }

  const url = safeArticleUrl(article.url);
  if (url) {
    const link = makeElement("a", "dialog-source-link", "Read at the original publisher");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    elements.dialogContent.append(link);
  }
}

async function openArticleDetails(articleId) {
  if (typeof articleId !== "string" || !articleId.trim()) {
    elements.dialogContent.replaceChildren(
      makeElement("p", "", "This article does not have an available details link."),
    );
    if (!elements.dialog.open) {
      elements.dialog.showModal();
    }
    return;
  }

  if (state.articleLoadingId === articleId) {
    return;
  }
  state.articleLoadingId = articleId;
  const requestId = ++state.articleRequestId;
  elements.dialogContent.replaceChildren();
  const spinner = makeElement("span", "loading-spinner");
  spinner.setAttribute("aria-hidden", "true");
  elements.dialogContent.append(spinner, makeElement("p", "", "Loading article details…"));
  if (!elements.dialog.open) {
    elements.dialog.showModal();
  }

  try {
    const article = await fetchJson(`/news/${encodeURIComponent(articleId)}`);
    if (requestId === state.articleRequestId && elements.dialog.open) {
      renderArticleDetails(article);
    }
  } catch (error) {
    console.error("TechPulse could not load article details:", error);
    if (requestId === state.articleRequestId && elements.dialog.open) {
      elements.dialogContent.replaceChildren(
        makeMessage(
          "Article details are unavailable",
          "The article may no longer be available. You can still use its source link from the news card.",
        ),
      );
    }
  } finally {
    if (requestId === state.articleRequestId) {
      state.articleLoadingId = "";
    }
  }
}

function announce(message) {
  elements.announcer.textContent = "";
  window.requestAnimationFrame(() => {
    elements.announcer.textContent = message;
  });
}

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const keyword = elements.searchInput.value.trim();
  if (!keyword) {
    elements.searchInput.focus();
    announce("Enter a keyword to search the news.");
    return;
  }
  state.keyword = keyword;
  state.category = "";
  updateCategorySelection();
  state.skip = 0;
  loadNews();
});

elements.searchInput.addEventListener("search", () => {
  if (!elements.searchInput.value.trim() && state.keyword) {
    state.keyword = "";
    state.skip = 0;
    loadNews();
  }
});

elements.searchInput.addEventListener("input", () => {
  if (!elements.searchInput.value.trim() && state.keyword) {
    state.keyword = "";
    state.skip = 0;
    loadNews();
  }
});

elements.categoryFilters.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-category]");
  if (!button) {
    return;
  }
  state.category = button.dataset.category || "";
  state.keyword = "";
  elements.searchInput.value = "";
  state.skip = 0;
  updateCategorySelection();
  loadNews();
});

elements.loadMore.addEventListener("click", () => loadNews(true));
elements.connectionButton.addEventListener("click", checkConnection);
elements.overviewConnection.addEventListener("click", checkConnection);

elements.menuToggle.addEventListener("click", () => {
  const isOpen = elements.navigation.classList.toggle("is-open");
  elements.menuToggle.setAttribute("aria-expanded", String(isOpen));
  elements.menuToggle.setAttribute(
    "aria-label",
    isOpen ? "Close navigation" : "Open navigation",
  );
});

elements.navigation.addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    elements.navigation.classList.remove("is-open");
    elements.menuToggle.setAttribute("aria-expanded", "false");
    elements.menuToggle.setAttribute("aria-label", "Open navigation");
  }
});

elements.dialogClose.addEventListener("click", () => elements.dialog.close());
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) {
    elements.dialog.close();
  }
});

for (const link of document.querySelectorAll(".primary-navigation .nav-link")) {
  link.addEventListener("click", () => {
    for (const navLink of document.querySelectorAll(".primary-navigation .nav-link")) {
      navLink.classList.toggle("is-active", navLink === link);
    }
  });
}

renderCategoryFilters();
setConnectionStatus("checking");
Promise.all([checkConnection(), loadOverview(), loadNews(), loadBriefing()]);
