/* ═══════════════════════════════════════════════════════════
   QUANTUM Dashboard — Frontend Application
   Pure vanilla JS SPA — no build step, no dependencies
   ═══════════════════════════════════════════════════════════ */

// ── API Client ──
const api = Object.freeze({
  get: (path) => fetch(`/api/${path}`).then(r => r.json()).catch(() => null),
  post: (path, body) => fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json()).catch(() => null),
});

// ── Utilities ──
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v;
    else if (k === "html") e.innerHTML = v;
    else if (k === "on") Object.entries(v).forEach(([ev, fn]) => e.addEventListener(ev, fn));
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else e.setAttribute(k, v);
  }
  children.forEach(c => {
    if (typeof c === "string") e.appendChild(document.createTextNode(c));
    else if (c) e.appendChild(c);
  });
  return e;
}

const fmtCurrency = (v, region = "US") =>
  region === "IN"
    ? `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtPct = (v) => `${Number(v).toFixed(1)}%`;

const fmtTime = (ts) => {
  if (!ts) return "—";
  const d = new Date(ts.replace(" ", "T"));
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " +
    d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
};

const badge = (text, type = "neutral") =>
  el("span", { class: `badge badge--${type}`, text });

const regionBadge = (sym) => {
  const isIN = sym.endsWith(".NS") || sym.endsWith(".BO");
  return badge(isIN ? "IN" : "US", isIN ? "warning" : "info");
};

const pnlColor = (val) => Number(val) >= 0 ? "var(--success)" : "var(--danger)";
const pnlPrefix = (val) => Number(val) >= 0 ? "+" : "";

// ── Theme Management ──
const themeButtons = { system: null, light: null, dark: null };

function initTheme() {
  themeButtons.system = $(".theme-btn--system");
  themeButtons.light = $(".theme-btn--light");
  themeButtons.dark = $(".theme-btn--dark");

  const stored = localStorage.getItem("quantum-theme") || "system";
  applyTheme(stored);

  Object.entries(themeButtons).forEach(([mode, btn]) => {
    if (btn) btn.addEventListener("click", () => applyTheme(mode));
  });
}

function applyTheme(mode) {
  localStorage.setItem("quantum-theme", mode);
  if (mode === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);

  Object.entries(themeButtons).forEach(([m, btn]) => {
    if (btn) btn.classList.toggle("active", m === mode);
  });

  // Re-render current view to update canvas colors
  handleRoute();
}

// ── Mobile Menu ──
function initMobile() {
  const toggle = $(".mobile-toggle");
  const sidebar = $(".sidebar");
  const overlay = $(".mobile-overlay");
  if (!toggle || !sidebar) return;

  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    overlay?.classList.toggle("visible");
  });
  overlay?.addEventListener("click", () => {
    sidebar.classList.remove("open");
    overlay.classList.remove("visible");
  });
}

// ── System Status Polling ──
async function pollStatus() {
  const data = await api.get("system-status");
  if (!data) return;

  const pill = $(".status-pill");
  if (pill) {
    pill.textContent = data.status;
    pill.className = "status-pill";
    if (data.status === "Active" || data.status === "Analyzing") pill.classList.add("status-pill--active");
    else if (data.status === "Markets Closed" || data.status === "Idle") pill.classList.add("status-pill--idle");
    else if (data.status === "Offline") pill.classList.add("status-pill--error");
    else pill.classList.add("status-pill--active");
  }
  const modeBadge = $(".mode-badge");
  if (modeBadge) modeBadge.textContent = `${data.trading_mode.toUpperCase()} · ${data.trading_style.toUpperCase()}`;

  const toggle = $(".kill-switch input");
  if (toggle) toggle.checked = data.trading_active;
}

// ── SPA Router ──
const routes = {
  portfolio: renderPortfolio,
  "ai-decisions": renderDecisions,
  discovery: renderDiscovery,
  "analysis-trade": renderAnalysisTrade,
  metrics: renderMetrics,
  settings: renderSettings,
};

function initRouter() {
  window.addEventListener("hashchange", handleRoute);
  handleRoute();
}

function handleRoute() {
  const hash = location.hash.slice(1) || "portfolio";
  const view = routes[hash] || routes.portfolio;
  const hashStr = `#${hash}`;
  console.log(hashStr);

  $$("[role='navigation'] a[href]").forEach(a => {
    a.classList.toggle("active", a.getAttribute("href") === hashStr);
    console.log(a.getAttribute("href"), hashStr);
  });
  const title = $(".page-title") || $("#pageTitle");
  if (title) {
    const titles = { portfolio: "Portfolio", "ai-decisions": "AI Decisions", discovery: "Discovery", "analysis-trade": "Analysis & Trade", metrics: "AI Metrics", settings: "Settings" };
    title.textContent = titles[hash] || "Portfolio";
  }
  view();
}

// ── Toast ──
function toast(msg, type = "info") {
  const container = $(".toast-container");
  if (!container) return;
  const t = el("div", { class: `toast toast--${type}`, text: msg });
  container.appendChild(t);
  requestAnimationFrame(() => t.classList.add("visible"));
  setTimeout(() => { t.classList.remove("visible"); setTimeout(() => t.remove(), 300); }, 3000);
}

// ── Confirmation Modal ──
function confirm(message) {
  return new Promise(resolve => {
    const overlay = el("div", { class: "modal-overlay", style: { zIndex: 1000 } });
    const modal = el("div", { class: "card", style: { maxWidth: "400px", margin: "20vh auto", padding: "24px", textAlign: "center" } }, [
      el("p", { text: message, style: { marginBottom: "20px", fontSize: "14px" } }),
      el("div", { style: { display: "flex", gap: "12px", justifyContent: "center" } }, [
        el("button", { class: "btn btn--ghost", text: "Cancel", on: { click: () => { overlay.remove(); resolve(false); } } }),
        el("button", { class: "btn btn--danger", text: "Confirm", on: { click: () => { overlay.remove(); resolve(true); } } }),
      ]),
    ]);
    overlay.appendChild(modal);
    overlay.addEventListener("click", e => { if (e.target === overlay) { overlay.remove(); resolve(false); } });
    document.body.appendChild(overlay);
  });
}

