/* Global Macro Desk - static site on GitHub Pages, data in Supabase (docs gm_* and table gm_ideas).
   Tabs (hash routes): #/macro  #/flows  #/crypto  #/commod  #/us  #/record  #/readme
   Without Supabase settings in config.js it runs in preview mode on ./sample. */
"use strict";

const CFG = window.DESK_CONFIG || {};
const LIVE = Boolean(CFG.supabaseUrl && CFG.supabaseAnonKey && window.supabase);
const sb = LIVE ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey, {
  auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true, autoRefreshToken: true },
}) : null;

const state = { view: "swing", newsTag: "all", recTab: "all", recView: "all", sort: {} };
let refreshTimer = null;
try { const v = localStorage.getItem("gm-view"); if (v === "swing" || v === "positional") state.view = v; } catch (e) { /* off */ }

// ------------------------------------------------------------------ helpers
function h(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}
const SVGNS = "http://www.w3.org/2000/svg";
function s(tag, attrs, ...kids) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) node.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid != null) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return node;
}
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const isNum = (v) => typeof v === "number" && isFinite(v);
const fmt = (v, d = 2) => (isNum(v) ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "–");
const fmt0 = (v) => fmt(v, 0);
const pct = (v, d = 1, signed = true) => (isNum(v) ? `${signed && v > 0 ? "+" : ""}${v.toFixed(d)}%` : "–");
const sign = (v) => (isNum(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "muted");
function px(v) {
  if (!isNum(v)) return "–";
  const a = Math.abs(v);
  const d = a >= 1000 ? 2 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8;
  return v.toLocaleString("en-US", { minimumFractionDigits: a >= 10000 ? 0 : Math.min(d, 2), maximumFractionDigits: a >= 10000 ? 0 : d });
}
function big(v) {
  if (!isNum(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${fmt0(v)}`;
}
function when(ts) {
  if (!ts) return "–";
  const d = new Date(String(ts).replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? "" : "Z"));
  if (isNaN(d)) return ts;
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}
function ago(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "";
  const m = Math.round((Date.now() - d) / 60000);
  return m < 60 ? `${m} min ago` : m < 48 * 60 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
}
function sideTag(side) {
  const k = side === "Long" ? "long" : side === "Short" ? "short" : "none";
  return h("span", { class: `side ${k}` }, h("i"), side || "–");
}
function stat(k, v, d, cls) {
  return h("div", { class: "stat" }, h("div", { class: "k" }, k), h("div", { class: `v ${cls || ""}` }, v), d ? h("div", { class: "d" }, d) : null);
}
function meterBar(v, max = 100) {
  const w = isNum(v) ? Math.max(0, Math.min(100, (v / max) * 100)) : 0;
  return h("span", { class: "meter" }, h("span", { class: "bar" }, h("b", { style: `width:${w}%` })), h("em", null, isNum(v) ? Math.round(v) : "–"));
}
function render(node, ...kids) { node.replaceChildren(...kids.flat().filter((k) => k != null && k !== false)); }
function store(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* off */ } }
function pageHead(title, sub, updated) {
  return h("div", { class: "page-head" }, h("h1", null, title), sub ? h("p", null, sub) : null,
    updated ? h("p", { class: `updated ${Date.now() - new Date(updated) > 3 * 3600e3 ? "stale" : ""}` }, `Updated ${when(updated)} IST (${ago(updated)})`) : null);
}
function section(title, sub, ...kids) {
  return h("section", null, h("div", { class: "section-head" }, h("h2", null, title), sub ? h("p", null, sub) : null), ...kids);
}
const panel = (...kids) => h("div", { class: "panel" }, ...kids);
const scroll = (t) => h("div", { class: "table-scroll" }, t);
function trendTag(t) {
  const m = { up: ["pos", "Up"], down: ["neg", "Down"], sideways: ["muted", "Sideways"], mixed: ["muted", "Mixed"], flat: ["muted", "Flat"] }[t] || ["muted", t || "–"];
  return h("span", { class: `tag ${m[0]}` }, m[1]);
}
function tvLink(tv, interval = "D", label) {
  if (!tv) return label || null;
  return h("a", { class: "tvlink", href: `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tv)}&interval=${interval}`,
    target: "_blank", rel: "noopener", title: `Open ${tv} on TradingView` }, label || "Chart ↗");
}
function seg(key, cur, opts, onPick) {
  return h("div", { class: "seg", role: "group" }, opts.map(([v, l]) =>
    h("button", { type: "button", "aria-pressed": String(cur === v), onclick: () => { state[key] = v; if (onPick) onPick(v); route(); } }, l)));
}
function viewSeg() {
  return seg("view", state.view, [["swing", "Swing (days–weeks)"], ["positional", "Positional (weeks–months)"]], (v) => store("gm-view", v));
}

// score -100..+100 on a 5-zone scale
function gscale(v, ends = ["Risk-off", "Neutral", "Risk-on"]) {
  const pos = isNum(v) ? Math.max(0, Math.min(100, (v + 100) / 2)) : 50;
  return h("div", { class: "gscale" }, h("div", { class: "track" }, Array.from({ length: 5 }, () => h("i"))),
    isNum(v) ? h("div", { class: "marker", style: `left:${pos}%` }) : null,
    h("div", { class: "ends" }, ends.map((e) => h("span", null, e))));
}
// -1..+1 bar centred on 0
function effBar(v) {
  const w = isNum(v) ? Math.min(50, Math.abs(v) * 50) : 0;
  const left = isNum(v) && v < 0 ? 50 - w : 50;
  return h("span", { class: "effbar", title: isNum(v) ? v.toFixed(2) : "no data" },
    h("span", { class: "track" }, h("i", { class: "mid" }), h("b", { class: isNum(v) && v < 0 ? "neg" : "pos", style: `left:${left}%;width:${w}%` })),
    h("em", { class: sign(v) }, isNum(v) ? `${v > 0 ? "+" : ""}${v.toFixed(2)}` : "–"));
}
function spark(vals, w = 120, ht = 30) {
  const v = (vals || []).filter(isNum);
  if (v.length < 2) return h("span", { class: "muted" }, "");
  const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${ht - 2 - ((x - lo) / r) * (ht - 4)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return s("svg", { class: "spark", viewBox: `0 0 ${w} ${ht}`, width: w, height: ht, "aria-hidden": "true" },
    s("polyline", { points: pts, fill: "none", stroke: up ? css("--up") : css("--down"), "stroke-width": 1.5 }));
}
function lineChart(series, labels, { height = 180, min = null, max = null, zero = false } = {}) {
  const W = 640, H = height, L = 34, R = 8, T = 10, B = 22;
  const all = series.flatMap((x) => x.values.filter(isNum));
  if (all.length < 2) return h("p", { class: "empty" }, "History builds up from the first days of running.");
  const lo = min ?? Math.min(...all), hi = max ?? Math.max(...all), r = hi - lo || 1;
  const n = labels.length;
  const X = (i) => L + (n > 1 ? (i / (n - 1)) * (W - L - R) : 0);
  const Y = (v) => T + (1 - (v - lo) / r) * (H - T - B);
  const g = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "lchart", role: "img" });
  [lo, (lo + hi) / 2, hi].forEach((t) => {
    g.append(s("line", { x1: L, x2: W - R, y1: Y(t), y2: Y(t), stroke: css("--grid") }),
      s("text", { x: L - 4, y: Y(t) + 4, "text-anchor": "end", class: "axis-text" }, Math.round(t)));
  });
  if (zero && lo < 0 && hi > 0) g.append(s("line", { x1: L, x2: W - R, y1: Y(0), y2: Y(0), stroke: css("--axis"), "stroke-dasharray": "3 3" }));
  [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => labels[i] && g.append(s("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle", class: "axis-text" }, labels[i].slice(5))));
  series.forEach((sr, k) => {
    const pts = sr.values.map((v, i) => (isNum(v) ? `${X(i)},${Y(v)}` : null)).filter(Boolean).join(" ");
    g.append(s("polyline", { points: pts, fill: "none", stroke: sr.color || css(`--s${(k % 3) + 1}`), "stroke-width": 2 }));
  });
  return h("div", null, g, h("div", { class: "legend" }, series.map((sr, k) => h("span", null, h("i", { class: "line", style: `background:${sr.color || css(`--s${(k % 3) + 1}`)}` }), sr.name))));
}

// sortable table: cols = [{k, label, l (left), fmt(row) -> node/text, sort(row) -> value}]
function table(id, cols, rows, opts = {}) {
  const st = state.sort[id] || opts.sort || {};
  const sorted = rows.slice();
  if (st.k) {
    const c = cols.find((x) => x.k === st.k);
    const val = (r) => (c && c.sort ? c.sort(r) : r[st.k]);
    sorted.sort((a, b) => {
      const x = val(a), y = val(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * (st.dir === "asc" ? 1 : -1);
    });
  }
  const thead = h("thead", null, h("tr", null, cols.map((c) => {
    const on = st.k === c.k;
    return h("th", { class: c.l ? "l" : null, "aria-sort": on ? (st.dir === "asc" ? "ascending" : "descending") : null },
      c.nosort ? c.label : h("button", { type: "button", onclick: () => { state.sort[id] = { k: c.k, dir: on && st.dir === "desc" ? "asc" : "desc" }; route(); } }, c.label));
  })));
  const tbody = h("tbody", null, sorted.slice(0, opts.limit || 500).map((r) => h("tr", { style: "cursor:default" },
    cols.map((c) => { const v = c.fmt ? c.fmt(r) : r[c.k]; return h("td", { class: [c.l ? "l" : "", c.cls ? c.cls(r) : ""].join(" ").trim() || null }, v == null ? "–" : v); }))));
  return scroll(h("table", { class: opts.cls || null }, thead, tbody));
}

// ------------------------------------------------------------------ data
const cache = {};
async function doc(key) {
  if (LIVE) {
    const { data, error } = await sb.from("docs").select("data,updated_at").eq("key", key).maybeSingle();
    if (error) throw new Error(error.message);
    return data ? data.data : null;
  }
  if (cache[key] !== undefined) return cache[key];
  const r = await fetch(`sample/${key}.json`, { cache: "no-cache" });
  cache[key] = r.ok ? await r.json() : null;
  return cache[key];
}
async function loadIdeas() {
  if (LIVE) {
    const { data, error } = await sb.from("gm_ideas").select("*").order("signal_ts", { ascending: false }).limit(5000);
    if (error) throw new Error(/gm_ideas|does not exist|schema cache/i.test(error.message)
      ? "the track record table is not set up yet (run supabase/001_global_macro_desk.sql in Supabase)" : error.message);
    return data;
  }
  const r = await fetch("sample/gm_ideas.json", { cache: "no-cache" });
  return r.ok ? r.json() : [];
}
function missing(app, what) {
  render(app, h("p", { class: "empty" }, `No ${what} yet. It appears after the first scheduled run (hourly; the US scan runs after the US close).`));
}
async function problemsBanner(job) {
  const st = await doc("gm_status").catch(() => null);
  const p = ((st || {})[job] || {}).problems || [];
  if (!p.length) return null;
  return h("details", { class: "run" }, h("summary", null, `${p.length} data source problem${p.length > 1 ? "s" : ""} in the last run`),
    h("div", { class: "panel" }, h("ul", { class: "warns" }, p.map((x) => h("li", null, x)))));
}

// ------------------------------------------------------------------ idea card (all tabs)
const PART_LABEL = { trend: "Trend", momentum: "Momentum", setup: "Setup", volume: "Volume", macro: "Macro fit" };
const PART_MAX = { trend: 25, momentum: 20, setup: 25, volume: 10, macro: 20 };
function ideaCard(x, rank, interval) {
  return h("div", { class: `idea ${rank === 1 ? "top" : ""}` },
    h("h3", null, h("span", null, h("span", { class: "rank" }, `#${rank}`), " ", x.symbol, " ", h("small", null, x.name && x.name !== x.symbol ? x.name : "")),
      h("span", null, sideTag(x.side))),
    h("div", { class: "meta" }, `${x.setup_name} · ${x.tf === "4h" ? "4-hour" : "daily"} candle ${when(x.candle)}${x.sector ? ` · ${x.sector}` : ""} · score `, h("b", null, x.score), "/100",
      x.logged ? null : h("span", { class: "flag" }, "watch only")),
    h("div", { class: "lv" },
      h("div", null, h("span", null, "Entry (close)"), h("b", null, px(x.entry))),
      h("div", null, h("span", null, "Stop"), h("b", { class: "neg" }, px(x.stop)), h("span", null, `risk ${x.risk_pct}%`)),
      h("div", null, h("span", null, `Target 1:${x.rr}`), h("b", { class: "pos" }, px(x.target)), h("span", null, `exit by ${x.max_days} days`))),
    h("div", { class: "parts" }, Object.keys(PART_MAX).map((k) => h("div", null, h("span", null, PART_LABEL[k]),
      h("span", { class: "bar" }, h("b", { style: `width:${Math.max(0, Math.min(100, ((x.parts || {})[k] || 0) / PART_MAX[k] * 100))}%` })),
      h("em", null, `${Math.round((x.parts || {})[k] || 0)}/${PART_MAX[k]}`)))),
    h("ul", { class: "reasons" }, (x.reasons || []).map((r) => h("li", null, r))),
    (x.warns || []).length ? h("ul", { class: "warns" }, x.warns.map((w) => h("li", null, w))) : null,
    h("div", { class: "meta" }, `Trend ${x.trend}, RSI ${x.rsi}`, (x.parts || {}).vol_ratio ? `, volume ${x.parts.vol_ratio}× average` : "", " · ", tvLink(x.tv, interval || (x.tf === "4h" ? "240" : "D"))));
}
function ideasBlock(v, interval, emptyText) {
  const ideas = (v && v.ideas) || [];
  if (!ideas.length) return h("p", { class: "empty" }, emptyText || "No setups on the latest completed candles. That is normal: the rules wait for clean breakouts and pullbacks.");
  return h("div", { class: "ideas" }, ideas.map((x, i) => ideaCard(x, i + 1, interval)));
}

