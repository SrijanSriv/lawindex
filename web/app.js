"use strict";

/* LawIndex local UI — plain JS, hash routing, same-origin API only. */

const mainEl = document.getElementById("main");
const bannerEl = document.getElementById("coverage-banner");

/* The skip link must move keyboard focus into <main>, never change the
   hash route: "#main" is not an application route and would otherwise be
   handled by the router below and rendered as "page not found". */
document.getElementById("skip-link").addEventListener("click", (event) => {
  event.preventDefault();
  mainEl.focus();
});

/* ---------- small DOM helpers (never use innerHTML for API text) ---------- */

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (value !== null && value !== undefined) node.setAttribute(key, value);
    }
  }
  for (const child of children || []) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

/* ---------- metadata filters (shared by search view and corpus refresh) ---------- */

const FILTER_FIELDS = [
  { name: "act", label: "Act" },
  { name: "year", label: "Act year" },
  { name: "ministry", label: "Ministry" },
  { name: "document_type", label: "Document type" },
];

function filtersFromParams(params) {
  const filters = {};
  for (const field of FILTER_FIELDS) filters[field.name] = params.get(field.name) || "";
  return filters;
}

function buildRouteParams(query, filters) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  for (const field of FILTER_FIELDS) if (filters[field.name]) params.set(field.name, filters[field.name]);
  return params;
}

/* Repopulates a <select> from the current corpus options. `desiredValue`
   (when given) is the value to select, e.g. from the route on first mount;
   otherwise the select's own current value is preserved across a corpus
   refresh. A value with no matching option is kept selected as an extra,
   clearly-labelled option instead of being silently dropped. */
function populateFilterSelect(select, options, desiredValue) {
  const value = desiredValue !== undefined ? desiredValue : select.value;
  clear(select);
  select.append(el("option", { value: "", text: "All" }));
  const known = new Set();
  for (const option of options) {
    known.add(option.value);
    select.append(el("option", { value: option.value, text: option.label }));
  }
  const isUnknown = Boolean(value) && !known.has(value);
  if (isUnknown) select.append(el("option", { value, text: `${value} (not currently searchable)` }));
  select.value = value;
  return isUnknown;
}

/* ---------- fetch with stale-response protection ---------- */

let corpusController = null;
let latestCorpus = null;
let activeSearchControls = null; // set while the search view is mounted; lets a corpus refresh update its filter <select> options without disturbing the route

async function apiFetch(path, controller) {
  const response = await fetch(path, { cache: "no-store", signal: controller ? controller.signal : undefined });
  let body = null;
  try {
    body = await response.json();
  } catch (parseError) {
    throw { networkError: true, message: "The response could not be read." };
  }
  if (!response.ok) {
    const err = new Error((body && body.error && body.error.message) || "Request failed.");
    err.status = response.status;
    err.code = body && body.error && body.error.code;
    throw err;
  }
  return body;
}

/* ---------- coverage banner (shown on every view) ---------- */

async function refreshBanner() {
  if (corpusController) corpusController.abort();
  corpusController = new AbortController();
  const controller = corpusController;
  try {
    const corpus = await apiFetch("/api/corpus", controller);
    if (controller.signal.aborted) return;
    latestCorpus = corpus;
    renderBanner(corpus);
    if (activeSearchControls) activeSearchControls.refreshOptions();
  } catch (error) {
    if (controller.signal.aborted) return;
    clear(bannerEl);
    bannerEl.hidden = false;
    bannerEl.className = "coverage-banner coverage-banner--unavailable";
    bannerEl.append(el("strong", { text: "Coverage information is unavailable. " }));
    bannerEl.append(document.createTextNode(
      error && error.status === 503
        ? "The local database or its evidence could not be loaded."
        : "Could not reach the local server."
    ));
  }
}

function renderBanner(corpus) {
  clear(bannerEl);
  bannerEl.hidden = false;
  bannerEl.className = "coverage-banner";
  bannerEl.append(el("p", { class: "coverage-banner__notice", text: corpus.notice }));
  const summary = el("p", { class: "coverage-banner__summary" }, [
    `${corpus.provision_count} provision${corpus.provision_count === 1 ? "" : "s"} currently available across ${corpus.acts.length} Act${corpus.acts.length === 1 ? "" : "s"}. `,
    el("a", { href: "#/coverage", text: "See what is indexed" }),
    ".",
  ]);
  bannerEl.append(summary);
  if (corpus.excluded_since_import_count > 0) {
    bannerEl.append(el("p", { class: "coverage-banner__excluded" },
      [`${corpus.excluded_since_import_count} previously admitted provision(s) are currently excluded by live evidence checks.`]));
  }
}

