/* Camply front-end behaviour: theme, navigation, charts. No build step. */
(function () {
  "use strict";

  // ----- Theme (light / dark / system) -----
  function storedTheme() {
    try { return localStorage.getItem("camply-theme"); } catch (e) { return null; }
  }
  function effectiveTheme() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-theme-toggle]");
    if (!toggle) return;
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("camply-theme", next); } catch (e) { /* private mode */ }
    renderCharts();
  });

  // ----- Mobile navigation -----
  document.addEventListener("click", function (event) {
    var app = document.querySelector(".app");
    if (!app) return;
    if (event.target.closest("[data-nav-toggle]")) {
      app.classList.toggle("nav-open");
    } else if (app.classList.contains("nav-open") && !event.target.closest(".sidebar")) {
      app.classList.remove("nav-open");
    }
  });

  // ----- Auto-submit filter forms -----
  document.addEventListener("change", function (event) {
    var form = event.target.closest("form[data-autosubmit]");
    if (!form) return;
    var custom = form.querySelector("[data-custom-range]");
    if (event.target.name === "range" && custom) {
      custom.hidden = event.target.value !== "custom";
      if (event.target.value === "custom") return;
    }
    form.submit();
  });

  // ----- Show / hide password -----
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-password-toggle]");
    if (!button) return;
    var input = document.getElementById(button.getAttribute("data-password-toggle"));
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", show ? "true" : "false");
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    button.innerHTML = '<i data-lucide="' + (show ? "eye-off" : "eye") + '"></i>';
    if (window.lucide) window.lucide.createIcons();
    input.focus();
  });

  // ----- Confirm before irreversible or spend-changing actions -----
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-print]")) window.print();
  });

  // ----- Ledger form: show adjustment direction only for adjustments -----
  document.addEventListener("change", function (event) {
    if (event.target.id !== "id_kind") return;
    var row = document.querySelector("[data-adjustment-only]");
    if (row) row.hidden = event.target.value !== "adjustment";
  });

  // ----- Charts -----
  var charts = [];
  var inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

  function compactInr(value) {
    var v = Math.abs(value);
    if (v >= 1e7) return "₹" + +(value / 1e7).toFixed(2) + "Cr";
    if (v >= 1e5) return "₹" + +(value / 1e5).toFixed(2) + "L";
    if (v >= 1e3) return "₹" + +(value / 1e3).toFixed(1) + "K";
    return "₹" + value;
  }
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function shortDate(iso) {
    var d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  }
  function readData(id) {
    var el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }
  function hexToRgba(hex, alpha) {
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
  }

  function baseOptions() {
    var text = css("--text-muted");
    var grid = css("--border");
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text"),
          borderColor: grid, borderWidth: 1, padding: 10, boxPadding: 4,
          callbacks: { label: function (ctx) { return " " + ctx.dataset.label + ": " + inr.format(ctx.parsed.y); } }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: text, maxTicksLimit: 7, callback: function (v) { return shortDate(this.getLabelForValue(v)); } } },
        y: { grid: { color: grid }, border: { display: false }, ticks: { color: text, callback: compactInr } }
      }
    };
  }

  function renderCharts() {
    if (!window.Chart) return;
    charts.forEach(function (c) { c.destroy(); });
    charts = [];

    var trendEl = document.getElementById("spend-trend-chart");
    var trend = readData("spend-trend-data");
    if (trendEl && trend) {
      charts.push(new Chart(trendEl, {
        type: "line",
        data: {
          labels: trend.labels,
          datasets: trend.series.map(function (s) {
            return {
              label: s.label, data: s.data, borderColor: s.color, backgroundColor: hexToRgba(s.color, 0.08),
              fill: true, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2
            };
          })
        },
        options: baseOptions()
      }));
    }

    var donutEl = document.getElementById("platform-donut");
    var donut = readData("platform-donut-data");
    if (donutEl && donut) {
      charts.push(new Chart(donutEl, {
        type: "doughnut",
        data: {
          labels: donut.map(function (d) { return d.label; }),
          datasets: [{ data: donut.map(function (d) { return d.value; }), backgroundColor: donut.map(function (d) { return d.color; }), borderColor: css("--surface"), borderWidth: 3, hoverOffset: 4 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: "72%",
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (ctx) { return " " + ctx.label + ": " + inr.format(ctx.parsed); } } } }
        }
      }));
    }

    var campaignEl = document.getElementById("campaign-chart");
    var series = readData("campaign-series-data");
    if (campaignEl && series) {
      var opts = baseOptions();
      opts.scales.y1 = { position: "right", grid: { display: false }, border: { display: false }, ticks: { color: css("--text-muted") } };
      opts.plugins.tooltip.callbacks.label = function (ctx) {
        return " " + ctx.dataset.label + ": " + (ctx.dataset.yAxisID === "y1" ? ctx.parsed.y : inr.format(ctx.parsed.y));
      };
      charts.push(new Chart(campaignEl, {
        type: "bar",
        data: {
          labels: series.labels,
          datasets: [
            { type: "bar", label: "Spend", data: series.spend, backgroundColor: hexToRgba("#FF6B35", 0.75), borderRadius: 4, yAxisID: "y" },
            { type: "line", label: "Leads", data: series.leads, borderColor: css("--positive"), backgroundColor: css("--positive"), tension: 0.35, pointRadius: 0, borderWidth: 2, yAxisID: "y1" }
          ]
        },
        options: opts
      }));
    }
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    if (!storedTheme()) renderCharts();
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (window.lucide) window.lucide.createIcons();
    renderCharts();
  });
})();
