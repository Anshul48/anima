// ANIMA Site A shared script. Vanilla JS, no dependencies.
// Progressive enhancement only: every page is fully readable with JS off.
// Honors prefers-reduced-motion (renders final state, no animation).
(function () {
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Mark current nav link.
  var here = location.pathname.split("/").pop() || "index.html";
  var navs = document.querySelectorAll("a.nav");
  for (var i = 0; i < navs.length; i++) {
    if (navs[i].getAttribute("href") === here) navs[i].setAttribute("aria-current", "page");
  }

  // Earned counters: animate only if every value is already in the DOM text.
  var counters = document.querySelectorAll("[data-count]");
  for (var c = 0; c < counters.length; c++) {
    (function (el) {
      var target = parseInt(el.getAttribute("data-count"), 10);
      if (isNaN(target)) return;
      if (reduce) { el.textContent = target.toLocaleString("en-US"); return; }
      var t0 = null, dur = 900;
      function frame(t) {
        if (!t0) t0 = t;
        var p = Math.min(1, (t - t0) / dur), v = Math.round(target * p);
        el.textContent = v.toLocaleString("en-US");
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    })(counters[c]);
  }

  // Generic step replay: lights <li> items in order when Play is pressed.
  var stages = document.querySelectorAll("[data-replay]");
  for (var s = 0; s < stages.length; s++) {
    (function (stage) {
      var items = stage.querySelectorAll("ol.steps li");
      var play = stage.querySelector("[data-play]");
      var reset = stage.querySelector("[data-reset]");
      if (!play || items.length === 0) return;
      function showAll() {
        for (var k = 0; k < items.length; k++) items[k].classList.add("lit");
      }
      function clear() {
        for (var k = 0; k < items.length; k++) items[k].classList.remove("lit");
      }
      if (reduce) { showAll(); play.disabled = true; if (reset) reset.disabled = true; return; }
      var idx = 0, timer = null;
      play.addEventListener("click", function () {
        if (timer) return;
        timer = setInterval(function () {
          if (idx >= items.length) { clearInterval(timer); timer = null; return; }
          items[idx].classList.add("lit"); idx++;
        }, 700);
      });
      if (reset) reset.addEventListener("click", function () {
        if (timer) { clearInterval(timer); timer = null; }
        idx = 0; clear();
      });
    })(stages[s]);
  }
})();