/* ---------- readable metadata / permission labels ---------- */

function metadataText(value) {
  return value === null || value === undefined ? "Not recorded" : value;
}

function renderMetadataLine(metadata) {
  return el("p", { class: "metadata-line" }, [
    `Act year: ${metadataText(metadata.year)} (the source's recorded year — not a commencement date). ` +
    `Ministry: ${metadataText(metadata.ministry)}. ` +
    `Document type: ${metadataText(metadata.document_type)}.`,
  ]);
}

function permissionLabel(code) {
  if (code === "personal_noncommercial_20_acts_user_reported") {
    return "Ministry permission reported for up to 20 Acts for this personal, non-commercial project.";
  }
  return `Permission status: ${code}.`;
}

/* ---------- router ---------- */

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [pathPart, queryPart] = raw.split("?");
  const path = pathPart || "/";
  const params = new URLSearchParams(queryPart || "");
  if (path === "/" || path === "") return { view: "search", params };
  if (path === "/coverage") return { view: "coverage", params };
  const provisionMatch = path.match(/^\/provisions\/(.+)$/);
  if (provisionMatch) return { view: "provision", key: provisionMatch[1], params };
  return { view: "not-found", params };
}

let currentRoute = null;

function route() {
  const parsed = parseHash();
  currentRoute = parsed;
  refreshBanner();
  if (parsed.view === "search") renderSearchView(parsed.params);
  else if (parsed.view === "provision") renderProvisionView(parsed.key);
  else if (parsed.view === "coverage") renderCoverageView();
  else renderNotFoundView();
}

function refreshOnFocus() {
  if (!currentRoute) return;
  if (currentRoute.view === "search") {
    const q = currentRoute.params.get("q") || "";
    const filters = filtersFromParams(currentRoute.params);
    if (q || Object.values(filters).some(Boolean)) runSearch(q, filters, false);
    refreshBanner();
  } else if (currentRoute.view === "provision") {
    renderProvisionView(currentRoute.key);
  } else if (currentRoute.view === "coverage") {
    renderCoverageView();
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", route);
window.addEventListener("focus", refreshOnFocus);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshOnFocus();
});

/* ---------- search view ---------- */

let searchController = null;
let searchSeq = 0;

