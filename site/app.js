const $ = (selector) => document.querySelector(selector);
const number = new Intl.NumberFormat("en-US");
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });
let catalogue;
let visible = [];

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

const label = (entry) => entry.model.display_name || entry.model.id;
const remote = (entry) => entry.upstream?.model || {};
const price = (value) => value == null ? "Unknown" : money.format(value);
const capacity = (value) => value == null ? "Unknown" : number.format(value);
const key = (entry) => `${entry.provider}/${entry.model.id}`;
const offeredPrice = (entry) => entry.pricing_basis === "reference" ? null : entry.model.pricing;

function differences(entry) {
  const labels = { context: "Context", input_per_million: "Input price", output_per_million: "Output price", cache_read_per_million: "Cache read price", cache_write_per_million: "Cache write price (full charge)" };
  return (entry.upstream?.differences || []).map(([field, a, b]) => [labels[field] || field, a, b]);
}

function matches(entry, query, provider, capability) {
  if (!$("#retired").checked && entry.model.deprecated) return false;
  if (provider && entry.provider !== provider) return false;
  if (capability === "vision" && entry.model.supports_vision !== true) return false;
  if (capability === "tools" && remote(entry).tool_call !== true) return false;
  if (capability === "reasoning" && remote(entry).reasoning !== true) return false;
  return `${label(entry)} ${entry.model.id} ${remote(entry).description || ""}`.toLowerCase().includes(query);
}

function render() {
  const query = $("#search").value.trim().toLowerCase();
  visible = catalogue.models.filter((entry) => matches(entry, query, $("#provider").value, $("#capability").value));
  const sort = $("#sort").value;
  visible.sort((a, b) => {
    if (sort === "cost") return (offeredPrice(a)?.input_per_million ?? Infinity) - (offeredPrice(b)?.input_per_million ?? Infinity) || label(a).localeCompare(label(b));
    if (sort === "context") return (b.model.context_window ?? 0) - (a.model.context_window ?? 0) || label(a).localeCompare(label(b));
    return label(a).localeCompare(label(b)) || a.provider.localeCompare(b.provider);
  });
  $("#rows").replaceChildren(...visible.map(row));
  $("#results").textContent = `${visible.length} of ${catalogue.models.length} models`;
  $("#empty").hidden = visible.length > 0;
  $(".table-scroll").hidden = visible.length === 0;
}

function row(entry) {
  const tr = element("tr");
  const title = element("td");
  const button = element("button", label(entry), "model-link");
  button.type = "button";
  button.addEventListener("click", () => openDetails(entry));
  title.append(button, element("span", entry.model.id, "model-id"));
  if (entry.model.deprecated) title.append(element("span", "Deprecated", "badge"));
  if (differences(entry).length) title.append(element("span", "Sources differ", "badge warn"));
  const costs = offeredPrice(entry);
  const vision = entry.model.supports_vision;
  const action = element("td");
  const open = element("button", "↗", "row-open");
  open.type = "button";
  open.setAttribute("aria-label", `Details for ${label(entry)} on ${catalogue.providers[entry.provider].name}`);
  open.addEventListener("click", () => openDetails(entry));
  action.append(open);
  tr.append(title, element("td", catalogue.providers[entry.provider].name, "muted"), element("td", capacity(entry.model.context_window), "number"), element("td", costs ? `${price(costs.input_per_million)} / ${price(costs.output_per_million)}` : entry.pricing_basis === "reference" ? "Reference only" : "Unknown", "number"), element("td", vision == null ? "Unknown" : vision ? "Yes" : "No", vision ? "yes" : "muted"), action);
  return tr;
}

function sourceLink(url, text) {
  const link = element("a", text, "source-link");
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.username) return element("span", "Source unavailable");
    link.href = parsed.href;
  } catch { return element("span", "Source unavailable"); }
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function facts(values) {
  const list = element("dl");
  for (const [name, value] of values) list.append(element("dt", name), element("dd", value));
  return list;
}

function referenceDetails(entry) {
  const model = entry.model;
  const pricing = model.pricing;
  const group = element("section");
  if (entry.pricing_note) group.append(element("p", entry.pricing_note, "detail-note warn"));
  const prefix = entry.pricing_basis === "reference" ? "Reference " : "";
  group.append(element("h3", "Catalogue reference"), facts([
    ["Provider", catalogue.providers[entry.provider].name],
    ["Context window", `${capacity(model.context_window)}${model.context_window ? " tokens" : ""}`],
    ["Image input", model.supports_vision == null ? "Unknown" : model.supports_vision ? "Yes" : "No"],
    [`${prefix}Input / 1M tokens`, price(pricing?.input_per_million)],
    [`${prefix}Output / 1M tokens`, price(pricing?.output_per_million)],
    ["Cache read / 1M tokens", price(pricing?.cache_read_per_million)],
    ["Price verified", pricing?.verified || "Not recorded"]
  ]), sourceLink(entry.source, "Original RoomKit source ↗"));
  if (pricing?.long_context_threshold_tokens) group.append(element("p", `Above ${capacity(pricing.long_context_threshold_tokens)} input tokens: input ×${pricing.long_context_input_multiplier}, output ×${pricing.long_context_output_multiplier}.`));
  return group;
}

