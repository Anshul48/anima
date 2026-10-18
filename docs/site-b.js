/* site-b.js — small progressive-enhancement helpers for site B pages.
   No-JS content is complete; this only animates gate flow / draws
   synthetic mocks. Honors prefers-reduced-motion. */
(function () {
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Gate-flow animation: elements with [data-gate-flow] contain
     .gate children; JS steps them pending -> active -> done. */
  function gateFlows() {
    var flows = document.querySelectorAll("[data-gate-flow]");
    flows.forEach(function (flow) {
      var gates = flow.querySelectorAll(".gate");
      if (!gates.length || reduce) {
        gates.forEach(function (g) { g.setAttribute("data-state", "done"); });
        return;
      }
      var i = 0;
      gates.forEach(function (g) { g.setAttribute("data-state", "pending"); });
      var timer = setInterval(function () {
        if (i > 0) gates[i - 1].setAttribute("data-state", "done");
        if (i >= gates.length) { clearInterval(timer); return; }
        gates[i].setAttribute("data-state", "active");
        i++;
      }, 700);
    });
  }

  /* Synthetic screen mock for reflex page: draws abstract boxes on canvas.
     Purely synthetic — no real screenshots. */
  function syntheticMock() {
    var c = document.getElementById("synthetic-screen");
    if (!c) return;
    var ctx = c.getContext("2d");
    var W = c.width, H = c.height;
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, W, H);
    /* fake window chrome */
    ctx.fillStyle = "#273449";
    ctx.fillRect(0, 0, W, 22);
    /* deterministic pseudo-random boxes (seeded) */
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
    /* routed crops strip */
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, H - 56, W, 56);
    ctx.fillStyle = "#f59e0b";
    ctx.font = "11px sans-serif";
    ctx.fillText("routed crops: box1, box3 -> VLM (synthetic mock)", 12, H - 34);
    ctx.fillStyle = "#94a3b8";
    ctx.fillText("full frame never sent (concept diagram)", 12, H - 18);
  }

  /* Timeline ribbon progress for entorhinal page (attribute-driven). */
  function ribbon() {
    var steps = document.querySelectorAll("[data-ribbon] .gate");
    if (!steps.length) return;
    if (reduce) {
      steps.forEach(function (s) { s.setAttribute("data-state", "done"); });
      return;
    }
    var i = 0;
    steps.forEach(function (s) { s.setAttribute("data-state", "pending"); });
    var timer = setInterval(function () {
      if (i > 0) steps[i - 1].setAttribute("data-state", "done");
      if (i >= steps.length) { clearInterval(timer); return; }
      steps[i].setAttribute("data-state", "active");
      i++;
    }, 800);
  }

  document.addEventListener("DOMContentLoaded", function () {
    gateFlows();
    syntheticMock();
    ribbon();
  });
})();