function renderSearchView(params) {
  activeSearchControls = null;
  clear(mainEl);

  const initialQuery = params.get("q") || "";
  const initialFilters = filtersFromParams(params);

  const heading = el("h1", { text: "Search reviewed provisions" });
  const purpose = el("p", { class: "purpose" }, [
    "Search the small set of Indian legislation provisions reviewed so far. Results show exact excerpts from admitted text, never a generated answer.",
  ]);

  const form = el("form", { class: "search-form", role: "search", "aria-label": "Search provisions" });
  const label = el("label", { for: "search-input", text: "Search query" });
  const input = el("input", {
    id: "search-input",
    name: "q",
    type: "search",
    autocomplete: "off",
    spellcheck: "false",
    maxlength: "500",
    placeholder: "e.g. exemption from disclosure, section 6, EPA section 3",
  });
  input.value = initialQuery;

  const selects = {};
  const filterRow = el("div", { class: "filter-row" });
  for (const field of FILTER_FIELDS) {
    const selectId = `filter-${field.name}`;
    const select = el("select", { id: selectId, name: field.name });
    select.append(el("option", { value: "", text: "All" }));
    filterRow.append(el("div", { class: "filter-field" }, [
      el("label", { for: selectId, text: field.label }),
      select,
    ]));
    selects[field.name] = select;
  }

  const queryHint = el("p", { class: "filter-hint", id: "query-hint" }, [
    "Quote a phrase to require it exactly (e.g. \u201cgive any reason\u201d). ",
    "Act citations such as \u201cAct 22 of 2005\u201d or \u201cAct, 2013\u201d, and references such as \u201csection 6\u201d, narrow results and never fall back to another Act or section.",
  ]);
  input.setAttribute("aria-describedby", "query-hint");
  const filterHint = el("p", { class: "filter-hint" }, [
    "Filter choices cover only the provisions currently searchable below — not the full proposed 20-Act inventory.",
  ]);
  const filterWarnings = el("div", { class: "filter-warning-region", "aria-live": "polite" });

  const actionRow = el("div", { class: "filter-actions" });
  const submit = el("button", { type: "submit", text: "Search" });
  const resetButton = el("button", { type: "button", class: "reset-button", text: "Clear all" });
  actionRow.append(submit, resetButton);

  form.append(label, input, queryHint, filterRow, filterHint, filterWarnings, actionRow);

  const resultsRegion = el("div", { id: "search-results", "aria-live": "polite" });

  function currentFilters() {
    const filters = {};
    for (const field of FILTER_FIELDS) filters[field.name] = selects[field.name].value;
    return filters;
  }

  function refreshOptions(desiredFilters) {
    // latestCorpus may not have loaded yet (e.g. right after a hard reload); until it
    // does, every field falls back to an empty option list so a route-supplied value
    // is still kept selected (as a temporarily "unknown" option) rather than lost.
    const optionSources = latestCorpus
      ? {
          act: latestCorpus.acts.map((act) => ({ value: act.slug, label: act.title })),
          year: latestCorpus.filter_options.year.map((value) => ({ value, label: value })),
          ministry: latestCorpus.filter_options.ministry.map((value) => ({ value, label: value })),
          document_type: latestCorpus.filter_options.document_type.map((value) => ({ value, label: value })),
        }
      : { act: [], year: [], ministry: [], document_type: [] };
    const unknownFields = [];
    for (const field of FILTER_FIELDS) {
      const desired = desiredFilters ? desiredFilters[field.name] : undefined;
      if (populateFilterSelect(selects[field.name], optionSources[field.name], desired)) unknownFields.push(field);
    }
    renderWarnings(unknownFields);
  }

  function renderWarnings(unknownFields) {
    clear(filterWarnings);
    for (const field of unknownFields) {
      const value = selects[field.name].value;
      const line = el("p", { class: "filter-warning", role: "alert" }, [
        `“${value}” is not one of the currently searchable ${field.label.toLowerCase()} choices. It stays selected but will not broaden the search. `,
      ]);
      line.append(el("button", {
        type: "button",
        text: `Clear ${field.label}`,
        onclick: () => {
          selects[field.name].value = "";
          refreshOptions();
          navigate();
        },
      }));
      filterWarnings.append(line);
    }
  }

  function navigate() {
    const q = input.value.trim();
    const filters = currentFilters();
    const routeParams = buildRouteParams(q, filters);
    const nextHash = routeParams.toString() ? `#/?${routeParams.toString()}` : "#/";
    const hasCriteria = Boolean(q) || Object.values(filters).some(Boolean);
    if (window.location.hash === nextHash) {
      if (hasCriteria) runSearch(q, filters, true);
      else renderSearchIdle(resultsRegion);
    } else {
      window.location.hash = nextHash;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    navigate();
  });

  resetButton.addEventListener("click", () => {
    input.value = "";
    for (const field of FILTER_FIELDS) selects[field.name].value = "";
    refreshOptions();
    navigate();
  });

  mainEl.append(heading, purpose, form, resultsRegion);
  heading.setAttribute("tabindex", "-1");
  heading.focus();

  activeSearchControls = { refreshOptions };
  refreshOptions(initialFilters);

  // Decide from the route's own values, not from currentFilters(): the <select>s may
  // not have their options populated yet if /api/corpus hasn't resolved (e.g. right
  // after a hard reload), and reading them back too early would wrongly look empty.
  if (initialQuery || Object.values(initialFilters).some(Boolean)) runSearch(initialQuery, initialFilters, true);
  else renderSearchIdle(resultsRegion);
}

function renderSearchIdle(container) {
  clear(container);
  container.append(el("p", { class: "hint", text: "Enter a query above, choose filters, or browse the current coverage list." }));
}

async function runSearch(query, filters, showLoadingState) {
  const container = document.getElementById("search-results");
  if (!container) return;
  const mySeq = ++searchSeq;

  if (searchController) searchController.abort();
  searchController = new AbortController();
  const controller = searchController;

  if (showLoadingState) {
    clear(container);
    container.append(el("p", { class: "loading", role: "status", text: "Searching…" }));
  }

  const apiParams = buildRouteParams(query, filters);
  apiParams.set("limit", "10");

  try {
    const data = await apiFetch(`/api/search?${apiParams.toString()}`, controller);
    if (mySeq !== searchSeq || controller.signal.aborted) return;
    renderSearchResults(container, data, query, filters);
  } catch (error) {
    if (mySeq !== searchSeq || controller.signal.aborted) return;
    clear(container);
    if (error && error.status === 400) {
      container.append(el("p", { class: "error", role: "alert" }, [error.message]));
    } else if (error && error.status === 503) {
      container.append(renderUnavailable(() => runSearch(query, filters, true)));
    } else {
      container.append(renderNetworkError(() => runSearch(query, filters, true)));
    }
  }
}

/* What the index does not hold. Notices never hide results; they say
   where a query reaches outside the index. */