// ═══════════════════════════════════════════════════════════
//  VIEW: PORTFOLIO
// ═══════════════════════════════════════════════════════════
async function renderPortfolio() {
  const main = $("main");
  main.innerHTML = '<div class="loading-spinner">Loading portfolio…</div>';

  const [portfolio, tradeData] = await Promise.all([
    api.get("portfolio"),
    api.get("trades?limit=100"),
  ]);
  if (!portfolio) { main.innerHTML = '<p class="text-muted">Failed to load portfolio.</p>'; return; }

  const trades = tradeData || [];
  const positions = portfolio.active_positions || [];

  // ── Compute unrealized P&L per position (estimated from avg vs latest trade price)
  const latestPrices = {};
  for (const t of trades) {
    if (!latestPrices[t.symbol]) latestPrices[t.symbol] = parseFloat(t.price);
  }

  let usActiveVal = 0, inActiveVal = 0;
  positions.forEach(p => {
    const region = p.region || (p.symbol.endsWith(".NS") || p.symbol.endsWith(".BO") ? "IN" : "US");
    const val = p.quantity * p.avg_price;
    const latest = latestPrices[p.symbol] || p.avg_price;
    p.current_price = latest;
    p.unrealized_pnl = (latest - p.avg_price) * p.quantity;
    p.unrealized_pct = p.avg_price > 0 ? ((latest - p.avg_price) / p.avg_price) * 100 : 0;
    if (region === "US") usActiveVal += val; else inActiveVal += val;
    p._region = region;
  });

  main.innerHTML = "";

  // ── Metric Cards ──
  const grid = el("div", { class: "metric-grid" });

  const fxRate = portfolio.live_usd_inr || 83.5;
  const globalUsdVal = usActiveVal + (inActiveVal / fxRate);

  const cards = [
    { label: "🇺🇸 Active Holdings", value: fmtCurrency(usActiveVal, "US"), sub: `${positions.filter(p => p._region === "US").length} positions` },
    { label: "🇮🇳 Active Holdings", value: fmtCurrency(inActiveVal, "IN"), sub: `${positions.filter(p => p._region === "IN").length} positions` },
    { label: "� Global Net Worth", value: fmtCurrency(globalUsdVal, "US"), sub: `INR @ ${fxRate.toFixed(2)}`, color: "var(--primary)" },
    { label: "�🇺🇸 Realized P&L", value: `${pnlPrefix(portfolio.us_realized_pnl)}${fmtCurrency(portfolio.us_realized_pnl, "US")}`, sub: `Fees: ${fmtCurrency(portfolio.us_fees, "US")}`, color: pnlColor(portfolio.us_realized_pnl) },
    { label: "🇮🇳 Realized P&L", value: `${pnlPrefix(portfolio.in_realized_pnl)}${fmtCurrency(portfolio.in_realized_pnl, "IN")}`, sub: `Fees: ${fmtCurrency(portfolio.in_fees, "IN")}`, color: pnlColor(portfolio.in_realized_pnl) },
  ];
  cards.forEach(c => {
    const card = el("div", { class: "card metric-card" }, [
      el("div", { class: "metric-label", text: c.label }),
      el("div", { class: "metric-value", text: c.value, style: c.color ? { color: c.color } : {} }),
      el("div", { class: "metric-sub text-muted", text: c.sub }),
    ]);
    grid.appendChild(card);
  });
  main.appendChild(grid);

  // ── Performance Metrics ──
  const advMetrics = portfolio.advanced_metrics;
  if (advMetrics) {
    const perfGrid = el("div", { class: "metric-grid", style: { marginTop: "16px" } });
    const perfCards = [
      { label: "🏆 Win Rate", value: `${advMetrics.win_rate}%`, sub: `${advMetrics.winning_trades}W / ${advMetrics.losing_trades}L` },
      { label: "⚖️ Profit Factor", value: advMetrics.profit_factor.toFixed(2), sub: advMetrics.profit_factor >= 2 ? "Excellent" : (advMetrics.profit_factor > 1 ? "Profitable" : "Unprofitable"), color: advMetrics.profit_factor > 1 ? "var(--primary)" : "var(--danger)" },
      { label: "📉 Max Drawdown", value: fmtCurrency(advMetrics.max_drawdown_usd, "US"), sub: "Peak to trough USD", color: "var(--danger)" },
    ];
    perfCards.forEach(c => {
      const card = el("div", { class: "card metric-card" }, [
        el("div", { class: "metric-label", text: c.label }),
        el("div", { class: "metric-value", text: c.value, style: c.color ? { color: c.color } : {} }),
        el("div", { class: "metric-sub text-muted", text: c.sub }),
      ]);
      perfGrid.appendChild(card);
    });
    main.appendChild(perfGrid);
  }

  // ── Portfolio Value Chart + Active Positions ──
  const midRow = el("div", { class: "grid-2" });

  // Value chart card
  const chartCard = el("div", { class: "card" });
  const chartHeader = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" } });
  chartHeader.appendChild(el("div", { class: "card-title", text: "PORTFOLIO VALUE" }));

  // Time range selector
  const timeRangeDiv = el("div", { style: { display: "flex", gap: "4px" } });
  const ranges = [
    { label: "24H", days: 1 }, { label: "7D", days: 7 }, { label: "1M", days: 30 },
    { label: "YTD", days: -1 }, { label: "1Y", days: 365 }, { label: "ALL", days: 0 },
  ];
  let activeRange = "ALL";
  ranges.forEach(r => {
    const btn = el("button", {
      class: `btn btn--ghost ${r.label === "ALL" ? "active" : ""}`,
      text: r.label,
      style: { padding: "4px 10px", fontSize: "11px", borderRadius: "6px" },
      on: {
        click: () => {
          $$("button", timeRangeDiv).forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          activeRange = r.label;
          drawPortfolioChart(chartCanvas, portfolio.value_timeline, r.days);
        }
      },
    });
    timeRangeDiv.appendChild(btn);
  });
  chartHeader.appendChild(timeRangeDiv);
  chartCard.appendChild(chartHeader);

  const chartCanvas = el("canvas", { width: "600", height: "260" });
  chartCard.appendChild(chartCanvas);

  // Legend
  const legend = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" } });

  const legendLeft = el("div", { style: { display: "flex", gap: "16px" } });
  legendLeft.appendChild(el("span", { html: '<span style="color:var(--primary)">●</span> Global Net Worth', class: "text-muted", style: { fontSize: "12px", fontWeight: "bold" } }));
  legendLeft.appendChild(el("span", { html: '<span style="color:var(--accent)">●</span> US Value', class: "text-muted", style: { fontSize: "12px" } }));
  legendLeft.appendChild(el("span", { html: '<span style="color:var(--warning)">●</span> IN Value', class: "text-muted", style: { fontSize: "12px" } }));

  let chartCurrency = "USD";
  const currencyToggle = el("div", { style: { fontSize: "12px", display: "flex", gap: "4px", alignItems: "center" } });
  currencyToggle.appendChild(document.createTextNode("View in: "));
  const btnUsd = el("button", { class: "btn btn--ghost active", text: "USD", style: { padding: "2px 6px", fontSize: "11px" } });
  const btnInr = el("button", { class: "btn btn--ghost", text: "INR", style: { padding: "2px 6px", fontSize: "11px" } });

  btnUsd.onclick = () => { btnUsd.classList.add("active"); btnInr.classList.remove("active"); chartCurrency = "USD"; drawPortfolioChart(chartCanvas, portfolio.value_timeline, activeRange === "ALL" ? 0 : ranges.find(r => r.label === activeRange).days, fxRate, "USD"); };
  btnInr.onclick = () => { btnInr.classList.add("active"); btnUsd.classList.remove("active"); chartCurrency = "INR"; drawPortfolioChart(chartCanvas, portfolio.value_timeline, activeRange === "ALL" ? 0 : ranges.find(r => r.label === activeRange).days, fxRate, "INR"); };

  currencyToggle.append(btnUsd, btnInr);
  legend.append(legendLeft, currencyToggle);

  chartCard.appendChild(legend);

  midRow.appendChild(chartCard);

  // ── Active Positions ──
  const posCard = el("div", { class: "card" });
  posCard.appendChild(el("div", { class: "card-title", text: "ACTIVE POSITIONS" }));

  if (positions.length === 0) {
    posCard.appendChild(el("p", { class: "empty-state", html: "📭 No active positions" }));
  } else {
    const tbl = el("table", { class: "data-table" });
    const thead = el("thead");
    thead.appendChild(el("tr", {}, [
      el("th", { text: "SYMBOL" }), el("th", { text: "QTY" }), el("th", { text: "AVG" }),
      el("th", { text: "VALUE" }), el("th", { text: "UNREALIZED P&L" }),
    ]));
    tbl.appendChild(thead);
    const tbody = el("tbody");
    positions.forEach(p => {
      const val = p.quantity * p.avg_price;
      const pnlVal = p.unrealized_pnl;
      const pnlPct = p.unrealized_pct;
      const isIN = p._region === "IN";
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [regionBadge(p.symbol), document.createTextNode(` ${p.symbol}`)]),
        el("td", { text: String(Math.round(p.quantity)) }),
        el("td", { text: Number(p.avg_price).toFixed(2) }),
        el("td", { text: fmtCurrency(val, isIN ? "IN" : "US") }),
        el("td", {
          html: `<span style="color:${pnlColor(pnlVal)}">${pnlPrefix(pnlVal)}${fmtCurrency(Math.abs(pnlVal), isIN ? "IN" : "US")} (${pnlPrefix(pnlPct)}${Math.abs(pnlPct).toFixed(1)}%)</span>`,
        }),
      ]));
    });
    tbl.appendChild(tbody);
    posCard.appendChild(tbl);
  }
  midRow.appendChild(posCard);
  main.appendChild(midRow);

  // Draw chart (ALL by default)
  drawPortfolioChart(chartCanvas, portfolio.value_timeline, 0, fxRate, chartCurrency);

  // ── Recent Trades ──
  const tradeCard = el("div", { class: "card" });
  tradeCard.appendChild(el("div", { class: "card-title", text: `RECENT TRADES (${trades.length} total)` }));

  if (trades.length === 0) {
    tradeCard.appendChild(el("p", { class: "empty-state", html: "📭 No trades yet" }));
  } else {
    const tbl = el("table", { class: "data-table" });
    const thead = el("thead");
    thead.appendChild(el("tr", {}, [
      el("th", { text: "TIME" }), el("th", { text: "SYMBOL" }), el("th", { text: "ACTION" }),
      el("th", { text: "QTY" }), el("th", { text: "PRICE" }), el("th", { text: "FEES" }),
      el("th", { text: "NET P&L" }), el("th", { text: "STATUS" }),
    ]));
    tbl.appendChild(thead);
    const tbody = el("tbody");
    trades.forEach(t => {
      const actionType = (t.action || "").toUpperCase().includes("BUY") ? "success" : "danger";
      const fees = t.estimated_fees ? fmtCurrency(t.estimated_fees, t.fee_currency === "INR" ? "IN" : "US") : "—";
      const pnl = t.net_pnl != null ? el("span", { text: `${pnlPrefix(t.net_pnl)}${fmtCurrency(Math.abs(t.net_pnl))}`, style: { color: pnlColor(t.net_pnl) } }) : el("span", { class: "text-muted", text: "—" });
      tbody.appendChild(el("tr", {}, [
        el("td", { text: fmtTime(t.timestamp) }),
        el("td", {}, [regionBadge(t.symbol), document.createTextNode(` ${t.symbol}`)]),
        el("td", {}, [badge(t.action, actionType)]),
        el("td", { text: String(Math.round(t.quantity)) }),
        el("td", { text: Number(t.price).toFixed(2) }),
        el("td", { text: fees }),
        el("td", {}, [pnl]),
        el("td", { text: t.status }),
      ]));
    });
    tbl.appendChild(tbody);
    tradeCard.appendChild(tbl);
  }
  main.appendChild(tradeCard);
}