function upstreamDetails(entry) {
  const group = element("section");
  group.append(element("h3", "From models.dev"));
  if (!entry.upstream) {
    group.append(element("p", "No exact match on this provider. This does not establish availability or retirement."));
    return group;
  }
  const model = remote(entry);
  const yesNo = (value) => value == null ? "Unknown" : value ? "Yes" : "No";
  if (model.description) group.append(element("p", model.description));
  group.append(facts([["Tool calling", yesNo(model.tool_call)], ["Reasoning", yesNo(model.reasoning)], ["Maximum output", capacity(model.limit?.output)], ["Released", model.release_date || "Unknown"], ["Metadata retrieved", entry.upstream.retrieved_at.slice(0, 10)]]));
  const conflicts = differences(entry);
  if (conflicts.length) {
    group.append(element("p", "Sources differ. The catalogue reference is preserved pending review.", "detail-note warn"));
    const list = element("ul");
    for (const [name, local, upstream] of conflicts) list.append(element("li", `${name}: catalogue ${local}; models.dev ${upstream}.`));
    group.append(list);
  }
  group.append(sourceLink(entry.upstream.source, "models.dev source ↗"));
  return group;
}

function guidanceDetails(entry) {
  const group = element("section");
  group.append(element("h3", "Choosing this model"));
  const guidance = entry.guidance;
  if (!guidance) {
    group.append(element("p", "No RoomKit coding evaluation yet. The facts above describe capabilities and list prices; they do not rank coding quality or speed.", "detail-note"));
    return group;
  }
  group.append(element("p", guidance.summary));
  for (const [title, items] of [["Recommended for", guidance.recommended_for], ["Limitations", guidance.limitations]]) {
    group.append(element("h3", title));
    const list = element("ul");
    for (const item of items) list.append(element("li", item));
    group.append(list);
  }
  group.append(element("p", `${guidance.basis} · Reviewed ${guidance.reviewed_on}`));
  for (const url of guidance.sources) group.append(sourceLink(url, "Evidence ↗"));
  return group;
}

function openDetails(entry, updateLocation = true) {
  const title = element("h2", label(entry));
  title.id = "detail-title";
  $("#detail-content").replaceChildren(title, element("p", key(entry), "model-id"), referenceDetails(entry), upstreamDetails(entry), guidanceDetails(entry));
  if (!$("#details").open) $("#details").showModal();
  if (updateLocation) history.replaceState(null, "", `#${encodeURIComponent(key(entry))}`);
}

function restoreDetail() {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
  const entry = catalogue.models.find((model) => key(model) === id);
  if (entry) openDetails(entry, false);
}

async function start() {
  try {
    const response = await fetch("v1/catalog.json");
    if (!response.ok) throw new Error("Catalogue unavailable");
    catalogue = await response.json();
    if (catalogue.schema_version !== 1 || !Array.isArray(catalogue.models)) throw new Error("Unsupported catalogue");
    for (const [id, provider] of Object.entries(catalogue.providers).sort((a, b) => a[1].name.localeCompare(b[1].name))) {
      const option = element("option", provider.name);
      option.value = id;
      $("#provider").append(option);
    }
    $("#model-count").textContent = number.format(catalogue.models.length);
    $("#catalogue-summary").textContent = `models across ${Object.keys(catalogue.providers).length} providers`;
    $("#updated").textContent = `Catalogue updated ${catalogue.updated_on}`;
    render();
    restoreDetail();
  } catch {
    $("#error").hidden = false;
    $("#results").textContent = "Catalogue unavailable";
    $("#catalogue-summary").textContent = "Catalogue unavailable";
  }
}

$("#filters").addEventListener("submit", (event) => event.preventDefault());
$("#filters").addEventListener("input", () => { if (catalogue) render(); });
$("#retired").addEventListener("change", () => { if (catalogue) render(); });
$("#reset").addEventListener("click", () => { $("#filters").reset(); $("#retired").checked = false; render(); });
$("#close").addEventListener("click", () => $("#details").close());
$("#details").addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
window.addEventListener("hashchange", () => { if (catalogue) restoreDetail(); });
start();