function renderCoverageNotices(container, data) {
  const notices = Array.isArray(data.notices) ? data.notices : [];
  if (notices.length > 0) {
    const box = el("div", { class: "search-notices", role: "note" });
    for (const notice of notices) {
      box.append(el("p", { class: "search-notice", text: notice.message }));
    }
    container.append(box);
  }
  if (data.scope && data.scope.statement) {
    container.append(el("p", { class: "search-scope" }, [
      data.scope.statement + " ",
      el("a", { href: "#/coverage", text: "Coverage" }),
    ]));
  }
}

/* When a query names no Act, one Act may not take over the page. Offer the
   close matches the cap kept back, as a search within that Act. */
function renderMoreInActs(container, data, query, filters) {
  const more = Array.isArray(data.more_in_acts) ? data.more_in_acts : [];
  if (more.length === 0) return;
  const line = el("p", { class: "more-in-acts" }, ["More close matches in: "]);
  more.forEach((entry, index) => {
    if (index > 0) line.append(document.createTextNode(" · "));
    const params = buildRouteParams(query, { ...filters, act: entry.act_slug });
    line.append(el("a", { href: `#/?${params.toString()}` },
      [`${entry.act_title} (${entry.close_matches_not_shown})`]));
  });
  container.append(line);
}

function renderSearchResults(container, data, query, filters) {
  clear(container);
  const routeParams = buildRouteParams(query, filters);
  renderCoverageNotices(container, data);

  if (data.results.length === 0) {
    container.append(el("p", { class: "empty-state" }, [
      query
        ? `No matches among the ${data.corpus.provision_count} currently available provision(s) for “${query}”. `
        : `No matches among the ${data.corpus.provision_count} currently available provision(s) for the selected filters. `,
      el("a", { href: "#/coverage", text: "See what is indexed" }),
      ".",
    ]));
    return;
  }

  const countLine = el("p", { class: "result-count" }, [
    query
      ? `${data.total} result${data.total === 1 ? "" : "s"} for “${data.query}”.`
      : `${data.total} result${data.total === 1 ? "" : "s"} for the selected filters.`,
  ]);
  container.append(countLine);

  const list = el("ol", { class: "result-list" });
  for (const result of data.results) {
    list.append(renderResultItem(result, routeParams));
  }
  container.append(list);
  renderMoreInActs(container, data, query, filters);
}

function renderResultItem(result, routeParams) {
  const item = el("li", { class: "result-item" });

  const qs = routeParams.toString();
  const link = el("a", {
    href: `#/provisions/${encodeURIComponent(result.key)}${qs ? `?${qs}` : ""}`,
    class: "result-title",
  }, [`${result.act_title} — Section ${result.section_number}. ${result.heading}`]);
  item.append(el("h2", { class: "result-heading" }, [link]));

  const excerpt = el("p", { class: "result-excerpt" });
  for (const segment of result.excerpt.segments) {
    excerpt.append(el(segment.match ? "mark" : "span", { text: segment.text }));
  }
  const wrapped = el("p", { class: "result-excerpt-wrap" });
  if (result.excerpt.omitted_before) wrapped.append(document.createTextNode("… "));
  wrapped.append(excerpt);
  item.append(wrapped);
  if (result.excerpt.omitted_after) wrapped.append(document.createTextNode(" …"));

  const contextLabel = excerptContextLabel(result.excerpt.context);
  if (contextLabel) item.append(el("p", { class: "excerpt-context", text: contextLabel }));

  item.append(renderMetadataLine(result.metadata));

  const badges = el("p", { class: "result-badges" });
  if (result.conflicts.length > 0) {
    badges.append(el("span", { class: "badge badge--conflict", text: "Source conflict recorded" }));
  }
  if (result.has_footnote) {
    badges.append(el("span", { class: "badge badge--footnote", text: "Has footnote" }));
  }
  if (result.review && result.review.individually_reviewed === false) {
    badges.append(el("span", {
      class: "badge badge--sampled", title: result.review.basis,
      text: "Text matched to source; not individually reviewed",
    }));
  }
  if (badges.childNodes.length > 0) item.append(badges);

  return item;
}

/* The context is read from the reviewed text's own numbering and proviso
   markers (see excerpt_context_note in the API response). It says where the
   highlighted text sits; it is not a separately admitted structure. */
function excerptContextLabel(context) {
  if (!context || (context.subsection === null && !context.proviso)) return null;
  const where = context.subsection === null ? "the provision" : `sub-section (${context.subsection})`;
  return context.proviso
    ? `Highlighted text is in a proviso to ${where}, per the provision's own markers.`
    : `Highlighted text is in ${where}, per the provision's own markers.`;
}

