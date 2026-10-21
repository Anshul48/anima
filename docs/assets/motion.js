// ANIMA docs motion (WS4). Vanilla JS, no dependencies.
// Progressive enhancement only: every page reads fully with JS off.
// IO-lazy animations; loops get pause; reduced-motion renders final state.
(function () {
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Current nav link.
  var here = location.pathname.split("/").pop() || "index.html";
  var navs = document.querySelectorAll("a.nav");
  for (var i = 0; i < navs.length; i++) {
    if (navs[i].getAttribute("href") === here) navs[i].setAttribute("aria-current", "page");
  }

  var io = ("IntersectionObserver" in window) ? new IntersectionObserver(function (entries) {
    for (var k = 0; k < entries.length; k++) {
      if (entries[k].isIntersecting) {
        entries[k].target.classList.add("in");
        io.unobserve(entries[k].target);
      }
    }
  }, { rootMargin: "0px 0px -10% 0px" }) : null;

  // Entrance reveals: IO-lazy, opacity/transform only.
  var rises = document.querySelectorAll(".rise");
  for (var r = 0; r < rises.length; r++) {
    if (reduce || !io) rises[r].classList.add("in");
    else io.observe(rises[r]);
  }
  // Safety: never leave content hidden if IO callbacks stall (odd embeds,
  // aggressive throttling). IO-lazy reveal still wins in normal browsers.
  setTimeout(function () {
    for (var k = 0; k < rises.length; k++) rises[k].classList.add("in");
  }, 2000);

  // Earned counters: values already in DOM text; IO-lazy.
  function runCounter(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target)) return;
    if (reduce) { el.textContent = target.toLocaleString("en-US"); return; }
    var t0 = null, dur = 600;
    function frame(t) {
      if (!t0) t0 = t;
      var p = Math.min(1, (t - t0) / dur), v = Math.round(target * p);
      el.textContent = v.toLocaleString("en-US");
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var counters = document.querySelectorAll("[data-count]");
  for (var c = 0; c < counters.length; c++) {
    if (reduce || !io) runCounter(counters[c]);
    else (function (el) {
      var o = new IntersectionObserver(function (es) {
        for (var k = 0; k < es.length; k++) {
          if (es[k].isIntersecting) { runCounter(el); o.disconnect(); }
        }
      });
      o.observe(el);
    })(counters[c]);
  }

  // Generic replay: Play/Reset parity. Loops get Pause.
  var stages = document.querySelectorAll("[data-replay]");
  for (var s = 0; s < stages.length; s++) {
    (function (stage) {
      var items = stage.querySelectorAll("ol.steps li");
      var play = stage.querySelector("[data-play]");
      var reset = stage.querySelector("[data-reset]");
      var pause = stage.querySelector("[data-pause]");
      var loop = stage.getAttribute("data-loop") === "1";
      if (!play || items.length === 0) return;
      function showAll() {
        for (var k = 0; k < items.length; k++) items[k].classList.add("lit");
      }
      function clear() {
        for (var k = 0; k < items.length; k++) items[k].classList.remove("lit");
      }
      if (reduce) { showAll(); play.disabled = true; if (reset) reset.disabled = true; if (pause) pause.disabled = true; return; }
      var idx = 0, timer = null, held = false;
      function stop() { if (timer) { clearInterval(timer); timer = null; } }
      function step() {
        if (idx >= items.length) {
          if (loop && !held) { idx = 0; clear(); return; }
          stop(); return;
        }
        items[idx].classList.add("lit"); idx++;
      }
      play.addEventListener("click", function () {
        if (timer) return;
        held = false;
        timer = setInterval(step, 400);
      });
      if (pause) pause.addEventListener("click", function () { held = true; stop(); });
      if (reset) reset.addEventListener("click", function () { stop(); held = false; idx = 0; clear(); });
    })(stages[s]);
  }

  // Scroll-pinned journey: scrolling lights the step in view; Play/Reset parity kept.
  var pinned = document.querySelectorAll("[data-pinned]");
  for (var p = 0; p < pinned.length; p++) {
    (function (stage) {
      var items = stage.querySelectorAll("ol.steps li");
      if (!items.length || reduce || !("IntersectionObserver" in window)) {
        for (var k = 0; k < items.length; k++) items[k].classList.add("lit");
        return;
      }
      var pin = new IntersectionObserver(function (entries) {
        for (var k = 0; k < entries.length; k++) {
          if (entries[k].isIntersecting) {
            for (var j = 0; j < items.length; j++) items[j].classList.remove("pinned");
            entries[k].target.classList.add("pinned", "lit");
          }
        }
      }, { rootMargin: "-40% 0px -40% 0px" });
      for (var m = 0; m < items.length; m++) pin.observe(items[m]);
    })(pinned[p]);
  }

  // Gate-flow + ribbon: light gates in order; loops get pause via sibling button.
  function stepGates(flow, delay) {
    var gates = flow.querySelectorAll(".gate");
    if (!gates.length) return;
    var k;
    function rest() {
      for (var j = 0; j < gates.length; j++) gates[j].setAttribute("data-state", "done");
    }
    if (reduce) { rest(); return { play: rest, reset: rest, stop: function () {} }; }
    var scope = flow.parentElement || document;
    var i = 0, timer = null;
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    function play() {
      stop(); i = 0;
      for (k = 0; k < gates.length; k++) gates[k].setAttribute("data-state", "pending");
      timer = setInterval(function () {
        if (i > 0) gates[i - 1].setAttribute("data-state", "done");
        if (i >= gates.length) { stop(); return; }
        gates[i].setAttribute("data-state", "active");
        i++;
      }, delay);
    }
    function reset() { stop(); rest(); }
    var playBtn = scope.querySelector("[data-play-flow]");
    var resetBtn = scope.querySelector("[data-reset-flow]");
    var pauseBtn = scope.querySelector("[data-pause-flow]");
    if (playBtn) playBtn.addEventListener("click", play);
    if (resetBtn) resetBtn.addEventListener("click", reset);
    if (pauseBtn) pauseBtn.addEventListener("click", stop);
    return { play: play, reset: reset, stop: stop };
  }
  var flows = document.querySelectorAll("[data-gate-flow]");
  for (var f = 0; f < flows.length; f++) {
    if (reduce || !io) stepGates(flows[f], 400);
    else (function (el) {
      var o = new IntersectionObserver(function (es) {
        for (var k = 0; k < es.length; k++) {
          if (es[k].isIntersecting) { stepGates(el, 400); o.disconnect(); }
        }
      });
      o.observe(el);
    })(flows[f]);
  }
  var ribbons = document.querySelectorAll("[data-ribbon]");
  for (var b = 0; b < ribbons.length; b++) {
    if (reduce || !io) stepGates(ribbons[b], 600);
    else (function (el) {
      var o = new IntersectionObserver(function (es) {
        for (var k = 0; k < es.length; k++) {
          if (es[k].isIntersecting) { stepGates(el, 600); o.disconnect(); }
        }
      });
      o.observe(el);
    })(ribbons[b]);
  }

  // SST tree expand/prune replay.
  var trees = document.querySelectorAll("[data-tree]");
  for (var t = 0; t < trees.length; t++) {
    (function (tree) {
      var nodes = tree.querySelectorAll(".treenode[data-branch]");
      var play = tree.querySelector("[data-play]");
      var reset = tree.querySelector("[data-reset]");
      function clear() {
        for (var k = 0; k < nodes.length; k++) {
          nodes[k].hidden = true;
          nodes[k].classList.remove("pruned", "champion");
        }
      }
      function show(i) {
        var n = nodes[i];
        n.hidden = false;
        if (n.getAttribute("data-branch") === "prune") n.classList.add("pruned");
        if (n.getAttribute("data-branch") === "champion") n.classList.add("champion");
      }
      if (!nodes.length) return;
      clear();
      if (reduce) { for (var k = 0; k < nodes.length; k++) show(k); if (play) play.disabled = true; return; }
      var idx = 0, timer = null;
      if (play) play.addEventListener("click", function () {
        if (timer) return;
        timer = setInterval(function () {
          if (idx >= nodes.length) { clearInterval(timer); timer = null; return; }
          show(idx); idx++;
        }, 400);
      });
      if (reset) reset.addEventListener("click", function () {
        if (timer) { clearInterval(timer); timer = null; }
        idx = 0; clear();
      });
    })(trees[t]);
  }

  // STC verify-hash micro-interaction: paste/edit a hash, compare client-side to pin.
  var vh = document.querySelectorAll("[data-verify-hash]");
  for (var v = 0; v < vh.length; v++) {
    (function (box) {
      var pin = (box.getAttribute("data-pin") || "").trim().toLowerCase();
      var input = box.querySelector("input");
      var out = box.querySelector("[data-vh-out]");
      if (!input || !out) return;
      function norm(s) { return s.trim().toLowerCase().replace(/^sha256:/, ""); }
      function check() {
        var val = norm(input.value);
        if (!val) { out.textContent = "Paste a code to compare with the pinned value."; out.className = ""; return; }
        if (val === pin) { out.textContent = "MATCH — pasted code equals the pinned code (compared in your browser)."; out.className = "hashok"; }
        else { out.textContent = "MISMATCH — pasted code differs from the pinned code (compared in your browser)."; out.className = "hashbad"; }
      }
      input.addEventListener("input", check);
      check();
    })(vh[v]);
  }

  // Synthetic screen mock: abstract boxes drawn at load; synthetic diagram only.
  (function syntheticMock() {
    var c = document.getElementById("synthetic-screen");
    if (!c) return;
    var ctx = c.getContext("2d");
    var W = c.width, H = c.height;
    ctx.fillStyle = "#161b22";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#1f2733";
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
      ctx.strokeStyle = routed.indexOf(i) >= 0 ? "#b35c00" : "#0a6e4e";
      ctx.lineWidth = routed.indexOf(i) >= 0 ? 3 : 1.5;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = "#8b949e";
      ctx.font = "10px sans-serif";
      ctx.fillText("box" + i + " score " + (0.5 + rnd() * 0.5).toFixed(2), x, y - 3);
    }
    ctx.fillStyle = "#0e1116";
    ctx.fillRect(0, H - 56, W, 56);
    ctx.fillStyle = "#f0c674";
    ctx.font = "11px sans-serif";
    ctx.fillText("top cut-outs: box1, box3 -> paid vision (drawn mock)", 12, H - 34);
    ctx.fillStyle = "#8b949e";
    ctx.fillText("full screen never sent (concept diagram)", 12, H - 18);
  })();
})();
