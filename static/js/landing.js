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

  // Reveal the comparison rows as they scroll into view.
  if ("IntersectionObserver" in window && !reduce.matches) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); } });
    }, { threshold: 0.2 });
    document.querySelectorAll(".change-row").forEach(function (el) {
      el.classList.add("reveal");
      io.observe(el);
    });
  }
})();