/* ---------- provision view ---------- */

let provisionController = null;
let provisionSeq = 0;

function renderProvisionView(encodedKey) {
  activeSearchControls = null;
  clear(mainEl);
  const qs = currentRoute ? currentRoute.params.toString() : "";
  const backLink = el("a", { class: "back-link", href: qs ? `#/?${qs}` : "#/" },
    ["← Back to search"]);
  const body = el("div", { id: "provision-body" });
  body.append(el("p", { class: "loading", role: "status", text: "Loading provision…" }));
  mainEl.append(backLink, body);

  loadProvision(encodedKey, body);
}

async function loadProvision(encodedKey, container) {
  const mySeq = ++provisionSeq;
  if (provisionController) provisionController.abort();
  provisionController = new AbortController();
  const controller = provisionController;

  try {
    const data = await apiFetch(`/api/provisions/${encodedKey}`, controller);
    if (mySeq !== provisionSeq || controller.signal.aborted) return;
    renderProvisionDetail(container, data.provision, data.navigation);
  } catch (error) {
    if (mySeq !== provisionSeq || controller.signal.aborted) return;
    clear(container);
    if (error && error.status === 404) {
      container.append(el("h1", { text: "Provision not found" }));
      container.append(el("p", { class: "empty-state" }, [
        "This provision is not currently admitted. It may have been withdrawn, or the link may be out of date. ",
        el("a", { href: "#/coverage", text: "See current coverage" }),
        ".",
      ]));
    } else if (error && error.status === 503) {
      container.append(renderUnavailable(() => loadProvision(encodedKey, container)));
    } else {
      container.append(renderNetworkError(() => loadProvision(encodedKey, container)));
    }
  }
}

function renderProvisionDetail(container, provision, navigation) {
  clear(container);

  const heading = el("h1", { text: `${provision.act_title} — Section ${provision.section_number}` });
  heading.setAttribute("tabindex", "-1");
  container.append(heading);
  container.append(el("p", { class: "provision-heading-label", text: provision.heading }));
  container.append(renderMetadataLine(provision.metadata));

  if (provision.conflicts.length > 0) {
    const conflictBox = el("div", { class: "conflict-box", role: "note" });
    conflictBox.append(el("h2", { text: "Source conflict" }));
    for (const conflict of provision.conflicts) {
      const entry = el("div", { class: "conflict-entry" });
      entry.append(el("p", { class: "conflict-meta" },
        [`${conflict.id} — ${conflict.classification} (${conflict.disposition})`]));
      entry.append(el("p", { class: "conflict-explanation", text: conflict.explanation }));
      conflictBox.append(entry);
    }
    container.append(conflictBox);
  }

  container.append(el("p", { class: "coverage-note", text: provision.coverage_note }));

  const bodyPre = el("pre", { class: "provision-text" });
  bodyPre.textContent = provision.body_text;
  container.append(bodyPre);

  if (provision.footnote_text) {
    const footnoteBox = el("div", { class: "footnote-box" });
    footnoteBox.append(el("h2", { text: "Footnote" }));
    const footnotePre = el("pre", { class: "footnote-text" });
    footnotePre.textContent = provision.footnote_text;
    footnoteBox.append(footnotePre);
    container.append(footnoteBox);
  }

  const reviewBox = el("div", { class: "review-note" });
  reviewBox.append(el("p", {},
    [`Review: ${provision.review.type}. Independent legal expert review: ${provision.review.independent_legal_expert ? "yes" : "no"}.`]));
  if (provision.review.basis) reviewBox.append(el("p", { text: provision.review.basis }));
  container.append(reviewBox);

  container.append(renderSourceSection(provision.source));
  if (navigation) container.append(renderNavigation(navigation, provision.key));

  const details = el("details", { class: "dev-panel" });
  details.append(el("summary", { text: "Provenance details (developer)" }));
  const dl = el("dl", { class: "provenance-list" });
  const source = provision.source;
  const fields = [
    ["Fetched at (source PDF capture)", source.fetched_at],
    ["Source-stated modification date", source.source_stated_modified_date || "Not stated"],
    ["PDF sha256", source.pdf_sha256],
    ["Text source sha256", source.text_source_sha256],
    ["Body text sha256", source.body_text_sha256],
    ["Representation", provision.representation],
  ];
  for (const [term, value] of fields) {
    dl.append(el("dt", { text: term }));
    dl.append(el("dd", { text: value }));
  }
  details.append(dl);
  container.append(details);
}