// ------------------------------------------------------------------ tab: global macro
const QGROUPS = [
  ["United States", ["spx", "ndx", "dji", "rut", "vix"]],
  ["India", ["nifty", "bnf", "ivix", "usdinr"]],
  ["Rates and dollar", ["us10y", "us2y", "us5y", "us30y", "us3m", "dxy", "tlt", "hyg", "ief"]],
  ["Commodities and crypto", ["gold", "silver", "copper", "brent", "wti", "btc", "eth"]],
];
function quoteCard(k, q) {
  const y = q.is_yield;
  const val = y ? `${fmt(q.last, 2)}%` : q.unit === "₹" ? `₹${fmt(q.last, 2)}` : px(q.last);
  const ch = (v) => (y ? (isNum(v) ? `${v > 0 ? "+" : ""}${Math.round(v * 100)} bp` : "–") : pct(v, 1));
  return h("div", { class: "qcard" }, h("div", { class: "k" }, q.label), h("div", { class: "v" }, val),
    h("div", { class: "d" }, h("span", { class: sign(q.d1) }, `1d ${ch(q.d1)}`), " · ", h("span", { class: sign(q.m1) }, `1m ${ch(q.m1)}`)),
    spark(q.spark, 150, 28));
}
function partsTable(parts) {
  return scroll(h("table", { class: "factors" },
    h("thead", null, h("tr", null, ["Part", "Now", "Score (−1..+1)", "Weight", "Why it matters"].map((c, i) => h("th", { class: i === 0 || i === 1 || i === 4 ? "l" : null }, c)))),
    h("tbody", null, parts.map((p) => h("tr", { style: "cursor:default" }, h("td", { class: "l name" }, p.label), h("td", { class: "l" }, p.value),
      h("td", null, effBar(p.score)), h("td", null, p.score == null ? "–" : p.weight), h("td", { class: "l muted" }, p.why))))));
}
async function viewMacro(app) {
  const d = await doc("gm_macro");
  if (!d) return missing(app, "macro data");
  const nw = (await doc("gm_news")) || { items: [] };
  const q = d.quotes || {}, f = d.fred || {}, dv = d.derived || {};
  const scoreCard = (name, x, sub) => h("div", { class: "panel regime" }, h("div", { class: "k" }, name),
    h("div", { class: "zone" }, `${x.regime} `, h("span", { class: sign(x.score) }, isNum(x.score) ? `(${x.score > 0 ? "+" : ""}${x.score})` : "")),
    gscale(x.score), h("p", { class: "note" }, sub));
  const fredRows = ["DGS10", "DGS2", "T10Y2Y", "DFII10", "T10YIE", "DFEDTARU", "DFF", "BAMLH0A0HYM2", "UNRATE"].filter((k) => f[k]).map((k) => ({ k, ...f[k] }));
  const extra = [
    dv.cpi_yoy != null && ["US CPI inflation (a year)", `${dv.cpi_yoy}%`, `${dv.cpi_yoy_3m_ago}% three months ago`],
    dv.core_pce_yoy != null && ["US core PCE (Fed's gauge)", `${dv.core_pce_yoy}%`, `${dv.core_pce_3m_ago}% three months ago`],
    dv.two_minus_ff != null && [dv.two_minus_ff_proxy ? "2Y yield minus 3-month bill" : "2Y yield minus Fed funds", `${dv.two_minus_ff > 0 ? "+" : ""}${dv.two_minus_ff} pp`, dv.two_minus_ff < -0.25 ? "market expects cuts" : dv.two_minus_ff > 0.25 ? "market expects hikes" : "no big change priced"],
    dv.walcl_tn != null && ["Fed balance sheet", `$${dv.walcl_tn} tn`, `${dv.walcl_3m_pct > 0 ? "+" : ""}${dv.walcl_3m_pct}% in 3 months`],
    dv.au_ag != null && ["Gold / silver ratio", fmt(dv.au_ag, 1), "ounces of silver per ounce of gold"],
  ].filter(Boolean);
  const tags = nw.tag_names || {};
  const items = (nw.items || []).filter((it) => state.newsTag === "all" || (it.tags || []).includes(state.newsTag));
  const tone = (v) => h("span", { class: `tone ${v > 0.15 ? "pos" : v < -0.15 ? "neg" : "muted"}` }, v > 0.15 ? "positive" : v < -0.15 ? "negative" : "neutral");
  const sent = d.news_sentiment || {};
  const hist = d.history || [];
  render(app,
    pageHead("Global macro", "Risk appetite from global and Indian market data, the Fed and the news. Scores run from −100 (risk-off) to +100 (risk-on).", d.updated),
    await problemsBanner("hourly"),
    h("div", { class: "grid3" },
      scoreCard("Global risk appetite", d.global, "VIX, credit spreads, S&P 500 trend, dollar, US yields, yield curve, copper/gold, news"),
      scoreCard("India risk appetite", d.india, "Nifty trend, India VIX, rupee, crude, FII flows, India news"),
      scoreCard("Overall", d.overall, "Average of the two")),
    section("What it means", "Plain-words rules on what moved in the last month and how it usually affects each asset class",
      panel(h("ul", { class: "interp" }, (d.interpret || []).map((x) => h("li", { class: x.tone > 0 ? "pos" : x.tone < 0 ? "neg" : "" }, x.text))))),
    QGROUPS.map(([g, keys]) => section(g, null, h("div", { class: "qgrid" }, keys.filter((k) => q[k]).map((k) => quoteCard(k, q[k]))))),
    section("Fed, rates and inflation", "From FRED (St. Louis Fed); daily series lag one day, monthly ones a few weeks",
      h("div", { class: "grid2" },
        panel(scroll(h("table", null, h("thead", null, h("tr", null, ["Series", "Now", "1m", "3m", "1y", "As of"].map((c, i) => h("th", { class: i === 0 ? "l" : null }, c)))),
          h("tbody", null, fredRows.map((r) => h("tr", { style: "cursor:default" }, h("td", { class: "l name" }, r.label), h("td", null, `${fmt(r.last, 2)}%`),
            ["m1", "m3", "y1"].map((k) => h("td", { class: sign(-r[k]) }, isNum(r[k]) ? `${r[k] > 0 ? "+" : ""}${Math.round(r[k] * 100)} bp` : "–")), h("td", null, r.date))))))),
        panel(h("table", { class: "kv" }, h("tbody", null, extra.map(([a, b, c]) => h("tr", { style: "cursor:default" }, h("td", { class: "l name" }, a), h("td", null, b), h("td", { class: "l muted" }, c))))),
          h("h3", { class: "mini" }, "Next central bank decisions"),
          h("table", { class: "kv" }, h("tbody", null, (d.calendar || []).map((c) => h("tr", { style: "cursor:default" }, h("td", { class: "l name" }, c.event), h("td", null, c.date), h("td", { class: "l muted" }, `in ${c.days} days`)))))))),
    section("Global score parts", null, panel(partsTable(d.global.parts || []))),
    section("India score parts", d.fii && d.fii.last_date ? `FII cash net on ${d.fii.last_date}: ₹${fmt0((d.fii.last || {}).fii)} Cr, DII ₹${fmt0((d.fii.last || {}).dii)} Cr` : null, panel(partsTable(d.india.parts || []))),
    section("Score history", "Daily value (last run of each day)", panel(lineChart([
      { name: "Global", values: hist.map((x) => x.global) }, { name: "India", values: hist.map((x) => x.india) }, { name: "Overall", values: hist.map((x) => x.overall) }],
      hist.map((x) => x.date), { min: -100, max: 100, zero: true }))),
    section("News", `${nw.count || 0} headlines from ${nw.feeds || 0} free feeds, last 4 days. Tone = keyword rules, so read the headline yourself.`,
      h("div", { class: "filters" }, seg("newsTag", state.newsTag, [["all", "All"], ...Object.entries(tags).map(([k, v]) => [k, `${v}${sent[k] && isNum(sent[k].score) ? ` ${sent[k].score > 0 ? "+" : ""}${Math.round(sent[k].score)}` : ""}`])])),
      panel(h("ul", { class: "news" }, items.slice(0, 80).map((it) => h("li", null,
        h("a", { href: it.link, target: "_blank", rel: "noopener" }, it.title),
        h("div", { class: "meta" }, tone(Object.keys(it.asset || {}).length && state.newsTag !== "all" && it.asset[state.newsTag] != null ? it.asset[state.newsTag] : it.risk),
          ` ${it.source} · ${ago(it.ts)} · `, (it.tags || []).map((t) => tags[t] || t).join(", ")))))))
  );
}