function drawPortfolioChart(canvas, timeline, daysFilter, fxRate = 83.5, currency = "USD") {
  if (!timeline || timeline.length === 0) {
    const ctx = canvas.getContext("2d");
    const w = canvas.parentElement.clientWidth - 40;
    canvas.width = w * 2; canvas.height = 260 * 2;
    canvas.style.width = w + "px"; canvas.style.height = "260px";
    ctx.scale(2, 2);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text-tertiary");
    ctx.font = "13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No trade data yet", w / 2, 130);
    return;
  }

  // Filter by time range
  let data = [...timeline];
  const now = new Date();
  if (daysFilter > 0) {
    const cutoff = new Date(now.getTime() - daysFilter * 86400000);
    data = data.filter(d => new Date(d.time.replace(" ", "T")) >= cutoff);
  } else if (daysFilter === -1) {
    // YTD
    const startOfYear = new Date(now.getFullYear(), 0, 1);
    data = data.filter(d => new Date(d.time.replace(" ", "T")) >= startOfYear);
  }
  if (data.length === 0) data = timeline;

  const ctx = canvas.getContext("2d");
  const w = canvas.parentElement.clientWidth - 40;
  const h = 260;
  canvas.width = w * 2; canvas.height = h * 2;
  canvas.style.width = w + "px"; canvas.style.height = h + "px";
  ctx.scale(2, 2);

  const pad = { top: 20, right: 60, bottom: 40, left: 60 };
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;

  const style = getComputedStyle(document.documentElement);
  const textColor = style.getPropertyValue("--text-tertiary").trim() || "#94a3b8";
  const gridColor = style.getPropertyValue("--border").trim() || "#e2e8f0";
  const accentColor = style.getPropertyValue("--accent").trim() || "#3b82f6";
  const warningColor = style.getPropertyValue("--warning").trim() || "#f59e0b";
  const primaryColor = style.getPropertyValue("--primary").trim() || "#10b981";

  const usValues = data.map(d => currency === "USD" ? d.us_value : (d.us_value * fxRate));
  const inValues = data.map(d => currency === "USD" ? (d.in_value / fxRate) : d.in_value);
  const globalValues = usValues.map((v, i) => v + inValues[i]);

  const allValues = [...usValues, ...inValues, ...globalValues];
  const maxVal = Math.max(...allValues, 1);

  // Grid lines
  ctx.strokeStyle = gridColor;
  ctx.lineWidth = 0.5;
  ctx.setLineDash([3, 3]);
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ch / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
    ctx.fillStyle = textColor; ctx.font = "10px Inter, sans-serif"; ctx.textAlign = "right";

    // Add symbol to grid labels
    const symb = currency === "USD" ? "$" : "₹";
    const label = Math.round(maxVal - (maxVal / 4) * i).toLocaleString();
    ctx.fillText(`${symb}${label}`, pad.left - 8, y + 4);

    // Also paint on the right side for symmetry
    ctx.textAlign = "left";
    ctx.fillText(`${symb}${label}`, w - pad.right + 8, y + 4);
  }
  ctx.setLineDash([]);

  // X-axis labels
  const step = Math.max(1, Math.floor(data.length / 6));
  ctx.fillStyle = textColor; ctx.font = "10px Inter, sans-serif"; ctx.textAlign = "center";
  for (let i = 0; i < data.length; i += step) {
    const x = pad.left + (i / (data.length - 1 || 1)) * cw;
    ctx.fillText(fmtTime(data[i].time), x, h - 8);
  }

  // Draw lines
  function drawLine(values, color, fill = false) {
    if (values.length < 2) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = fill ? 3 : 2;
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = pad.left + (i / (values.length - 1 || 1)) * cw;
      const y = pad.top + ch - (v / maxVal) * ch;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    if (fill) {
      // Area fill
      ctx.globalAlpha = 0.08;
      ctx.lineTo(pad.left + cw, pad.top + ch);
      ctx.lineTo(pad.left, pad.top + ch);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  drawLine(usValues, accentColor, false);
  drawLine(inValues, warningColor, false);
  drawLine(globalValues, primaryColor, true);
}


// ═══════════════════════════════════════════════════════════
//  VIEW: AI DECISIONS
// ═══════════════════════════════════════════════════════════
async function renderDecisions() {
  const main = $("main");
  main.innerHTML = '<div class="loading-spinner">Loading AI decisions…</div>';

  const data = await api.get("ai-decisions?limit=200");
  if (!data) { main.innerHTML = '<p class="text-muted">Failed to load decisions.</p>'; return; }

  main.innerHTML = "";

  // ── Filters ──
  const filterBar = el("div", { class: "filter-bar" });

  // Decision type filter
  const decisionSelect = el("select", { class: "filter-select", on: { change: () => applyFilters() } }, [
    el("option", { value: "", text: "All Decisions" }),
    el("option", { value: "BUY", text: "🟢 BUY" }),
    el("option", { value: "SELL", text: "🔴 SELL" }),
    el("option", { value: "HOLD", text: "⚪ HOLD" }),
  ]);
  filterBar.appendChild(decisionSelect);

  // Symbol filter
  const symbols = [...new Set(data.map(d => d.symbol))].sort();
  const symbolSelect = el("select", { class: "filter-select", on: { change: () => applyFilters() } }, [
    el("option", { value: "", text: "All Symbols" }),
    ...symbols.map(s => el("option", { value: s, text: s })),
  ]);
  filterBar.appendChild(symbolSelect);

  // Count
  const countSpan = el("span", { class: "text-muted", style: { marginLeft: "8px", fontSize: "13px" } });
  filterBar.appendChild(countSpan);

  main.appendChild(filterBar);

  const container = el("div", { class: "decisions-list" });
  main.appendChild(container);

  function applyFilters() {
    const decFilter = decisionSelect.value;
    const symFilter = symbolSelect.value;
    let filtered = data;
    if (decFilter) filtered = filtered.filter(d => (d.decision || "").toUpperCase().includes(decFilter));
    if (symFilter) filtered = filtered.filter(d => d.symbol === symFilter);
    countSpan.textContent = `${filtered.length} of ${data.length} decisions`;
    renderDecisionList(container, filtered);
  }

  applyFilters();
}

function renderDecisionList(container, decisions) {
  container.innerHTML = "";
  if (decisions.length === 0) {
    container.appendChild(el("div", { class: "empty-state", html: "🧠<br>No AI decisions match the current filters." }));
    return;
  }

  decisions.forEach(d => {
    const decision = (d.decision || "HOLD").toUpperCase();
    const confidence = parseFloat(d.confidence || 0);
    const reasoning = d.reasoning || d.reason || "";
    const isError = reasoning.startsWith("Error");

    let decType = "neutral";
    if (isError) decType = "danger";
    else if (decision.includes("BUY")) decType = "success";
    else if (decision.includes("SELL")) decType = "danger";

    const card = el("div", { class: "card decision-card", style: { cursor: "pointer" } });

    // Header row
    const header = el("div", { class: "decision-card-header" });
    header.appendChild(el("div", { style: { display: "flex", alignItems: "center", gap: "10px" } }, [
      regionBadge(d.symbol),
      el("strong", { text: d.symbol, class: "symbol" }),
      badge(isError ? "ERROR" : decision, decType),
      confidence > 0 ? el("span", { class: "text-muted", text: `${(confidence * 100).toFixed(0)}% conf`, style: { fontSize: "12px" } }) : null,
    ]));
    header.appendChild(el("span", { class: "time", text: fmtTime(d.timestamp) }));
    card.appendChild(header);

    // Reasoning (always show, even if error)
    if (reasoning) {
      const reasoningEl = el("div", { class: "decision-reasoning" });
      if (isError) {
        reasoningEl.style.color = "var(--danger)";
        reasoningEl.textContent = `⚠️ ${reasoning}`;
      } else {
        reasoningEl.textContent = reasoning;
      }
      card.appendChild(reasoningEl);
    }

    // Expandable Details (Technicals, News, Risk Review)
    const details = el("div", { class: "decision-details expandable-content", style: { marginTop: "12px", borderTop: "1px solid var(--border)", paddingTop: "12px", fontSize: "13px" } });

    let hasDetails = false;

    // 1. Risk Review
    if (d.was_overridden || d.review_decision) {
      hasDetails = true;
      const reviewBox = el("div", { style: { marginBottom: "12px", padding: "8px", background: d.was_overridden ? "var(--danger-soft)" : "var(--bg-elevated)", borderRadius: "6px" } });
      reviewBox.innerHTML = `<strong>🛡 Risk Manager:</strong> ${d.review_decision || "Reviewed"} ${d.was_overridden ? "(OVERRIDE)" : ""} — ${d.review_reasoning || "No details"}`;
      details.appendChild(reviewBox);
    }

    // Execution Targets
    if (d.target_buy_price || d.target_sell_price || d.stop_loss_suggestion || d.option_strike) {
      hasDetails = true;
      const paramBox = el("div", { style: { marginBottom: "12px" } });
      paramBox.innerHTML = `<div class="text-muted" style="margin-bottom:4px; font-weight:600;">🎯 Execution Targets</div>`;

      const paramGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "8px" } });

      if (d.target_buy_price) paramGrid.appendChild(el("div", { class: "badge badge--info", text: `Buy Target: $${d.target_buy_price}` }));
      if (d.target_sell_price) paramGrid.appendChild(el("div", { class: "badge badge--success", text: `Sell Target: $${d.target_sell_price}` }));
      if (d.stop_loss_suggestion) paramGrid.appendChild(el("div", { class: "badge badge--danger", text: `Stop Loss: $${d.stop_loss_suggestion}` }));

      if (d.option_strike) paramGrid.appendChild(el("div", { class: "badge badge--warning", text: `Strike: $${d.option_strike}` }));
      if (d.option_expiry) paramGrid.appendChild(el("div", { class: "badge badge--warning", text: `Expiry: ${d.option_expiry}` }));

      paramBox.appendChild(paramGrid);
      details.appendChild(paramBox);
    }

    // 2. Technicals (from ai_decision_logs)
    if (d.technical_summary) {
      hasDetails = true;
      const tech = d.technical_summary;
      const techBox = el("div", { style: { marginBottom: "12px" } });
      techBox.innerHTML = `<div class="text-muted" style="margin-bottom:4px; font-weight:600;">📈 Technicals</div>`;

      const techGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "8px" } });
      for (const [k, v] of Object.entries(tech)) {
        if (typeof v === 'object') continue; // Skip nested if any
        let displayVal = v;
        let semanticLabel = k.toUpperCase().replace(/_/g, " ");

        if (typeof v === 'number') {
          if (k === 'volume' || k === 'avg_volume') {
            displayVal = v.toLocaleString(); // Add commas for big numbers
          } else if (k === 'rsi') {
            displayVal = `${v.toFixed(1)} ${v >= 70 ? '🟥 (Overbought)' : v <= 30 ? '🟩 (Oversold)' : '⬜ (Neutral)'}`;
          } else if (k.includes('macd')) {
            displayVal = `${v > 0 ? '+' : ''}${v.toFixed(3)}`;
          } else if (k === 'volume_oscillator') {
            displayVal = `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
          } else if (!Number.isInteger(v)) {
            displayVal = `$${v.toFixed(2)}`; // Price values (SMA, Bollinger, ATR)
          }
        }

        techGrid.appendChild(el("div", { class: "badge badge--neutral", text: `${semanticLabel}: ${displayVal}` }));
      }
      techBox.appendChild(techGrid);
      details.appendChild(techBox);
    }

    // 3. News Headlines
    if (d.news_headlines && Array.isArray(d.news_headlines)) {
      hasDetails = true;
      const newsBox = el("div", { style: { marginBottom: "12px" } });
      newsBox.innerHTML = `<div class="text-muted" style="margin-bottom:4px; font-weight:600;">📰 News Context</div>`;
      const ul = el("ul", { style: { paddingLeft: "16px", color: "var(--text-secondary)" } });
      d.news_headlines.forEach(h => ul.appendChild(el("li", { text: h })));
      newsBox.appendChild(ul);
      details.appendChild(newsBox);
    }

    // 4. Fallback Mode Warning
    if (d.fallback_mode) {
      // Only show if we strictly rely on fallback and user might wonder where technicals are
      // But usually, existing decisions won't have technicals anyway.
    }

    if (hasDetails) {
      const toggleBtn = el("button", { class: "expand-toggle", text: "Show Analysis Details ▾" });
      toggleBtn.onclick = (e) => {
        e.stopPropagation();
        const isOpen = details.classList.toggle("open");
        toggleBtn.textContent = isOpen ? "Hide Analysis Details ▴" : "Show Analysis Details ▾";
      };
      card.appendChild(toggleBtn);
      card.appendChild(details);
    } else if (!isError) {
      // If no details and no error, maybe just show reasoning is enough
    }

    container.appendChild(card);
  });
}


// ═══════════════════════════════════════════════════════════
//  VIEW: AI METRICS
// ═══════════════════════════════════════════════════════════
async function renderMetrics() {
  const main = $("main");
  main.innerHTML = '<div class="loading-spinner">Loading metrics…</div>';

  const data = await api.get("metrics");
  if (!data) { main.innerHTML = '<p class="text-muted">Failed to load metrics.</p>'; return; }

  main.innerHTML = "";

  // ── Metric Cards (removed Est. Cost) ──
  const grid = el("div", { class: "metric-grid" });
  const metrics = [
    { label: "TOTAL API CALLS", value: data.total_calls.toLocaleString() },
    { label: "TOTAL TOKENS", value: data.total_tokens.toLocaleString() },
    { label: "AVG LATENCY", value: `${data.avg_latency_ms.toLocaleString()} ms` },
    { label: "SUCCESS RATE", value: fmtPct(data.success_rate) },
  ];
  metrics.forEach(m => {
    grid.appendChild(el("div", { class: "card metric-card" }, [
      el("div", { class: "metric-label", text: m.label }),
      el("div", { class: "metric-value", text: m.value }),
    ]));
  });
  main.appendChild(grid);

  // ── Charts Row: Token Usage + Decision Distribution ──
  const chartRow = el("div", { class: "grid-2" });

  // Token donut
  const tokenCard = el("div", { class: "card" });
  tokenCard.appendChild(el("div", { class: "card-title", text: "TOKEN USAGE" }));
  const tokenCanvas = el("canvas", { width: "300", height: "240" });
  tokenCard.appendChild(tokenCanvas);
  tokenCard.appendChild(el("div", { style: { display: "flex", gap: "16px", marginTop: "8px" } }, [
    el("span", { html: `<span style="color:var(--accent)">●</span> Prompt: ${data.prompt_tokens.toLocaleString()}`, class: "text-muted", style: { fontSize: "12px" } }),
    el("span", { html: `<span style="color:var(--warning)">●</span> Completion: ${data.completion_tokens.toLocaleString()}`, class: "text-muted", style: { fontSize: "12px" } }),
  ]));
  chartRow.appendChild(tokenCard);

  // Decision distribution
  const distCard = el("div", { class: "card" });
  distCard.appendChild(el("div", { class: "card-title", text: "DECISION DISTRIBUTION" }));
  if (data.decision_distribution && data.decision_distribution.length > 0) {
    const distCanvas = el("canvas", { width: "300", height: "240" });
    distCard.appendChild(distCanvas);
    const distLegend = el("div", { style: { display: "flex", gap: "12px", marginTop: "8px", flexWrap: "wrap" } });
    const distColors = ["var(--success)", "var(--danger)", "var(--accent)", "var(--warning)", "#94a3b8"];
    data.decision_distribution.forEach((d, i) => {
      distLegend.appendChild(el("span", { html: `<span style="color:${distColors[i % distColors.length]}">●</span> ${d.decision}: ${d.count}`, class: "text-muted", style: { fontSize: "12px" } }));
    });
    distCard.appendChild(distLegend);
    setTimeout(() => drawDonut(distCanvas, data.decision_distribution.map(d => d.count), distColors, data.decision_distribution.reduce((a, c) => a + c.count, 0).toLocaleString()), 50);
  } else {
    distCard.appendChild(el("p", { class: "empty-state text-muted", text: "No decision data" }));
  }
  chartRow.appendChild(distCard);
  main.appendChild(chartRow);

  // ── Source Breakdown + Latency Trend ──
  const bottomRow = el("div", { class: "grid-2" });

  // Source breakdown
  const srcCard = el("div", { class: "card" });
  srcCard.appendChild(el("div", { class: "card-title", text: "API CALL SOURCES" }));
  if (data.source_breakdown && data.source_breakdown.length > 0) {
    const srcTbl = el("table", { class: "data-table" });
    srcTbl.appendChild(el("thead", {}, [el("tr", {}, [el("th", { text: "SOURCE" }), el("th", { text: "CALLS" }), el("th", { text: "%" })])]));
    const srcBody = el("tbody");
    data.source_breakdown.forEach(s => {
      const pct = data.total_calls > 0 ? ((s.count / data.total_calls) * 100).toFixed(1) : "0";
      srcBody.appendChild(el("tr", {}, [
        el("td", { text: s.source }),
        el("td", { text: s.count.toLocaleString() }),
        el("td", { text: `${pct}%` }),
      ]));
    });
    srcTbl.appendChild(srcBody);
    srcCard.appendChild(srcTbl);
  } else {
    srcCard.appendChild(el("p", { class: "empty-state text-muted", text: "No source data" }));
  }
  bottomRow.appendChild(srcCard);

  // Latency trend
  const latCard = el("div", { class: "card" });
  latCard.appendChild(el("div", { class: "card-title", text: "API LATENCY TREND" }));
  const latCanvas = el("canvas", { width: "600", height: "220" });
  latCard.appendChild(latCanvas);
  bottomRow.appendChild(latCard);

  main.appendChild(bottomRow);

  // Draw charts after DOM paint
  setTimeout(() => {
    drawDonut(tokenCanvas, [data.prompt_tokens, data.completion_tokens], ["var(--accent)", "var(--warning)"], data.total_tokens.toLocaleString());
    if (data.latency_trend && data.latency_trend.length > 1)
      drawLineChart(latCanvas, data.latency_trend.reverse());
  }, 50);
}


// ═══════════════════════════════════════════════════════════
//  VIEW: DISCOVERY
// ═══════════════════════════════════════════════════════════
async function renderDiscovery() {
  const main = $("main");
  main.innerHTML = '<div class="loading-spinner">Loading discovery…</div>';

  const watched = await api.get("watched-tickers") || [];

  main.innerHTML = "";

  // ── WATCHED TICKERS ──
  const watchCard = el("div", { class: "card", style: { marginBottom: "20px" } });
  watchCard.appendChild(el("div", { class: "card-title", text: "👀 WATCHED TICKERS" }));

  if (watched.length === 0) {
    watchCard.appendChild(el("p", { class: "text-muted empty-state", text: "No watched tickers yet. Browse below to add some." }));
  } else {
    const wGrid = el("div", { style: { display: "flex", flexWrap: "wrap", gap: "8px" } });
    watched.forEach(w => {
      const chip = el("div", { class: "badge badge--neutral", style: { display: "flex", gap: "6px", alignItems: "center", padding: "4px 10px", fontSize: "12px", borderRadius: "12px" } });
      chip.appendChild(regionBadge(w.symbol));
      chip.appendChild(el("strong", { text: w.symbol }));

      const delBtn = el("button", {
        html: "&times;",
        style: { background: "none", border: "none", color: "var(--danger)", cursor: "pointer", fontSize: "16px", marginLeft: "4px", padding: "0 4px", lineHeight: "1" },
        on: {
          click: async () => {
            if (await confirm(`Remove ${w.symbol} from watchlist?`)) {
              await api.delete(`watched-tickers/${w.symbol}`);
              toast(`Removed ${w.symbol}`);
              renderDiscovery();
            }
          }
        }
      });
      chip.appendChild(delBtn);
      wGrid.appendChild(chip);
    });
    watchCard.appendChild(wGrid);
  }
  main.appendChild(watchCard);

  const sectors = [
    // US
    { name: "US Mega-Cap Tech", flag: "🇺🇸", tickers: ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA"] },
    { name: "US Semiconductors", flag: "🇺🇸", tickers: ["NVDA", "AMD", "INTC", "MU", "AVGO", "QCOM", "TSM", "ASML"] },
    { name: "US Finance", flag: "🇺🇸", tickers: ["JPM", "BAC", "GS", "MS", "V", "MA", "BRK-B", "C"] },
    { name: "US Healthcare", flag: "🇺🇸", tickers: ["JNJ", "UNH", "PFE", "ABBV", "MRK", "AMGN", "LLY", "BMY"] },
    { name: "US Energy & Resources", flag: "🇺🇸", tickers: ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "SGLD.L"] },
    { name: "US ETFs & Index", flag: "🇺🇸", tickers: ["SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "XLF"] },
    { name: "Crypto Proxies", flag: "🇺🇸", tickers: ["MSTR", "MSTX", "COIN", "MARA", "RIOT", "SQ", "PYPL"] },
    { name: "US Aerospace & Defense", flag: "🇺🇸", tickers: ["LMT", "RTX", "BA", "NOC", "GD", "PLTR", "LHX"] },
    { name: "US Consumer & Retail", flag: "🇺🇸", tickers: ["WMT", "COST", "TGT", "HD", "NKE", "SBUX", "MCD", "DIS"] },
    // India
    { name: "Nifty 50 Blue Chips", flag: "🇮🇳", tickers: ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "HINDUNILVR.NS", "ITC.NS", "BAJFINANCE.NS"] },
    { name: "India IT Services", flag: "🇮🇳", tickers: ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTI.NS", "MPHASIS.NS"] },
    { name: "India Banking & Finance", flag: "🇮🇳", tickers: ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS"] },
    { name: "India Pharma & Healthcare", flag: "🇮🇳", tickers: ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS", "BIOCON.NS"] },
    { name: "India Auto & Industrial", flag: "🇮🇳", tickers: ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "TATASTEEL.NS"] },
    { name: "India Energy & Power", flag: "🇮🇳", tickers: ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "ADANIGREEN.NS", "TATAPOWER.NS"] },
    { name: "India FMCG & Consumer", flag: "🇮🇳", tickers: ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "DABUR.NS", "BRITANNIA.NS", "GODREJCP.NS"] },
  ];

  // Sector grid
  const discoverCard = el("div", { class: "card" });
  discoverCard.appendChild(el("div", { class: "card-title", text: "📊 STOCK DISCOVERY" }));
  discoverCard.appendChild(el("p", { class: "text-muted", text: "Browse sectors and add tickers to your watchlist.", style: { marginBottom: "16px", fontSize: "13px" } }));

  const sectorGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "12px" } });

  sectors.forEach(sector => {
    const sCard = el("div", { class: "card", style: { padding: "14px", cursor: "pointer" } });

    const header = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" } });
    header.appendChild(el("strong", { text: `${sector.flag} ${sector.name}`, style: { fontSize: "14px" } }));
    header.appendChild(el("span", { class: "text-muted", text: `${sector.tickers.length} tickers`, style: { fontSize: "12px" } }));
    sCard.appendChild(header);

    const tickerRow = el("div", { style: { display: "flex", flexWrap: "wrap", gap: "4px" } });
    sector.tickers.forEach(ticker => {
      const chip = el("button", {
        class: "btn btn--ghost",
        text: ticker,
        style: { padding: "2px 8px", fontSize: "11px", borderRadius: "4px" },
        on: {
          click: async (e) => {
            e.stopPropagation();
            const region = ticker.endsWith(".NS") || ticker.endsWith(".BO") ? "IN" : "US";
            const res = await api.post("watched-tickers", { symbol: ticker, region: region, notes: "Added from Discovery" });
            if (res && res.ok) {
              toast(`Added ${ticker} to watch list`, "success");
              renderDiscovery();
            } else {
              toast(`Failed or already in watchlist`, "error");
            }
          }
        },
      });
      tickerRow.appendChild(chip);
    });
    sCard.appendChild(tickerRow);
    sectorGrid.appendChild(sCard);
  });

  discoverCard.appendChild(sectorGrid);
  main.appendChild(discoverCard);
}


// ═══════════════════════════════════════════════════════════
//  VIEW: ANALYSIS & TRADE
// ═══════════════════════════════════════════════════════════
async function renderAnalysisTrade() {
  const main = $("main");
  main.innerHTML = "";

  const container = el("div", { style: { maxWidth: "800px", margin: "0 auto" } });

  // ── HEADER ──
  container.appendChild(el("div", { class: "card-title", text: "⚡ ANALYSIS & TRADE", style: { marginBottom: "8px" } }));
  container.appendChild(el("p", { class: "text-muted", text: "Analyze assets with the AI before executing. Manually executed trades are recorded in the portfolio database.", style: { marginBottom: "24px", fontSize: "14px" } }));

  // ── ANALYSIS SECTION ──
  const analysisCard = el("div", { class: "card", style: { marginBottom: "20px" } });

  const searchRow = el("div", { style: { display: "flex", gap: "12px", marginBottom: "16px" } });
  searchRow.appendChild(el("div", { style: { flex: 2 } }, [
    el("label", { text: "Symbol", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "analyze-symbol", class: "settings-input", type: "text", required: true, style: { width: "100%" }, placeholder: "e.g. AAPL or RELIANCE.NS" })
  ]));
  searchRow.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Asset", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("select", {
      id: "analyze-asset", class: "settings-input", style: { width: "100%" }, on: {
        change: (e) => {
          const isOpt = e.target.value !== "STOCK";
          $("#opt-details-row").style.display = isOpt ? "flex" : "none";
        }
      }
    }, [
      el("option", { value: "STOCK", text: "Stock" }),
      el("option", { value: "CALL", text: "Call Option" }),
      el("option", { value: "PUT", text: "Put Option" }),
    ])
  ]));
  analysisCard.appendChild(searchRow);

  const optRow = el("div", { id: "opt-details-row", style: { display: "none", gap: "12px", marginBottom: "16px", padding: "12px", background: "var(--bg-elevated)", borderRadius: "8px" } });
  optRow.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Strike Price", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "analyze-strike", class: "settings-input", type: "number", step: "0.01", style: { width: "100%" } })
  ]));
  optRow.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Expiry Date", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "analyze-expiry", class: "settings-input", type: "date", style: { width: "100%" } })
  ]));
  analysisCard.appendChild(optRow);

  const analyzeBtn = el("button", {
    class: "btn btn--primary",
    html: "🧠 Get AI Analysis & Load Chart",
    style: { width: "100%", padding: "12px" }
  });
  analysisCard.appendChild(analyzeBtn);

  // ── RESULTS & CHART BOX ──
  const resultsBox = el("div", { id: "analysis-result-box", style: { display: "none", marginTop: "20px" } });
  const aiReportDiv = el("div", { style: { padding: "16px", background: "var(--bg-card)", border: "1px dashed var(--border)", borderRadius: "8px", marginBottom: "20px" } });
  const chartContainer = el("div", { style: { width: "100%", height: "300px", position: "relative", marginBottom: "20px" } });
  const chartCanvas = el("canvas", { width: "800", height: "300" });
  chartContainer.appendChild(chartCanvas);

  resultsBox.appendChild(aiReportDiv);
  resultsBox.appendChild(chartContainer);

  const proceedBtn = el("button", { class: "btn btn--outline", text: "Proceed to Trade Execution ↓", style: { width: "100%" } });
  resultsBox.appendChild(proceedBtn);

  analysisCard.appendChild(resultsBox);
  container.appendChild(analysisCard);

  // ── TRADE EXECUTION SECTION (Hidden initally) ──
  const executeCard = el("div", { id: "execute-card", class: "card", style: { display: "none" } });
  executeCard.appendChild(el("div", { class: "card-title", text: "📝 ORDER DETAILS", style: { marginBottom: "16px", color: "var(--text-secondary)" } }));

  const form = el("form", {
    on: {
      submit: async (e) => {
        e.preventDefault();
        const payload = {
          symbol: $("#analyze-symbol").value.trim().toUpperCase(),
          action: $("#trade-action").value,
          quantity: parseFloat($("#trade-qty").value),
          price: parseFloat($("#trade-price").value),
          order_type: $("#trade-order").value,
          limit_price: parseFloat($("#trade-limit").value) || null,
          stop_price: parseFloat($("#trade-stop").value) || null,
          asset_type: $("#analyze-asset").value,
          option_strike: parseFloat($("#analyze-strike").value) || null,
          option_expiry: $("#analyze-expiry").value || null,
          region: $("#trade-region").value,
        };

        if (!payload.symbol || !payload.quantity || !payload.price) {
          return toast("Symbol, quantity, and execution price are required.", "error");
        }

        const confirmMsg = `Execute ${payload.action} for ${payload.quantity} ${payload.symbol} @ $${payload.price} (${payload.order_type})?`;
        if (!(await confirm(confirmMsg))) return;

        const res = await api.post("manual-trade", payload);
        if (res && res.ok) {
          toast(`Trade submitted successfully! ID: ${res.order_id}`, "success");
          form.reset();
          $("#execute-card").style.display = "none";
          $("#analysis-result-box").style.display = "none";
        } else {
          toast("Failed to submit trade.", "error");
        }
      }
    }
  });

  const row1 = el("div", { style: { display: "flex", gap: "12px", marginBottom: "12px" } });
  row1.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Action", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("select", { id: "trade-action", class: "settings-input", style: { width: "100%" } }, [
      el("option", { value: "BUY", text: "BUY" }),
      el("option", { value: "SELL", text: "SELL" }),
    ])
  ]));
  row1.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Quantity", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "trade-qty", class: "settings-input", type: "number", step: "0.000001", required: true, style: { width: "100%" } })
  ]));
  row1.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Est. Execution Price", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "trade-price", class: "settings-input", type: "number", step: "0.01", required: true, style: { width: "100%" } })
  ]));
  form.appendChild(row1);

  const row2 = el("div", { style: { display: "flex", gap: "12px", marginBottom: "16px" } });
  row2.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Region", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("select", { id: "trade-region", class: "settings-input", style: { width: "100%" } }, [
      el("option", { value: "US", text: "US (USD)" }),
      el("option", { value: "IN", text: "IN (INR)" }),
    ])
  ]));
  row2.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Order Type", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("select", { id: "trade-order", class: "settings-input", style: { width: "100%" } }, [
      el("option", { value: "MARKET", text: "Market" }),
      el("option", { value: "LIMIT", text: "Limit" }),
      el("option", { value: "STOP", text: "Stop Loss" }),
    ])
  ]));
  row2.appendChild(el("div", { style: { flex: 1 } }, [
    el("label", { text: "Limit / Stop Price", style: { display: "block", marginBottom: "4px", fontSize: "12px", fontWeight: "bold" } }),
    el("input", { id: "trade-limit", class: "settings-input", type: "number", step: "0.01", style: { width: "100%" }, placeholder: "Optional target" })
  ]));
  form.appendChild(row2);

  form.appendChild(el("button", { class: "btn btn--primary", type: "submit", text: "Submit Order", style: { width: "100%", padding: "12px" } }));
  executeCard.appendChild(form);
  container.appendChild(executeCard);

  main.appendChild(container);

  // ── EVENT LISTENERS ──
  proceedBtn.onclick = () => {
    executeCard.style.display = "block";
    proceedBtn.style.display = "none";
    $("#trade-qty").focus();
  };

  analyzeBtn.onclick = async () => {
    const symbol = $("#analyze-symbol").value.trim().toUpperCase();
    if (!symbol) return toast("Symbol is required.", "error");

    const payload = {
      symbol: symbol,
      asset_type: $("#analyze-asset").value,
      option_strike: parseFloat($("#analyze-strike").value) || null,
      option_expiry: $("#analyze-expiry").value || null,
    };

    analyzeBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:14px;height:14px;margin:0 8px 0 0;border-width:2px"></span> Analyzing...';
    analyzeBtn.disabled = true;
    resultsBox.style.display = "none";
    executeCard.style.display = "none";
    proceedBtn.style.display = "block";

    try {
      // 1. Fetch AI Analysis
      const res = await api.post("analyze", payload);
      if (res && res.ok) {
        $("#trade-price").value = res.current_price || "";
        $("#trade-region").value = symbol.endsWith(".NS") || symbol.endsWith(".BO") ? "IN" : "US";

        // Auto-fill action based on decision
        if (res.decision.includes("BUY")) $("#trade-action").value = "BUY";
        else if (res.decision.includes("SELL")) $("#trade-action").value = "SELL";

        let decColor = res.decision.includes("BUY") ? "var(--success)" : res.decision.includes("SELL") ? "var(--danger)" : "var(--text-primary)";

        let optionHtml = '';
        if (res.recommended_option && res.recommended_option !== 'null') {
          const bidText = res.option_bid ? `$${res.option_bid.toFixed(2)}` : 'N/A';
          const askText = res.option_ask ? `$${res.option_ask.toFixed(2)}` : 'N/A';
          const assetType = res.recommended_option.includes('CALL') ? 'CALL' : 'PUT';

          optionHtml = `
            <div style="font-size: 13px; padding: 12px; margin-top: 12px; border: 1px solid var(--accent); border-radius: 6px; background: rgba(16, 185, 129, 0.05); cursor: pointer;"
                 onclick="
                   document.getElementById('analyze-asset').value = '${assetType}';
                   document.getElementById('opt-details-row').style.display = 'flex';
                   document.getElementById('analyze-strike').value = '${res.option_strike || ''}';
                   document.getElementById('analyze-expiry').value = '${res.option_expiry || ''}';
                   document.getElementById('trade-action').value = 'BUY';
                   document.getElementById('trade-price').value = '${res.option_ask || res.target_buy_price || ''}';
                   window.toast('Option inputs auto-filled! Please check Execution Form.', 'success');
                   document.getElementById('execute-card').scrollIntoView({ behavior: 'smooth' });
                 ">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <strong>💡 Option Insight (Click to structure trade)</strong>
                <span style="font-size: 11px; padding: 2px 6px; background: var(--bg-hover); border-radius: 4px;">Bid: ${bidText} | Ask: ${askText}</span>
              </div>
              <div>${res.recommended_option}</div>
            </div>`;
        }

        aiReportDiv.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
              <strong style="font-size: 16px;">AI Verdict: <span style="color: ${decColor}">${res.decision}</span></strong>
              <span class="badge badge--neutral">${(res.confidence * 100).toFixed(0)}% Confidence</span>
            </div>
            <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 12px;">
              ${res.reasoning || "No reasoning provided."}
            </p>
            <div style="font-size: 13px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
              <div><strong>Current Price:</strong> $${res.current_price}</div>
              <div><strong>Suggested Alloc:</strong> ${res.allocation_pct ? (res.allocation_pct * 100).toFixed(1) + '%' : 'N/A'}</div>
              <div><strong>Buy Target:</strong> ${res.target_buy_price ? '$' + res.target_buy_price : 'N/A'}</div>
              <div><strong>Sell Target:</strong> ${res.target_sell_price ? '$' + res.target_sell_price : 'N/A'}</div>
            </div>
            ${optionHtml}
          `;
      } else {
        aiReportDiv.innerHTML = `<p class="text-danger">Analysis Failed: ${res?.error || "Unknown error"}</p>`;
      }

      // 2. Fetch Chart Data in parallel visually
      const chartRes = await api.get(`chart/${symbol}?days=90`);

      const ctx = chartCanvas.getContext("2d");
      const w = chartContainer.clientWidth || 760;
      chartCanvas.width = w * 2; chartCanvas.height = 300 * 2;
      chartCanvas.style.width = w + "px"; chartCanvas.style.height = "300px";

      if (chartRes && !chartRes.error) {
        drawExecutionChart(chartCanvas, chartRes.prices, chartRes.trades);
      } else {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(2, 2);
        ctx.clearRect(0, 0, w, 300);
        ctx.fillStyle = "var(--text-tertiary)";
        ctx.font = "14px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Chart data unavailable.", w / 2, 150);
      }

      resultsBox.style.display = "block";

    } catch (e) {
      toast("Request Error", "error");
    } finally {
      analyzeBtn.innerHTML = "🧠 Get AI Analysis & Load Chart";
      analyzeBtn.disabled = false;
    }
  };
}
// ═══════════════════════════════════════════════════════════
//  VIEW: SETTINGS
// ═══════════════════════════════════════════════════════════
async function renderSettings() {
  const main = $("main");
  main.innerHTML = '<div class="loading-spinner">Loading settings…</div>';

  const data = await api.get("config");
  if (!data) { main.innerHTML = '<p class="text-muted">Failed to load configuration.</p>'; return; }

  const config = data.config;
  const defaults = data.defaults;
  main.innerHTML = "";

  const topRow = el("div", { class: "grid-2" });

  // Watchlists
  const wlCard = el("div", { class: "card" });
  wlCard.appendChild(el("div", { class: "card-title", text: "📋 WATCHLISTS" }));

  wlCard.appendChild(el("label", { text: "🇺🇸 US Tickers", style: { fontSize: "13px", fontWeight: 600, marginBottom: "4px", display: "block" } }));
  const usTA = el("textarea", {
    class: "settings-input",
    rows: "4",
    style: { width: "100%", marginBottom: "12px" },
  });
  usTA.value = config.US_TICKERS || defaults.us_tickers;
  wlCard.appendChild(usTA);

  wlCard.appendChild(el("label", { text: "🇮🇳 India Tickers", style: { fontSize: "13px", fontWeight: 600, marginBottom: "4px", display: "block" } }));
  const inTA = el("textarea", {
    class: "settings-input",
    rows: "4",
    style: { width: "100%", marginBottom: "12px" },
  });
  inTA.value = config.INDIA_TICKERS || defaults.india_tickers;
  wlCard.appendChild(inTA);
  topRow.appendChild(wlCard);

  // Risk & Capital
  const riskCard = el("div", { class: "card" });
  riskCard.appendChild(el("div", { class: "card-title", text: "🎯 RISK & CAPITAL" }));

  riskCard.appendChild(el("label", { text: "Max Allocation per Trade (%)", style: { fontSize: "13px", fontWeight: 600, display: "block", marginBottom: "4px" } }));
  const allocInput = el("input", { class: "settings-input", type: "number", value: config.RISK_MAX_ALLOC_PCT || "25", style: { width: "100%", marginBottom: "12px" } });
  riskCard.appendChild(allocInput);

  riskCard.appendChild(el("label", { text: "Max Risk per Trade (%)", style: { fontSize: "13px", fontWeight: 600, display: "block", marginBottom: "4px" } }));
  const riskInput = el("input", { class: "settings-input", type: "number", value: config.RISK_MAX_RISK_PCT || "5", style: { width: "100%", marginBottom: "12px" } });
  riskCard.appendChild(riskInput);

  riskCard.appendChild(el("label", { text: "Trading Style", style: { fontSize: "13px", fontWeight: 600, display: "block", marginBottom: "4px" } }));
  const styleSelect = el("select", { class: "settings-input", style: { width: "100%", marginBottom: "12px" } }, [
    el("option", { value: "intraday", text: "Intraday (Aggressive)" }),
    el("option", { value: "short_term", text: "Short Term (Swing)" }),
    el("option", { value: "long_term", text: "Long Term (Trend)" }),
    el("option", { value: "optimistic", text: "Optimistic" })
  ]);
  styleSelect.value = config.TRADING_STYLE || defaults.trading_style;
  riskCard.appendChild(styleSelect);

  riskCard.appendChild(el("div", { class: "text-muted", style: { fontSize: "12px", lineHeight: "1.6" }, html: `Mode: <strong>${defaults.trading_mode.toUpperCase()}</strong><br>US Capital: <strong>${fmtCurrency(defaults.us_max_capital, "US")}</strong> · IN Capital: <strong>${fmtCurrency(defaults.india_max_capital, "IN")}</strong>` }));
  topRow.appendChild(riskCard);
  main.appendChild(topRow);

  // Save button
  const saveBtn = el("button", {
    class: "btn btn--primary",
    html: "💾 Save Configuration",
    on: {
      click: async () => {
        const updates = [
          { key: "US_TICKERS", value: usTA.value.trim() },
          { key: "INDIA_TICKERS", value: inTA.value.trim() },
          { key: "RISK_MAX_ALLOC_PCT", value: allocInput.value },
          { key: "RISK_MAX_RISK_PCT", value: riskInput.value },
          { key: "TRADING_STYLE", value: styleSelect.value },
        ];
        for (const u of updates) await api.post("config", u);
        toast("Configuration saved!", "success");
      }
    },
  });
  main.appendChild(el("div", { style: { marginTop: "12px" } }, [saveBtn]));

  // Danger Zone
  const danger = el("div", { class: "card", style: { marginTop: "24px", borderColor: "var(--danger)" } });
  danger.appendChild(el("div", { class: "card-title", text: "⚠️ DANGER ZONE", style: { color: "var(--danger)" } }));
  const dangerBtns = el("div", { style: { display: "flex", gap: "12px", flexWrap: "wrap" } });
  [
    { label: "🗑 Clear Trades", endpoint: "config/clear-trades", msg: "Clear ALL trade history? This cannot be undone." },
    { label: "🗑 Clear Logs", endpoint: "config/clear-logs", msg: "Clear ALL activity logs? This cannot be undone." },
    { label: "🔥 Factory Reset", endpoint: "config/factory-reset", msg: "Delete ALL data and reset to defaults? This CANNOT be undone." },
  ].forEach(action => {
    dangerBtns.appendChild(el("button", {
      class: "btn btn--danger",
      html: action.label,
      on: {
        click: async () => {
          const ok = await confirm(action.msg);
          if (!ok) return;
          await api.post(action.endpoint, {});
          toast(`${action.label.replace(/🗑 |🔥 /g, "")} complete`, "success");
          renderSettings();
        }
      },
    }));
  });
  danger.appendChild(dangerBtns);
  main.appendChild(danger);
}