/* Previous/next move only between admitted provisions of the same Act. The
   API's note and source section count are shown so a gap (e.g. 3 → 6) is
   never read as "nothing in between". */
function renderNavigation(navigation, currentKey) {
  const qs = currentRoute ? currentRoute.params.toString() : "";
  const href = (key) => `#/provisions/${encodeURIComponent(key)}${qs ? `?${qs}` : ""}`;
  const nav = el("nav", { class: "provision-nav", "aria-label": "Admitted provisions of this Act" });
  nav.append(el("h2", { text: "In this Act" }));

  const links = el("p", { class: "provision-nav__links" });
  if (navigation.previous) {
    links.append(el("a", { href: href(navigation.previous.key) },
      [`← Section ${navigation.previous.section_number}. ${navigation.previous.heading}`]));
  } else {
    links.append(el("span", { class: "provision-nav__end", text: "No earlier admitted provision" }));
  }
  links.append(document.createTextNode(" · "));
  if (navigation.next) {
    links.append(el("a", { href: href(navigation.next.key) },
      [`Section ${navigation.next.section_number}. ${navigation.next.heading} →`]));
  } else {
    links.append(el("span", { class: "provision-nav__end", text: "No later admitted provision" }));
  }
  nav.append(links);

  const list = el("ul", { class: "provision-nav__list" });
  for (const item of navigation.admitted) {
    const current = item.key === currentKey;
    list.append(el("li", current ? { "aria-current": "page" } : {}, [
      current ? `Section ${item.section_number}. ${item.heading} (this page)`
        : el("a", { href: href(item.key) }, [`Section ${item.section_number}. ${item.heading}`]),
    ]));
  }
  nav.append(list);

  const countText = navigation.source_section_count === null
    ? "The source's section count is not recorded."
    : `The source lists ${navigation.source_section_count} sections for this Act; ${navigation.admitted.length} are admitted here.`;
  nav.append(el("p", { class: "source-caveat" }, [`${navigation.note} ${countText}`]));
  return nav;
}

function renderSourceSection(source) {
  const section = el("section", { class: "source-section", "aria-label": "Source verification" });
  section.append(el("h2", { text: "Source" }));

  const pdfLine = el("p");
  pdfLine.append(el("a", { href: source.local_pdf_url, target: "_blank", rel: "noopener" },
    ["Source PDF — only listed provisions reviewed."]));
  pdfLine.append(document.createTextNode(` (verified file pages ${source.pdf_page_from}–${source.pdf_page_to})`));
  section.append(pdfLine);

  const downloadLine = el("p", {}, [
    el("a", { href: source.pdf_download_url, target: "_blank", rel: "noopener" }, ["Download full retained PDF"]),
  ]);
  section.append(downloadLine);

  const originalLine = el("p", {}, [
    el("a", { href: source.act_url, target: "_blank", rel: "noopener" }, ["Original India Code Act page"]),
    document.createTextNode(" · "),
    el("a", { href: source.viewer_url, target: "_blank", rel: "noopener" }, ["Original India Code PDF viewer"]),
    document.createTextNode(" (remote availability not guaranteed)"),
  ]);
  section.append(originalLine);

  section.append(el("p", { class: "source-caveat" },
    ["The source PDF may contain sections beyond the ones reviewed here. Access to the full PDF is not a claim that its full text is indexed."]));

  return section;
}

/* ---------- coverage view ----------
   Two independent panels, each with its own fetch/abort/sequence tracking,
   so a failure or slow response in one can never blank out or race against
   the other: the live searchable-corpus panel (unchanged from before) and
   the Phase 3 acquisition/candidate inventory panel (new). */

let coverageController = null;
let coverageSeq = 0;
let inventoryController = null;
let inventorySeq = 0;

function renderCoverageView() {
  activeSearchControls = null;
  clear(mainEl);
  mainEl.append(el("h1", { text: "Current coverage" }));

  const inventoryBody = el("div", { id: "inventory-body" });
  inventoryBody.append(el("p", { class: "loading", role: "status", text: "Loading Phase 3 acquisition coverage…" }));
  mainEl.append(inventoryBody);

  const body = el("div", { id: "coverage-body" });
  body.append(el("p", { class: "loading", role: "status", text: "Loading coverage…" }));
  mainEl.append(body);

  loadInventory(inventoryBody);
  loadCoverage(body);
}

