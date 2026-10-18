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

  /* Gate-flow animation (unified from site-b.js): step .gate children
     pending -> active -> done inside [data-gate-flow] / [data-ribbon].
     Decorative only; values already in the DOM. No-JS shows final state. */
  function stepGates(flow, delay) {
    var gates = flow.querySelectorAll(".gate");
    if (!gates.length) return;
    var k;
    if (reduce) {
      for (k = 0; k < gates.length; k++) gates[k].setAttribute("data-state", "done");
      return;
    }
    var i = 0, timer = null;
    for (k = 0; k < gates.length; k++) gates[k].setAttribute("data-state", "pending");
    timer = setInterval(function () {
      if (i > 0) gates[i - 1].setAttribute("data-state", "done");
      if (i >= gates.length) { clearInterval(timer); return; }
      gates[i].setAttribute("data-state", "active");
      i++;
    }, delay);
  }
  var flows = document.querySelectorAll("[data-gate-flow]");
  for (var f = 0; f < flows.length; f++) stepGates(flows[f], 700);
  var ribbons = document.querySelectorAll("[data-ribbon]");
  for (var r = 0; r < ribbons.length; r++) stepGates(ribbons[r], 800);

  /* Synthetic screen mock (unified from site-b.js): draws abstract boxes
     on #synthetic-screen. Purely synthetic — no real screenshots. */
  (function syntheticMock() {
    var c = document.getElementById("synthetic-screen");
    if (!c) return;
    var ctx = c.getContext("2d");
    var W = c.width, H = c.height;
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#273449";
    ctx.fillRect(0, 0, W, 22);
    var seed = 42;
    function rnd() {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    }
    var routed = [1, 3];
    for (var i = 0; i < 6; i++) {
      var x = 20 + rnd() * (W - 140), y = 40 + rnd() * (H - 100);
      var w = 50 + rnd() * 70, h = 24 + rnd() * 30;
      ctx.strokeStyle = routed.indexOf(i) >= 0 ? "#f59e0b" : "#14b8a6";
      ctx.lineWidth = routed.indexOf(i) >= 0 ? 3 : 1.5;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px sans-serif";
      ctx.fillText("box" + i + " r=" + (0.5 + rnd() * 0.5).toFixed(2), x, y - 3);
    }
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, H - 56, W, 56);
    ctx.fillStyle = "#f59e0b";
    ctx.font = "11px sans-serif";
    ctx.fillText("routed crops: box1, box3 -> VLM (synthetic mock)", 12, H - 34);
    ctx.fillStyle = "#94a3b8";
    ctx.fillText("full frame never sent (concept diagram)", 12, H - 18);
  })();
})();