// ------------------------------------------------------------------ tab: money flow
async function viewFlows(app) {
  const d = await doc("gm_flows");
  if (!d) return missing(app, "money flow data");
  const A = d.assets || [];
  const flowTag = (f) => (f === "in" ? h("span", { class: "tag pos" }, "Money in") : f === "out" ? h("span", { class: "tag neg" }, "Money out") : f === "flat" ? h("span", { class: "tag muted" }, "Balanced") : "–");
  const stance = (s2) => h("span", { class: `tag ${s2 === "Overweight" ? "pos" : s2 === "Underweight" ? "neg" : "muted"}` }, s2);
  const hist = d.history || [];
  const keys = A.map((a) => a.key);
  render(app,
    pageHead("Money flow across asset classes", "Where money is moving, seen by an Indian investor (all returns in rupees). Score 0–100 = 55% momentum and volume-based money flow + 45% macro fit.", d.updated),
    h("div", { class: "stats" },
      stat("Global", d.regime.global || "–", isNum(d.scores.global) ? `${d.scores.global > 0 ? "+" : ""}${d.scores.global}` : null, sign(d.scores.global)),
      stat("India", d.regime.india || "–", isNum(d.scores.india) ? `${d.scores.india > 0 ? "+" : ""}${d.scores.india}` : null, sign(d.scores.india)),
      stat("Leading asset", A[0] ? A[0].label : "–", A[0] ? `score ${A[0].score}` : null),
      stat("Weakest asset", A.length ? A[A.length - 1].label : "–", A.length ? `score ${A[A.length - 1].score}` : null)),
    section("Asset classes ranked", "Click a column to sort. Suggested mix = your base mix tilted by the score (at most ±50% of each base weight).",
      panel(table("flows", [
        { k: "label", label: "Asset", l: true, fmt: (r) => h("span", { class: "name" }, r.label, h("small", null, r.flow_symbol ? `flow: ${r.flow_symbol}` : r.note || "")) },
        { k: "score", label: "Score", fmt: (r) => meterBar(r.score) },
        { k: "stance", label: "Stance", fmt: (r) => stance(r.stance) },
        { k: "chg7", label: "vs 7d ago", fmt: (r) => h("span", { class: sign(r.chg7) }, isNum(r.chg7) ? `${r.chg7 > 0 ? "+" : ""}${r.chg7}` : "–") },
        { k: "mom", label: "Momentum" }, { k: "fit", label: "Macro fit" },
        { k: "cmf", label: "Money flow", fmt: (r) => flowTag(r.flow), sort: (r) => r.cmf },
        { k: "r1m", label: "1m ₹", fmt: (r) => h("span", { class: sign(r.r1m) }, pct(r.r1m)) },
        { k: "r3m", label: "3m ₹", fmt: (r) => h("span", { class: sign(r.r3m) }, pct(r.r3m)) },
        { k: "r6m", label: "6m ₹", fmt: (r) => h("span", { class: sign(r.r6m) }, pct(r.r6m)) },
        { k: "r1y", label: "1y ₹", fmt: (r) => h("span", { class: sign(r.r1y) }, pct(r.r1y)) },
        { k: "trend", label: "Trend", fmt: (r) => trendTag(r.trend) },
        { k: "vol", label: "Volatility", fmt: (r) => (isNum(r.vol) ? `${r.vol}%` : "–") },
        { k: "base", label: "Base mix", fmt: (r) => `${r.base}%` },
        { k: "tilt", label: "Suggested", fmt: (r) => h("b", { class: r.tilt > r.base + 0.5 ? "pos" : r.tilt < r.base - 0.5 ? "neg" : "" }, `${r.tilt}%`) },
      ], A))),
    section("Why each score", "Macro fit: how today's backdrop usually affects each asset (+ helps, − hurts)",
      h("div", { class: "ideas" }, A.map((a) => h("div", { class: "idea" },
        h("h3", null, a.label, h("small", null, `score ${a.score} · ${a.stance}`)),
        h("div", { class: "lv" }, h("div", null, h("span", null, "Momentum"), h("b", null, a.mom)), h("div", null, h("span", null, "Macro fit"), h("b", null, a.fit)),
          h("div", null, h("span", null, "Money flow (CMF)"), h("b", { class: sign(a.cmf) }, isNum(a.cmf) ? a.cmf.toFixed(2) : "–"))),
        h("table", { class: "kv" }, h("tbody", null, (a.fit_parts || []).map((p) => h("tr", { style: "cursor:default" }, h("td", { class: "l" }, p.factor, p.inverse ? h("small", { class: "muted" }, " (works against)") : ""), h("td", null, effBar(p.effect)))))))))),
    section("Score history", "Daily asset scores", panel(lineChart(keys.slice(0, 7).map((k, i) => ({
      name: (A.find((a) => a.key === k) || {}).label || k, values: hist.map((x) => x[k]),
      color: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a63d2", "#d03b3b", "#7a8590"][i] })), hist.map((x) => x.date), { min: 0, max: 100 }))),
    h("p", { class: "note" }, `Bank FD uses a fixed ${d.fd_rate}% rate and India CPI ${d.india_cpi}% (edit FD_RATE and INDIA_CPI in gmd/config.py when they change). Money flow = Chaikin money flow of a traded ETF (20 days): above +0.08 buyers in control, below −0.08 sellers. Not advice: a model view to compare with your own.`));
}

// ------------------------------------------------------------------ tab: crypto
async function viewCrypto(app) {
  const d = await doc("gm_crypto");
  if (!d) return missing(app, "crypto data");
  const m = d.market || {}, b = m.btc || {};
  const fng = m.fng || {};
  const domChg = isNum(m.btc_dom) && isNum(m.btc_dom_7d_ago) ? m.btc_dom - m.btc_dom_7d_ago : null;
  const v = (d.views || {})[state.view];
  render(app,
    pageHead("Crypto", "Market overview, coins ranked by price action, and long ideas from the rules (spot investing, no shorts).", d.updated),
    await problemsBanner("hourly"),
    h("div", { class: "stats" },
      stat("Total market cap", big(m.total_mcap), isNum(m.mcap_chg24) ? `${pct(m.mcap_chg24)} in 24 h` : null, sign(m.mcap_chg24)),
      stat("Bitcoin", `$${px(b.price)}`, `${pct(b.d1)} 24 h · ${pct(b.m1)} 30 d`, sign(b.d1)),
      stat("BTC dominance", isNum(m.btc_dom) ? `${m.btc_dom.toFixed(1)}%` : "–", isNum(domChg) ? `${domChg > 0 ? "+" : ""}${domChg.toFixed(1)} pp in 7 days` : "ETH " + (isNum(m.eth_dom) ? `${m.eth_dom.toFixed(1)}%` : "–")),
      stat("Fear & Greed", isNum(fng.value) ? `${fng.value} ${fng.label}` : "–", isNum(m.fng_avg7) ? `7-day average ${m.fng_avg7}` : null),
      stat("Altcoins beating BTC", isNum(m.altseason) ? `${m.altseason}%` : "–", "over 90 days (≥75% = alt season)"),
      stat("Macro fit", isNum(m.fit) ? `${m.fit}/100` : "–", "from the Money flow tab")),
    section(`Market: ${(m.regime || {}).label || "–"}`, null, panel(h("ul", { class: "interp" }, ((m.regime || {}).why || []).map((w) => h("li", null, w))),
      (m.fng_hist || []).length > 5 ? h("div", null, h("h3", { class: "mini" }, "Fear & Greed, last 60 days"), lineChart([{ name: "Fear & Greed", values: m.fng_hist.map((x) => x.value) }], m.fng_hist.map((x) => x.date), { height: 140, min: 0, max: 100 })) : null)),
    section("Trade ideas", state.view === "swing" ? "4-hour candles; higher timeframe = daily. Target 1:2, exit after 14 days." : "Daily candles; higher timeframe = weekly. Target 1:3, exit after 90 days.",
      h("div", { class: "filters" }, viewSeg()), ideasBlock(v, state.view === "swing" ? "240" : "D")),
    section("Trending coins", "Top coins by market cap (stablecoins and wrapped tokens left out), ranked by trend score: 7-day and 30-day strength vs the rest, trend, volume surge, CoinGecko trending list",
      panel(table("coins", [
        { k: "sym", label: "Coin", l: true, fmt: (r) => h("span", { class: "name" }, r.sym, " ", tvLink(r.tv, "D", "↗"), h("small", null, `${r.name}${r.rank ? ` · #${r.rank}` : ""}`), r.cg_trending ? h("span", { class: "flag fno" }, "Trending") : null) },
        { k: "trend_score", label: "Trend score", fmt: (r) => meterBar(r.trend_score) },
        { k: "price", label: "Price $", fmt: (r) => px(r.price) },
        { k: "d1", label: "24 h", fmt: (r) => h("span", { class: sign(r.d1) }, pct(r.d1)) },
        { k: "w1", label: "7 d", fmt: (r) => h("span", { class: sign(r.w1) }, pct(r.w1)) },
        { k: "m1", label: "30 d", fmt: (r) => h("span", { class: sign(r.m1) }, pct(r.m1)) },
        { k: "vs_btc_90d", label: "vs BTC 90 d", fmt: (r) => h("span", { class: sign(r.vs_btc_90d) }, pct(r.vs_btc_90d)) },
        { k: "trend_d", label: "Daily", fmt: (r) => trendTag(r.trend_d) },
        { k: "trend_w", label: "Weekly", fmt: (r) => trendTag(r.trend_w) },
        { k: "rsi", label: "RSI" },
        { k: "ath_chg", label: "From ATH", fmt: (r) => pct(r.ath_chg, 0) },
        { k: "vol_surge", label: "Volume vs 30 d", fmt: (r) => (isNum(r.vol_surge) ? `${r.vol_surge}×` : "–") },
        { k: "mcap", label: "Market cap", fmt: (r) => big(r.mcap) },
      ], d.coins || [], { sort: { k: "trend_score", dir: "desc" } }))));
}

// ------------------------------------------------------------------ tab: commodities
async function viewCommod(app) {
  const d = await doc("gm_commod");
  if (!d) return missing(app, "commodity data");
  const M = d.metals || {}, r = d.ratios || {}, c = d.context || {};
  const v = (d.views || {})[state.view];
  const card = (k) => {
    const x = M[k];
    if (!x) return null;
    const rngPos = isNum(x.hi52) && x.hi52 > x.lo52 ? ((x.price - x.lo52) / (x.hi52 - x.lo52)) * 100 : null;
    return h("div", { class: "panel metal" },
      h("h3", null, x.label, " ", h("small", null, `${x.symbol} · COMEX, USD`), " ", tvLink(x.tv, "D")),
      h("div", { class: "zone" }, `$${px(x.price)} `, h("span", { class: sign(x.d1) }, pct(x.d1)), " ", h("span", { class: `tag ${x.bias === "Bullish" ? "pos" : x.bias === "Bearish" ? "neg" : "muted"}` }, `${x.bias} ${x.direction > 0 ? "+" : ""}${x.direction}`)),
      gscale(x.direction, ["Bearish", "Neutral", "Bullish"]),
      h("div", { class: "lv" }, h("div", null, h("span", null, "1 week"), h("b", { class: sign(x.w1) }, pct(x.w1))), h("div", null, h("span", null, "1 month"), h("b", { class: sign(x.m1) }, pct(x.m1))), h("div", null, h("span", null, "1 year"), h("b", { class: sign(x.y1) }, pct(x.y1)))),
      h("p", { class: "note" }, "Trend: weekly ", trendTag(x.trend_w), " daily ", trendTag(x.trend_d), " 4-hour ", trendTag(x.trend_4h), ` · RSI ${x.rsi_d} · daily range ${x.atr_pct}%`),
      h("div", { class: "range" }, h("span", null, `52w low ${px(x.lo52)}`), h("span", { class: "bar" }, isNum(rngPos) ? h("b", { style: `left:${rngPos}%` }) : null), h("span", null, `high ${px(x.hi52)}`)),
      h("table", { class: "kv" }, h("tbody", null, (x.drivers || []).map((p) => h("tr", { style: "cursor:default" }, h("td", { class: "l" }, p.driver), h("td", null, effBar(p.effect)))))),
      spark(x.spark, 300, 40));
  };
  render(app,
    pageHead("Commodities", "Gold, silver and copper futures (COMEX, USD). Direction score −100..+100 = 40% daily trend + 15% 4-hour trend + 45% macro drivers.", d.updated),
    await problemsBanner("hourly"),
    h("div", { class: "grid3" }, ["gold", "silver", "copper"].map(card)),
    section("Backdrop", null, h("div", { class: "stats" },
      stat("Gold / silver ratio", r.gold_silver ? fmt(r.gold_silver.now, 1) : "–", r.gold_silver ? `1-year range ${r.gold_silver.lo}–${r.gold_silver.hi} (${r.gold_silver.pctile}th percentile; high = silver cheap)` : null),
      stat("Copper / gold", r.copper_gold ? pct(r.copper_gold.m1) : "–", r.copper_gold ? `1 month (3 months ${pct(r.copper_gold.m3)}); rising = growth optimism` : null, r.copper_gold ? sign(r.copper_gold.m1) : ""),
      stat("Dollar (DXY)", isNum(c.dxy) ? fmt(c.dxy, 2) : "–", isNum(c.dxy_m1) ? `${pct(c.dxy_m1)} in 1 month` : null, sign(-c.dxy_m1)),
      stat("Real 10Y yield", isNum(c.real10) ? `${fmt(c.real10, 2)}%` : "–", isNum(c.real10_m1) ? `${c.real10_m1 > 0 ? "+" : ""}${Math.round(c.real10_m1 * 100)} bp in 1 month` : null, sign(-c.real10_m1)),
      stat("Global regime", c.regime || "–", isNum(c.vix) ? `US VIX ${fmt(c.vix, 1)}` : null))),
    section("Trading ideas", state.view === "swing" ? "4-hour candles, long and short; higher timeframe = daily. Target 1:2, exit after 14 days." : "Daily candles, long and short; higher timeframe = weekly. Target 1:3, exit after 90 days.",
      h("div", { class: "filters" }, viewSeg()), ideasBlock(v, state.view === "swing" ? "240" : "D", "No setup on the latest completed candles for gold, silver or copper. Use the direction score and trends above until one forms.")));
}

// ------------------------------------------------------------------ tab: US equity
async function viewUS(app) {
  const d = await doc("gm_us");
  if (!d) return missing(app, "US equity data");
  const t = d.trend || {}, se = d.sentiment || {}, b = d.breadth || {};
  const v = (d.views || {})[state.view];
  const QC = { Leading: "q-leading", Weakening: "q-weakening", Lagging: "q-lagging", Improving: "q-improving" };
  const secCols = [
    { k: "name", label: "Sector", l: true, fmt: (r) => h("span", { class: "name" }, r.name, h("small", null, r.etf)) },
    { k: "flow_score", label: "Flow score", fmt: (r) => meterBar(r.flow_score) },
    { k: "flow", label: "Money", fmt: (r) => h("span", { class: `tag ${r.flow === "Inflow" ? "pos" : r.flow === "Outflow" ? "neg" : "muted"}` }, r.flow) },
    { k: "quad", label: "Rotation", sort: (r) => (r.rrg || {}).ratio, fmt: (r) => (r.rrg ? h("span", { class: `q ${QC[r.rrg.quadrant]}` }, h("i"), r.rrg.quadrant) : "–") },
    { k: "rs1m", label: "vs S&P 1m", fmt: (r) => h("span", { class: sign(r.rs1m) }, pct(r.rs1m)) },
    { k: "rs3m", label: "vs S&P 3m", fmt: (r) => h("span", { class: sign(r.rs3m) }, pct(r.rs3m)) },
    { k: "w1", label: "1 w", fmt: (r) => h("span", { class: sign(r.w1) }, pct(r.w1)) },
    { k: "m1", label: "1 m", fmt: (r) => h("span", { class: sign(r.m1) }, pct(r.m1)) },
    { k: "cmf", label: "CMF 20d", fmt: (r) => h("span", { class: sign(r.cmf) }, isNum(r.cmf) ? r.cmf.toFixed(2) : "–") },
    { k: "breadth50", label: "Stocks > 50d", fmt: (r) => (isNum(r.breadth50) ? `${r.breadth50}%` : "–") },
  ];
  const idx = (name, x) => (x ? stat(`${name} trend`, `${x.score}/100`, `${x.state} · 3m ${pct(x.m3)} · ${pct(x.from_high)} from high`, x.score >= 60 ? "pos" : x.score < 40 ? "neg" : "") : null);
  render(app,
    pageHead("US equity", `S&P 500 + Nasdaq 100 (${d.scanned} of ${d.universe} stocks passed the price ≥ $10 and $50M a day liquidity filter). Daily candles up to ${d.asof}.`, d.updated),
    await problemsBanner("us"),
    h("div", { class: "grid2" },
      h("div", { class: "panel regime" }, h("div", { class: "k" }, "Sentiment score"),
        h("div", { class: "zone" }, `${se.label || "–"} `, h("span", null, isNum(se.score) ? `${se.score}/100` : "")),
        gscale(isNum(se.score) ? se.score * 2 - 100 : null, ["Extreme fear", "Neutral", "Extreme greed"]),
        partsTable((se.parts || []).map((p) => ({ label: p.label, value: p.value, score: isNum(p.score) ? (p.score - 50) / 50 : null, weight: p.weight, why: "" })))),
      h("div", null, h("div", { class: "stats" }, idx("S&P 500", t.spx), idx("Nasdaq 100", t.ndx), idx("Russell 2000", t.rut)),
        h("div", { class: "stats" },
          stat("Above 50-day avg", isNum(b.above50) ? `${b.above50}%` : "–", "share of stocks"),
          stat("Above 200-day avg", isNum(b.above200) ? `${b.above200}%` : "–"),
          stat("New 52w highs / lows", `${b.new_highs} / ${b.new_lows}`),
          stat("Up / down today", `${b.adv} / ${b.dec}`)))),
    section(`Top ${(v && v.ideas || []).length || 10} ideas`, state.view === "swing" ? "Daily candles; weekly trend as filter. Target 1:2, exit after 14 days. Long only." : "Daily candles with the 50 EMA and momentum leaders; weekly trend as filter. Target 1:3, exit after 90 days. Long only.",
      h("div", { class: "filters" }, viewSeg()), ideasBlock(v, "D"),
      v && (v.more || []).length ? h("details", { class: "run" }, h("summary", null, `${v.more.length} more setups`), panel(table("usmore", [
        { k: "symbol", label: "Stock", l: true, fmt: (r) => h("span", { class: "name" }, r.symbol, " ", tvLink(r.tv, "D", "↗"), h("small", null, `${r.name} · ${r.sector || ""}`)) },
        { k: "setup_name", label: "Setup", l: true }, { k: "score", label: "Score", fmt: (r) => meterBar(r.score) },
        { k: "entry", label: "Entry", fmt: (r) => px(r.entry) }, { k: "stop", label: "Stop", fmt: (r) => px(r.stop) },
        { k: "target", label: "Target", fmt: (r) => px(r.target) }, { k: "risk_pct", label: "Risk", fmt: (r) => `${r.risk_pct}%` },
      ], v.more))) : null),
    section("Sector money flow", "Rotation vs the S&P 500 (RRG-style): Leading → Weakening → Lagging → Improving. Flow score = 40% relative strength + 30% Chaikin money flow + 30% rotation.",
      panel(table("sectors", secCols, (d.sectors || []).filter((x) => !x.style)))),
    section("Style flow", "Growth, small caps, equal-weight and Dow vs the S&P 500", panel(table("style", secCols.map((c) => (c.k === "name" ? { ...c, label: "Style" } : c)).filter((c) => c.k !== "breadth50"), (d.sectors || []).filter((x) => x.style)))),
    section("Momentum leaders", "Top 10% relative strength over 3–6 months and in an uptrend: a watchlist, not entries",
      panel(table("leaders", [
        { k: "symbol", label: "Stock", l: true, fmt: (r) => h("span", { class: "name" }, r.symbol, " ", tvLink(r.symbol, "D", "↗"), h("small", null, `${r.name} · ${r.sector}`)) },
        { k: "rs", label: "RS rank", fmt: (r) => `${Math.round(r.rs * 100)}` }, { k: "price", label: "Price", fmt: (r) => px(r.price) },
        { k: "m1", label: "1 m", fmt: (r) => h("span", { class: sign(r.m1) }, pct(r.m1)) }, { k: "m3", label: "3 m", fmt: (r) => h("span", { class: sign(r.m3) }, pct(r.m3)) },
        { k: "m6", label: "6 m", fmt: (r) => h("span", { class: sign(r.m6) }, pct(r.m6)) }, { k: "from_high", label: "From high", fmt: (r) => pct(r.from_high) },
      ], d.leaders || []))));
}

// ------------------------------------------------------------------ tab: track record
async function viewRecord(app) {
  let rows = [], err = null;
  try { rows = await loadIdeas(); } catch (e) { err = e.message; }
  const shown = rows.filter((r) => (state.recTab === "all" || r.tab === state.recTab) && (state.recView === "all" || r.view === state.recView));
  const done = shown.filter((r) => r.status === "closed" && r.result !== "unclear" && r.net_pct !== null);
  const openN = shown.filter((r) => r.status !== "closed").length;
  const agg = (list) => {
    const n = list.length, w = list.filter((r) => +r.net_pct > 0);
    const gain = w.reduce((a, r) => a + +r.net_pct, 0), loss = list.filter((r) => +r.net_pct <= 0).reduce((a, r) => a + +r.net_pct, 0);
    const rr = list.filter((r) => r.r_mult !== null);
    return { n, win: n ? (w.length / n) * 100 : null, avg: n ? (gain + loss) / n : null, pf: loss < 0 ? gain / Math.abs(loss) : null,
      r: rr.length ? rr.reduce((a, r) => a + +r.r_mult, 0) / rr.length : null };
  };
  const tot = agg(done);
  const TAB = { crypto: "Crypto", commodities: "Commodities", us: "US equity" };
  const SETUP = { BO: "Base breakout", PB: "Trend pullback", ML: "Momentum leader", BD: "Base breakdown", PS: "Rally into resistance (short)" };
  const group = (title, keyFn, labelFn) => {
    const g = {};
    done.forEach((r) => { (g[keyFn(r)] ||= []).push(r); });
    const keys = Object.keys(g).sort((a, b) => g[b].length - g[a].length);
    if (!keys.length) return null;
    return section(title, null, panel(scroll(h("table", null,
      h("thead", null, h("tr", null, ["Group", "Finished", "Win rate", "Avg %", "Avg R", "Profit factor"].map((c, i) => h("th", { class: i === 0 ? "l" : null }, c)))),
      h("tbody", null, keys.map((k) => { const a = agg(g[k]); return h("tr", { class: a.n < 10 ? "few" : null, style: "cursor:default" }, h("td", { class: "l name" }, labelFn(k)), h("td", null, a.n),
        h("td", null, isNum(a.win) ? `${Math.round(a.win)}%` : "–"), h("td", { class: sign(a.avg) }, pct(a.avg, 2)), h("td", { class: sign(a.r) }, isNum(a.r) ? a.r.toFixed(2) : "–"), h("td", null, isNum(a.pf) ? a.pf.toFixed(2) : "–")); }))))));
  };
  const band = (sc) => (sc >= 80 ? "80+" : sc >= 70 ? "70–79" : sc >= 60 ? "60–69" : "50–59");
  const status = (r) => {
    if (r.status === "pending") return h("span", { class: "muted" }, "waiting for the next candle");
    if (r.status === "open") return h("span", null, "open ", h("span", { class: sign(r.last_pct) }, isNum(+r.last_pct) && r.last_pct !== null ? pct(+r.last_pct, 2) : ""));
    return h("span", { class: `res-tag ${r.result}` }, r.result);
  };
  render(app,
    pageHead("Track record", "Every idea scoring 50 or more is logged once, filled at the open of the next candle (no look-ahead) and closed at its stop, target or time exit on the same timeframe."),
    err ? h("div", { class: "banner" }, `Could not load: ${err}`) : null,
    h("div", { class: "filters" }, seg("recTab", state.recTab, [["all", "All"], ["crypto", "Crypto"], ["commodities", "Commodities"], ["us", "US equity"]]),
      seg("recView", state.recView, [["all", "Both views"], ["swing", "Swing"], ["positional", "Positional"]])),
    h("div", { class: "stats" },
      stat("Finished", tot.n, `${openN} open or waiting`), stat("Win rate", isNum(tot.win) ? `${Math.round(tot.win)}%` : "–"),
      stat("Average", pct(tot.avg, 2), "per idea, before costs", sign(tot.avg)), stat("Average R", isNum(tot.r) ? tot.r.toFixed(2) : "–", "result ÷ risk to the stop"),
      stat("Profit factor", isNum(tot.pf) ? tot.pf.toFixed(2) : "–", "gains ÷ losses")),
    h("p", { class: "note" }, "Stop and target are checked on every candle's high and low; a candle that touches both is \"unclear\" and left out of every number. Gaps through a level exit at the open. Small groups (under 10) are greyed: too few to judge."),
    group("By tab and view", (r) => `${r.tab}|${r.view}`, (k) => { const [a, b2] = k.split("|"); return `${TAB[a] || a} · ${b2}`; }),
    group("By setup", (r) => `${r.setup}|${r.side}`, (k) => { const [a, b2] = k.split("|"); return `${SETUP[a] || a} (${b2.toLowerCase()})`; }),
    group("By score", (r) => band(+r.score), (k) => `Score ${k}`),
    section("All logged ideas", null, panel(table("rec", [
      { k: "signal_ts", label: "Signal", l: true, fmt: (r) => when(r.signal_ts) },
      { k: "tab", label: "Tab", l: true, fmt: (r) => `${TAB[r.tab] || r.tab} · ${r.view}` },
      { k: "symbol", label: "Symbol", l: true, fmt: (r) => h("span", { class: "name" }, r.symbol, h("small", null, `${SETUP[r.setup] || r.setup} · ${r.tf}`)) },
      { k: "side", label: "Side", l: true, fmt: (r) => sideTag(r.side) }, { k: "score", label: "Score" },
      { k: "entry", label: "Entry", fmt: (r) => (r.entry ? px(+r.entry) : `${px(+r.planned_entry)}*`) },
      { k: "stop", label: "Stop", fmt: (r) => px(+r.stop) }, { k: "target", label: "Target", fmt: (r) => px(+r.target) },
      { k: "status", label: "Status", l: true, fmt: status },
      { k: "net_pct", label: "Result", fmt: (r) => h("span", { class: sign(+r.net_pct) }, r.net_pct !== null && r.net_pct !== undefined ? pct(+r.net_pct, 2) : "–"), sort: (r) => (r.net_pct === null ? null : +r.net_pct) },
      { k: "r_mult", label: "R", fmt: (r) => (r.r_mult !== null && r.r_mult !== undefined ? (+r.r_mult).toFixed(2) : "–"), sort: (r) => (r.r_mult === null ? null : +r.r_mult) },
      { k: "exit_ts", label: "Closed", l: true, fmt: (r) => (r.exit_ts ? when(r.exit_ts) : "–") },
    ], shown, { limit: 400 }))));
}

// ------------------------------------------------------------------ tab: readme
function viewReadme(app) {
  const li = (...x) => h("li", null, ...x);
  const blk = (title, ...items) => section(title, null, panel(h("ul", { class: "readme-list" }, items)));
  render(app, pageHead("Readme", "How every score and idea is made. All numbers live in gmd/config.py: untested starting values, to be judged in the Track record."),
    blk("Data and timing",
      li("Hourly job (about 7 minutes past every hour, every day): market data and FRED, news, FII flows, Global macro, Money flow, Crypto, Commodities, Track record for crypto and commodities."),
      li("US scan once a day after the US close (about 3:10 am IST, Tuesday–Saturday): S&P 500 + Nasdaq 100, sectors, Top 10 ideas, Track record for US ideas."),
      li("Sources are free and unofficial (Yahoo Finance, FRED, CoinGecko, alternative.me, NSE, RSS feeds). When one fails the run carries on and lists the problem at the top of the tab."),
      li("Only completed candles are used for ideas: the last 4-hour or daily candle still forming is ignored.")),
    blk("Global macro scores (−100 risk-off … +100 risk-on)",
      li("Global: US VIX 20 (below 14 = +1, 14–18 = +0.5, 18–22 = 0, 22–28 = −0.5, above = −1, ±0.25 for falling/rising vs its 20-day average), high-yield credit spread 15, S&P 500 trend 15, dollar index 1-month move 15 (−2.5% = +1), US 10Y 1-month move 10 (−40 bp = +1), yield curve 5, copper/gold 1-month 10, news tone 10."),
      li("India: Nifty trend 25, India VIX 15, rupee 1-month move 15, Brent 1-month move 15, FII cash flows over 5 sessions 15 (±₹15,000 Cr = ±1), India news tone 15."),
      li("Zones: below −60 strong risk-off, −60 to −20 risk-off, −20 to +20 neutral, +20 to +60 risk-on, above +60 strong risk-on. Parts with no data are left out and the rest re-weighted."),
      li("What it means: fixed rules, e.g. DXY ±1.5% in a month, 10Y ±25 bp, curve inverted, 2Y vs Fed funds ±0.4 pp, CPI trend vs 3 months ago, Fed balance sheet ±0.5% in 3 months, crude ±8%, rupee ±1%, FII ±₹5,000 Cr, FOMC/RBI within 7 days.")),
    blk("News tone",
      li("Headlines from 18 free feeds (CNBC, MarketWatch, Yahoo Finance, Fed, Economic Times, Livemint, Moneycontrol, CoinDesk, Cointelegraph, Google News searches), last 4 days, duplicates removed."),
      li("Each headline is tagged (Fed, US, India, bonds, dollar, gold, silver, copper, oil, crypto, macro) and scored −1..+1 by word rules: who moved (\"gold rises\" = good for gold; \"yields jump\" = bad for stocks and bonds) plus good/bad words (rate cut, deal, beat / war, tariff, recession, hawkish), with simple negation (\"no rate cut\")."),
      li("Scores per tag are weighted means (last 24 h ×1, 24–48 h ×0.5, older ×0.25), shrunk towards 0 when there are few headlines. Keyword rules miss sarcasm and context: read the headline.")),
    blk("Money flow (asset classes, INR terms)",
      li("Assets: Indian equity (Nifty; flow from NIFTYBEES), US equity (SPY), US bonds (TLT), bank FDs (fixed rate), gold (COMEX; flow GLD), silver (COMEX; SLV), crypto (Bitcoin). US-dollar assets are converted to rupees every day."),
      li("Momentum 0–100: 50 + 25 × tanh(risk-adjusted return / 6) + 15 for an uptrend (−15 downtrend) + up to ±10 from Chaikin money flow. Risk-adjusted return = (30% 1m + 40% 3m + 30% 6m) ÷ volatility × 10."),
      li("Macro fit 0–100: weighted factors, e.g. gold = falling real yields 30%, weaker dollar 25%, risk-off 15%, gold news 15%, rising inflation 15%; crypto = global risk 30%, Fed liquidity 20%, weaker dollar 20%, falling yields 10%, crypto news 20%."),
      li("Score = 55% momentum + 45% macro fit. 62+ Overweight, below 45 Underweight. Suggested mix = base mix (Indian equity 35, US equity 15, US bonds 5, FD 20, gold 12, silver 5, crypto 8) × (1 + 0.5 × (score − 50) / 50), rescaled to 100%.")),
    blk("Trade ideas (Crypto, Commodities, US equity)",
      li("Swing: 4-hour candles for crypto and commodities, daily for US stocks; target 1:2, exit after 14 days. Positional: daily candles; target 1:3, exit after 90 days."),
      li("Base breakout: a sideways base (swing 8–30 candles within 3× ATR; positional 15–60 within 4.5× ATR; first-to-last close within half the range), then a candle with body ≥ 50% closing 0.1 ATR beyond the base and the 50 EMA, previous close still inside. Stop beyond the base (or the breakout candle if the base is deeper than the stop limit)."),
      li("Trend pullback: uptrend (4 of 5: price over 20 EMA, over 50 EMA, 20 over 50, 50 over 200, 50 EMA rising), a dip to the 20 EMA (swing) or 50 EMA (positional) within 0.5 ATR in the last 5 candles after holding above it, then a bullish candle closing above the previous high. RSI 38–68. Stop below the pullback low."),
      li("Momentum leader (positional, long only): new 50-day closing high within 5% of the 1-year high, uptrend above the 200 EMA, relative strength in the top 30% of its group."),
      li("Crypto and US: long only. Commodities: longs and the mirror shorts (base breakdown, rally into a falling EMA)."),
      li("Score 0–100: trend 25 (trend points + ADX), momentum 20 (relative strength vs the group: crypto vs BTC, US vs the other stocks; RSI zone), setup quality 25, volume 10 (breakout volume vs 20-candle average), macro fit 20 (from Money flow; US stocks blend in their sector's flow score). Against the higher-timeframe trend: −5 and a warning."),
      li("Ideas scoring 50+ are logged in the Track record; lower ones show as \"watch only\".")),
    blk("Commodities direction score (−100..+100)",
      li("40% daily trend + 15% 4-hour trend + 45% drivers. Gold: falling real yields, weaker dollar, risk-off, gold news. Silver: real yields, dollar, industrial demand (copper/gold), silver news. Copper: growth (copper/gold), global risk, dollar, copper news. ±25 = bullish/bearish.")),
    blk("US equity scores",
      li("Trend score per index (S&P 500 via SPY, Nasdaq 100 via QQQ, Russell 2000 via IWM): 50 + 30 × trend points + 10 for the 3-month move + 10 for distance from the 1-year high."),
      li("Sentiment 0–100: S&P trend 20, Nasdaq trend 10, % of stocks above the 50-day 15 and 200-day 10, new highs vs lows 10, VIX 15, credit spreads 10, US news 10. Below 20 extreme fear … above 80 extreme greed."),
      li("Sector flow score: 40% relative strength vs the S&P (1m + half of 3m), 30% Chaikin money flow (20 days), 30% rotation quadrant (Leading 1, Improving 0.65, Weakening 0.35, Lagging 0). 60+ inflow, below 40 outflow."),
      li("Earnings dates are not checked: look before you enter.")));
}

// ------------------------------------------------------------------ sign-in and routing
function viewSignIn(app, message) {
  const email = h("input", { type: "email", value: CFG.email || "", required: true, autocomplete: "username" });
  const pass = h("input", { type: "password", required: true, autocomplete: "current-password" });
  const msg = h("p", { class: "err", role: "status" }, message || "");
  const btn = h("button", { class: "btn primary", type: "submit" }, "Sign in");
  const form = h("form", { class: "panel signin" }, h("h1", null, "Sign in"),
    h("p", { class: "intro" }, "Same account as F&O Desk. You stay signed in on this device until you sign out."),
    h("label", { class: "note" }, "Email", email), h("div", { style: "height:10px" }),
    h("label", { class: "note" }, "Password", pass),
    h("label", { class: "toggle", style: "margin-top:8px" }, h("input", { type: "checkbox", onchange: (e) => { pass.type = e.target.checked ? "text" : "password"; } }), "Show password"),
    h("div", { style: "height:14px" }), btn, msg);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true;
    msg.textContent = "";
    const { error } = await sb.auth.signInWithPassword({ email: email.value.trim(), password: pass.value });
    btn.disabled = false;
    if (error) msg.textContent = /invalid/i.test(error.message) ? "Email or password is wrong." : `Could not sign in: ${error.message}`;
    else route();
  });
  render(app, form);
}

async function route() {
  const app = document.getElementById("app");
  const tab = (location.hash.match(/^#\/(\w+)/) || [])[1] || "macro";
  document.querySelectorAll(".tabs a").forEach((a) => (a.dataset.tab === tab ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  const who = document.getElementById("who");
  if (LIVE) {
    const { data } = await sb.auth.getSession();
    if (!data.session) { who.replaceChildren(); return viewSignIn(app); }
    const mail = data.session.user.email;
    who.replaceChildren(h("span", null, mail), h("button", { type: "button", onclick: async () => { await sb.auth.signOut(); route(); } }, "Sign out"));
    if (CFG.email && mail.toLowerCase() !== CFG.email.toLowerCase()) return viewSignIn(app, `${mail} does not have access to this desk.`);
  } else {
    who.replaceChildren(h("span", null, "Preview with sample data"));
  }
  try {
    if (tab === "flows") await viewFlows(app);
    else if (tab === "crypto") await viewCrypto(app);
    else if (tab === "commod") await viewCommod(app);
    else if (tab === "us") await viewUS(app);
    else if (tab === "record") await viewRecord(app);
    else if (tab === "readme") viewReadme(app);
    else await viewMacro(app);
  } catch (err) {
    console.error(err);
    render(app, h("p", { class: "empty" }, `Could not load the data (${err.message}). Refresh to try again.`));
  }
  clearInterval(refreshTimer);
  if (tab !== "readme") refreshTimer = setInterval(() => { if (!document.getElementById("dlg").open) route(); }, 10 * 60 * 1000);
}

window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
document.getElementById("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  store("desk-theme", dark ? "light" : "dark");
  route();
});
if (LIVE) {
  sb.auth.onAuthStateChange((event) => {
    if (event === "SIGNED_IN") {
      if (location.search.includes("code=")) history.replaceState(null, "", location.pathname + (location.hash || "#/macro"));
      route();
    }
  });
}
route();