async function loadCoverage(container) {
  const mySeq = ++coverageSeq;
  if (coverageController) coverageController.abort();
  coverageController = new AbortController();
  const controller = coverageController;

  try {
    const corpus = await apiFetch("/api/corpus", controller);
    if (mySeq !== coverageSeq || controller.signal.aborted) return;
    renderCoverageDetail(container, corpus);
  } catch (error) {
    if (mySeq !== coverageSeq || controller.signal.aborted) return;
    clear(container);
    if (error && error.status === 503) container.append(renderUnavailable(() => loadCoverage(container)));
    else container.append(renderNetworkError(() => loadCoverage(container)));
  }
}

/* ---------- Phase 3 acquisition/candidate inventory panel ---------- */

async function loadInventory(container) {
  const mySeq = ++inventorySeq;
  if (inventoryController) inventoryController.abort();
  inventoryController = new AbortController();
  const controller = inventoryController;

  try {
    const report = await apiFetch("/api/inventory", controller);
    if (mySeq !== inventorySeq || controller.signal.aborted) return;
    renderInventoryDetail(container, report);
  } catch (error) {
    // A failed inventory fetch must never manufacture zero coverage or touch
    // the separate searchable-corpus panel: it only replaces this panel's
    // own container with a retry-capable error state.
    if (mySeq !== inventorySeq || controller.signal.aborted) return;
    clear(container);
    if (error && error.status === 503) container.append(renderUnavailable(() => loadInventory(container)));
    else container.append(renderNetworkError(() => loadInventory(container)));
  }
}

function inventoryCount(value, singular) {
  if (value === null || value === undefined) return "Unknown";
  return `${value} ${singular}${value === 1 ? "" : "s"}`;
}

const ACQUISITION_STATUS_LABEL = {
  not_requested: "Not yet captured",
  captured_review_pending: "Captured — review pending",
  acquisition_failed: "Capture failed",
  invalid_evidence: "Capture evidence invalid or stale",
};

const CANDIDATE_STATUS_LABEL = {
  not_processed: "Not yet processed",
  parsed_review_pending: "Candidates extracted — review pending",
  parse_failed: "Candidate extraction failed",
  unavailable: "Unavailable",
};

function statusLabel(map, code) {
  return map[code] || code;
}

function renderInventoryDetail(container, report) {
  clear(container);

  const section = el("section", { class: "inventory-section", "aria-labelledby": "inventory-heading" });
  section.append(el("h2", { id: "inventory-heading", text: "Phase 3 acquisition and candidate coverage" }));
  section.append(el("p", { class: "purpose" }, [
    "This panel tracks the bounded 20-Act acquisition and its text-comparison candidates. ",
    "Captured or matching text shown here is bookkeeping only — it is not reviewed, not admitted, ",
    "and not approved for search. The searchable counts above come from a separately reviewed and admitted corpus.",
  ]));

  const summary = el("dl", { class: "inventory-summary" });
  const summaryEntries = [
    ["Selected Acts", report.selected_act_count],
    ["Captured Acts", report.captured_act_count],
    ["Searchable Acts", report.searchable_act_count],
    ["Searchable provisions", report.searchable_provision_count],
  ];
  for (const [label, value] of summaryEntries) {
    summary.append(el("div", { class: "inventory-summary__item" }, [
      el("dt", { text: label }),
      el("dd", { text: value === null || value === undefined ? "Unknown" : String(value) }),
    ]));
  }
  section.append(summary);

  if (Array.isArray(report.limitations) && report.limitations.length > 0) {
    const limitations = el("ul", { class: "inventory-limitations" });
    for (const note of report.limitations) limitations.append(el("li", { text: note }));
    section.append(limitations);
  }

  const list = el("ul", { class: "inventory-act-list" });
  for (const row of report.rows) list.append(renderInventoryRow(row));
  section.append(list);

  container.append(section);
}

