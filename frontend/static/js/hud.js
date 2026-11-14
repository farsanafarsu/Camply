/* Camply home page ("HUD" edition) behaviour.
 * - Nav: mobile menu, solid background once scrolled, right-edge scroll progress.
 * - Hero: the 3D emblem leans toward the pointer.
 * - Cards fade up as they scroll into view.
 * - GST demo: switching the client's state swaps CGST + SGST for IGST.
 * - Live Indian Standard Time clock.
 * Everything still reads fine without JavaScript.
 */
(function () {
  "use strict";
  var root = document.querySelector(".hud");
  if (!root) return;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hover = window.matchMedia("(hover: hover)").matches;

  // Navigation
  var nav = root.querySelector("[data-hud-nav]");
  var menu = root.querySelector("[data-hud-menu]");
  if (nav && menu) {
    menu.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      menu.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.querySelectorAll(".hud-mobile a").forEach(function (a) {
      a.addEventListener("click", function () { nav.classList.remove("is-open"); menu.setAttribute("aria-expanded", "false"); });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { nav.classList.remove("is-open"); menu.setAttribute("aria-expanded", "false"); }
    });
  }
  var progress = root.querySelector("[data-hud-progress]");
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var y = window.scrollY;
      if (nav) nav.classList.toggle("is-scrolled", y > 8);
      if (progress) {
        var max = document.documentElement.scrollHeight - window.innerHeight;
        progress.parentNode.style.setProperty("--progress", max > 0 ? (y / max).toFixed(4) : 0);
      }
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Hero emblem follows the pointer a little
  var core = root.querySelector("[data-core]");
  var hero = root.querySelector(".hero");
  if (core && hero && hover && !reduce) {
    var stage = core.querySelector(".core-stage");
    hero.addEventListener("pointermove", function (e) {
      var r = hero.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5;
      var y = (e.clientY - r.top) / r.height - 0.5;
      stage.style.setProperty("--ry", (x * 26).toFixed(2) + "deg");
      stage.style.setProperty("--rx", (y * -18).toFixed(2) + "deg");
    });
    hero.addEventListener("pointerleave", function () {
      stage.style.removeProperty("--ry");
      stage.style.removeProperty("--rx");
    });
  }

  // Reveal on scroll
  var items = root.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && !reduce && items.length) {
    root.classList.add("js-reveal");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var siblings = Array.prototype.indexOf.call(el.parentNode.children, el);
        el.style.transitionDelay = Math.min(siblings, 6) * 60 + "ms";
        el.classList.add("is-in");
        setTimeout(function () { el.style.transitionDelay = ""; }, 1200);
        io.unobserve(el);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.1 });
    items.forEach(function (el) { io.observe(el); });
  }

  // GST demo
  var gst = root.querySelector("[data-gst-demo]");
  if (gst) {
    var clients = { "Kerala": "Kovalam Bay Resorts", "Tamil Nadu": "Lumen Dental Care" };
    gst.addEventListener("click", function (e) {
      var button = e.target.closest("[data-state]");
      if (!button) return;
      var state = button.getAttribute("data-state");
      var intra = state === "Kerala";  // the agency is registered in Kerala
      gst.querySelectorAll("[data-state]").forEach(function (b) {
        var on = b === button;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
      });
      gst.querySelectorAll("[data-tax]").forEach(function (row) {
        row.hidden = (row.getAttribute("data-tax") === "intra") !== intra;
      });
      gst.querySelector("[data-gst-place]").textContent = state;
      gst.querySelector("[data-gst-client]").textContent = clients[state];
      gst.querySelector("[data-gst-kind]").textContent = intra ? "Intra-state" : "Inter-state";
      gst.querySelector("[data-gst-rule]").textContent = intra ? "CGST + SGST" : "IGST";
    });
  }

  // Invoice tilts toward the pointer
  var tilt = root.querySelector("[data-tilt]");
  if (tilt && hover && !reduce) {
    tilt.addEventListener("pointermove", function (e) {
      var r = tilt.getBoundingClientRect();
      tilt.style.setProperty("--ry", (((e.clientX - r.left) / r.width - 0.5) * 12).toFixed(2) + "deg");
      tilt.style.setProperty("--rx", (((e.clientY - r.top) / r.height - 0.5) * -10).toFixed(2) + "deg");
    });
    tilt.addEventListener("pointerleave", function () {
      tilt.style.removeProperty("--ry");
      tilt.style.removeProperty("--rx");
    });
  }

  // Live IST clock
  var clock = root.querySelector("[data-ist-clock]");
  if (clock && window.Intl) {
    var fmt = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true });
    var tick = function () {
      var parts = fmt.formatToParts(new Date());
      var get = function (t) { var p = parts.find(function (x) { return x.type === t; }); return p ? p.value : ""; };
      clock.innerHTML = get("hour") + ":" + get("minute") + " <small>" + get("dayPeriod").toUpperCase() + " IST</small>";
    };
    tick();
    setInterval(tick, 15000);
  }
})();