// ═══════════════════════════════════════════════════════════
//  CANVAS CHARTS
// ═══════════════════════════════════════════════════════════
function drawDonut(canvas, values, colors, centerText) {
  const w = canvas.parentElement.clientWidth - 40;
  const h = 240;
  canvas.width = w * 2; canvas.height = h * 2;
  canvas.style.width = w + "px"; canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);

  const resolvedColors = colors.map(c =>
    c.startsWith("var(") ? getComputedStyle(document.documentElement).getPropertyValue(c.slice(4, -1)).trim() : c
  );

  const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - 20;
  const total = values.reduce((a, b) => a + b, 0);
  if (total === 0) return;

  let angle = -Math.PI / 2;
  values.forEach((v, i) => {
    const slice = (v / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, angle, angle + slice);
    ctx.arc(cx, cy, r * 0.6, angle + slice, angle, true);
    ctx.closePath();
    ctx.fillStyle = resolvedColors[i];
    ctx.fill();
    angle += slice;
  });

  // Center text
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text-primary").trim();
  ctx.font = "bold 18px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(centerText, cx, cy);
}

function drawLineChart(canvas, data) {
  const w = canvas.parentElement.clientWidth - 40;
  const h = 220;
  canvas.width = w * 2; canvas.height = h * 2;
  canvas.style.width = w + "px"; canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);

  const style = getComputedStyle(document.documentElement);
  const textColor = style.getPropertyValue("--text-muted").trim();
  const gridColor = style.getPropertyValue("--border").trim();
  const accentColor = style.getPropertyValue("--accent").trim();

  const pad = { top: 16, right: 16, bottom: 36, left: 48 };
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;

  const values = data.map(d => d.latency_ms);
  const maxVal = Math.max(...values, 1);

  // Grid
  ctx.strokeStyle = gridColor; ctx.lineWidth = 0.5; ctx.setLineDash([3, 3]);
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ch / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
    ctx.fillStyle = textColor; ctx.font = "10px Inter, sans-serif"; ctx.textAlign = "right";
    ctx.fillText(Math.round(maxVal - (maxVal / 4) * i).toLocaleString(), pad.left - 6, y + 4);
  }
  ctx.setLineDash([]);

  // X labels
  const step = Math.max(1, Math.floor(data.length / 6));
  ctx.textAlign = "center";
  for (let i = 0; i < data.length; i += step) {
    const x = pad.left + (i / (data.length - 1 || 1)) * cw;
    ctx.fillText(fmtTime(data[i].time), x, h - 6);
  }

  // Line
  ctx.strokeStyle = accentColor; ctx.lineWidth = 2; ctx.beginPath();
  values.forEach((v, i) => {
    const x = pad.left + (i / (values.length - 1 || 1)) * cw;
    const y = pad.top + ch - (v / maxVal) * ch;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function drawExecutionChart(canvas, prices, trades) {
  const ctx = canvas.getContext("2d");
  const w = canvas.parentElement.clientWidth;
  const h = 300;
  canvas.width = w * 2; canvas.height = h * 2;
  canvas.style.width = w + "px"; canvas.style.height = h + "px";
  // Reset transform from earlier
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(2, 2);
  ctx.clearRect(0, 0, w, h);

  if (!prices || prices.length < 2) {
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text-tertiary");
    ctx.font = "14px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Not enough price data.", w / 2, h / 2);
    return;
  }

  const pad = { top: 30, right: 60, bottom: 40, left: 20 };
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;

  const style = getComputedStyle(document.documentElement);
  const textColor = style.getPropertyValue("--text-tertiary").trim() || "#94a3b8";
  const gridColor = style.getPropertyValue("--border").trim() || "#e2e8f0";
  const accentColor = style.getPropertyValue("--primary").trim() || "#10b981"; // use primary for chart
  const buyColor = style.getPropertyValue("--success") || "#10b981";
  const sellColor = style.getPropertyValue("--danger") || "#ef4444";

  const allVals = prices.map(p => p.close);
  const minVal = Math.min(...allVals) * 0.98;
  const maxVal = Math.max(...allVals) * 1.02;
  const range = maxVal - minVal;

  // Grid lines
  ctx.strokeStyle = gridColor; ctx.lineWidth = 0.5; ctx.setLineDash([3, 3]);
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ch / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
    ctx.fillStyle = textColor; ctx.font = "10px Inter, sans-serif"; ctx.textAlign = "left";
    const label = (maxVal - (range / 4) * i).toFixed(2);
    ctx.fillText(label, w - pad.right + 8, y + 4);
  }
  ctx.setLineDash([]);

  // X-axis (Dates)
  const step = Math.max(1, Math.floor(prices.length / 6));
  ctx.fillStyle = textColor; ctx.font = "10px Inter, sans-serif"; ctx.textAlign = "center";
  for (let i = 0; i < prices.length; i += step) {
    const x = pad.left + (i / (prices.length - 1 || 1)) * cw;
    ctx.fillText(prices[i].date, x, h - 8);
  }

  // Draw Price Line
  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 2;
  ctx.beginPath();
  prices.forEach((p, i) => {
    const x = pad.left + (i / (prices.length - 1 || 1)) * cw;
    const y = pad.top + ch - ((p.close - minVal) / range) * ch;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw Trades
  if (trades && trades.length > 0) {
    trades.forEach(t => {
      // Best effort alignment: Find closest date index
      const tDate = t.timestamp.split("T")[0].split(" ")[0];
      let closestIdx = -1;
      let minDiff = Infinity;
      const tTime = new Date(tDate).getTime();

      prices.forEach((p, i) => {
        const pTime = new Date(p.date).getTime();
        const diff = Math.abs(pTime - tTime);
        if (diff < minDiff) { minDiff = diff; closestIdx = i; }
      });

      if (closestIdx !== -1) {
        const x = pad.left + (closestIdx / (prices.length - 1 || 1)) * cw;
        const ptPrice = t.price || prices[closestIdx].close;
        const clampedPrice = Math.max(minVal, Math.min(maxVal, ptPrice));
        const y = pad.top + ch - ((clampedPrice - minVal) / range) * ch;

        ctx.beginPath();
        ctx.arc(x, y, 6, 0, 2 * Math.PI);
        ctx.fillStyle = t.action.toUpperCase().includes("BUY") ? buyColor : sellColor;
        ctx.fill();
        ctx.strokeStyle = "var(--bg-card)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    });

    // Legend for trades
    ctx.fillStyle = textColor;
    ctx.textAlign = "left";
    ctx.fillText("● BUY", pad.left, pad.top - 10);
    ctx.fillStyle = sellColor;
    ctx.fillText("● SELL", pad.left + 45, pad.top - 10);
  }
}

// ═══════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initMobile();
  pollStatus();
  initRouter();

  // Auto-refresh every 30s
  setInterval(pollStatus, 30000);

  // Refresh button
  const refreshBtn = $(".refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", handleRoute);

  // Kill switch
  const killSwitch = $(".kill-switch input");
  if (killSwitch) {
    killSwitch.addEventListener("change", async () => {
      await api.post("config", {
        key: "TRADING_STATUS",
        value: killSwitch.checked ? "ACTIVE" : "PAUSED",
      });
      toast(killSwitch.checked ? "Trading activated" : "Trading paused", killSwitch.checked ? "success" : "warning");
    });
  }
});