function renderInventoryRow(row) {
  const item = el("li", { class: "inventory-act-card" });
  item.append(el("h3", { class: "inventory-act-card__title", text: row.title }));

  const fields = el("dl", { class: "inventory-act-card__fields" });
  const rows = [
    ["Capture outcome", statusLabel(ACQUISITION_STATUS_LABEL, row.acquisition_status)],
    ["Source-listed sections", inventoryCount(row.source_section_count, "section")],
    ["Candidate status", statusLabel(CANDIDATE_STATUS_LABEL, row.candidate_status)],
    ["Exact comparison review pending", inventoryCount(row.agreement_review_pending_count, "candidate")],
    ["Typographic comparison review pending", inventoryCount(row.typographic_agreement_review_pending_count, "candidate")],
    ["Quarantined", inventoryCount(row.quarantined_count, "candidate")],
    ["Live searchable provisions", inventoryCount(row.searchable_provision_count, "provision")],
    ["Full-Act coverage verified", row.full_act_coverage_verified ? "Yes" : "No"],
  ];
  for (const [label, value] of rows) {
    fields.append(el("div", { class: "inventory-act-card__field" }, [
      el("dt", { text: label }),
      el("dd", { text: value }),
    ]));
  }
  item.append(fields);

  const reasons = row.quarantine_reasons && typeof row.quarantine_reasons === "object"
    ? Object.entries(row.quarantine_reasons) : [];
  // Agreed Phase 3 coverage target: an Act with less than half its sections
  // searchable shows why, open and flagged, rather than behind a toggle.
  const low = Number.isInteger(row.source_section_count) && row.source_section_count > 0
    && row.searchable_provision_count / row.source_section_count < 0.5;
  if (low) {
    const share = Math.round(100 * row.searchable_provision_count / row.source_section_count);
    item.classList.add("inventory-act-card--low");
    item.append(el("p", { class: "inventory-act-card__low", role: "note" }, [
      `Only ${share}% of this Act's sections are searchable. The rest are held back, mostly because the portal's text `
      + "and the official PDF disagree. The reasons are listed below; held-back sections are not a finding that the law is wrong.",
    ]));
  }
  if (reasons.length > 0) {
    const list = el("ul", { class: "inventory-act-card__reasons" });
    for (const [reason, count] of reasons) list.append(el("li", { text: `${reason}: ${count}` }));
    const details = el("details", { class: "inventory-act-card__reasons-wrap" }, [
      el("summary", { text: "Quarantine reasons" }), list]);
    if (low) details.open = true;
    item.append(details);
  }

  if (row.diagnostic) {
    item.append(el("p", { class: "inventory-act-card__diagnostic", role: "note" }, [
      el("strong", { text: "Diagnostic: " }),
      row.diagnostic,
    ]));
  }

  item.append(el("p", { class: "inventory-act-card__note" }, [
    "Exact comparison folds whitespace only; typographic comparison also applies enumerated normalizations ",
    "(dash and quote glyphs, reference marks, hyphenation, spacing, case, editorial brackets, footnote blocks at page breaks) ",
    "recorded on each candidate. Neither is fidelity approval. Quarantined candidates are not automatically a wording error ",
    "in the law — they may reflect formatting, parser limitations, or ambiguous alignment that still needs review. ",
    "Comparison-review-pending and quarantined counts can overlap previously admitted provisions and are never summed into the searchable count.",
  ]));

  return item;
}

function renderCoverageDetail(container, corpus) {
  clear(container);
  container.append(el("p", { class: "purpose", text: corpus.notice }));
  container.append(el("p", {}, [
    `${corpus.provision_count} provision(s) are currently available. Whole Acts are not indexed — only the sections listed below.`,
  ]));
  if (corpus.excluded_since_import_count > 0) {
    container.append(el("p", { class: "coverage-banner__excluded" },
      [`${corpus.excluded_since_import_count} previously admitted provision(s) are currently excluded by live evidence checks.`]));
  }
  container.append(el("p", { class: "permission-note" }, [permissionLabel(corpus.public_use_permission)]));

  for (const act of corpus.acts) {
    const actSection = el("section", { class: "coverage-act" });
    actSection.append(el("h2", { text: act.title }));
    actSection.append(renderMetadataLine(act.metadata));
    const list = el("ul", { class: "coverage-provision-list" });
    for (const provision of act.provisions) {
      const item = el("li");
      item.append(el("a", { href: `#/provisions/${encodeURIComponent(provision.key)}` },
        [`Section ${provision.section_number}. ${provision.heading}`]));
      list.append(item);
    }
    actSection.append(list);
    container.append(actSection);
  }

  container.append(el("p", {}, [el("a", { href: "#/", text: "← Back to search" })]));
}

/* ---------- shared error/unavailable widgets ---------- */

function renderUnavailable(onRetry) {
  const box = el("div", { class: "unavailable-state", role: "alert" });
  box.append(el("p", {}, ["The local database or required evidence is currently unavailable."]));
  box.append(el("button", { type: "button", text: "Retry", onclick: onRetry }));
  return box;
}

function renderNetworkError(onRetry) {
  const box = el("div", { class: "unavailable-state", role: "alert" });
  box.append(el("p", {}, ["Could not reach the local server. Check that it is still running."]));
  box.append(el("button", { type: "button", text: "Retry", onclick: onRetry }));
  return box;
}

function renderNotFoundView() {
  activeSearchControls = null;
  clear(mainEl);
  mainEl.append(el("h1", { text: "Page not found" }));
  mainEl.append(el("p", {}, [el("a", { href: "#/", text: "Go to search" })]));
}
