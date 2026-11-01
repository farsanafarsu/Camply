/* Home page scroll story: chaos -> "It's time to change" -> Introducing Camply.
 *
 * The section is pinned while the visitor scrolls through it, and progress (0..1) drives
 * four CSS variables: --p (overall), --before, --mid and --after (panel visibility).
 * Without JS, on small screens or with reduced motion, the panels simply stack.
 */
(function () {
  "use strict";
  var story = document.querySelector("[data-story]");
  if (!story) return;

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var wide = window.matchMedia("(min-width: 900px) and (min-height: 560px)");
  var ticking = false;

  function clamp(v) { return Math.max(0, Math.min(1, v)); }
  // Smooth 0..1 ramp between a and b.
  function ramp(p, a, b) { var t = clamp((p - a) / (b - a)); return t * t * (3 - 2 * t); }

  function update() {
    ticking = false;
    var rect = story.getBoundingClientRect();
    var travel = story.offsetHeight - window.innerHeight;
    var p = travel > 0 ? clamp(-rect.top / travel) : 1;
    var s = story.style;
    s.setProperty("--p", ramp(p, 0.08, 0.62).toFixed(4));
    s.setProperty("--before", (1 - ramp(p, 0.12, 0.42)).toFixed(4));
    s.setProperty("--mid", Math.min(ramp(p, 0.3, 0.44), 1 - ramp(p, 0.5, 0.62)).toFixed(4));
    s.setProperty("--after", ramp(p, 0.56, 0.78).toFixed(4));
    s.setProperty("--progress", p.toFixed(4));
    story.classList.toggle("is-after", p > 0.6);
    story.classList.toggle("is-done", p > 0.97);
  }

  function onScroll() {
    if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
  }

  function setMode() {
    var live = wide.matches && !reduce.matches;
    story.classList.toggle("is-live", live);
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", onScroll);
    if (live) {
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll);
      update();
    } else {
      ["--p", "--before", "--mid", "--after", "--progress"].forEach(function (v) { story.style.removeProperty(v); });
    }
  }

  // 3D stack follows the pointer a little (desktop only, not with reduced motion).
  var hub = document.querySelector("[data-hub]");
  if (hub && window.matchMedia("(hover: hover)").matches && !reduce.matches) {
    hub.addEventListener("pointermove", function (e) {
      var r = hub.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5;
      var y = (e.clientY - r.top) / r.height - 0.5;
      hub.style.setProperty("--tilt-x", (x * 12).toFixed(2) + "deg");
      hub.style.setProperty("--tilt-y", (y * -10).toFixed(2) + "deg");
    });
    hub.addEventListener("pointerleave", function () {
      hub.style.removeProperty("--tilt-x");
      hub.style.removeProperty("--tilt-y");
    });
  }

  // "See the better way": glide to the reveal instead of jumping to the anchor.
  document.addEventListener("click", function (e) {
    var link = e.target.closest("[data-story-jump]");
    if (!link || !story.classList.contains("is-live")) return;
    e.preventDefault();
    var travel = story.offsetHeight - window.innerHeight;
    window.scrollTo({ top: story.offsetTop + travel * 0.82, behavior: "smooth" });
  });

  [reduce, wide].forEach(function (mq) {
    if (mq.addEventListener) mq.addEventListener("change", setMode); else mq.addListener(setMode);
  });
  setMode();

  // GST demo: switching the client's state swaps CGST + SGST for IGST on the invoice.
  var gst = document.querySelector("[data-gst-demo]");
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

  // Invoice stack tilts toward the pointer.
  var tilt = document.querySelector("[data-tilt]");
  if (tilt && window.matchMedia("(hover: hover)").matches && !reduce.matches) {
    tilt.addEventListener("pointermove", function (e) {
      var r = tilt.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      tilt.querySelectorAll(".invoice-sheet").forEach(function (sheet) {
        sheet.style.setProperty("--ry", (x * 18).toFixed(2) + "deg");
        sheet.style.setProperty("--rx", (y * -14).toFixed(2) + "deg");
      });
    });
    tilt.addEventListener("pointerleave", function () {
      tilt.querySelectorAll(".invoice-sheet").forEach(function (sheet) {
        sheet.style.removeProperty("--ry");
        sheet.style.removeProperty("--rx");
      });
    });
  }

  // Live Indian Standard Time on the clock tile.
  var clock = document.querySelector("[data-ist-clock]");
  if (clock) {
    var fmt = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true });
    var tick = function () {
      var parts = fmt.formatToParts(new Date());
      var get = function (t) { var p = parts.find(function (x) { return x.type === t; }); return p ? p.value : ""; };
      clock.innerHTML = get("hour") + ":" + get("minute") + " <small>" + get("dayPeriod").toUpperCase() + " IST</small>";
    };
    tick();
    setInterval(tick, 15000);
  }

  // Flip cards: each turns from "Before" to "With Camply" as it rises from the bottom
  // of the screen to the middle, and lifts toward the viewer mid-turn.
  var flips = Array.prototype.slice.call(document.querySelectorAll("[data-flip]"));
  if (flips.length && !reduce.matches) {
    var flipTicking = false;
    var updateFlips = function () {
      flipTicking = false;
      var vh = window.innerHeight, start = vh * 0.95, end = vh * 0.5;
      flips.forEach(function (card) {
        var t = ramp(clamp((start - card.getBoundingClientRect().top) / (start - end)), 0, 1);
        card.style.setProperty("--flip", (t * 180).toFixed(1) + "deg");
        card.style.setProperty("--lift", (Math.sin(t * Math.PI) * 70).toFixed(1) + "px");
      });
    };
    var onFlipScroll = function () {
      if (!flipTicking) { flipTicking = true; window.requestAnimationFrame(updateFlips); }
    };
    window.addEventListener("scroll", onFlipScroll, { passive: true });
    window.addEventListener("resize", onFlipScroll);
    updateFlips();
  }
})();
