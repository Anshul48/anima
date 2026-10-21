/* R5 story canvas: "The Wrong Total" — one token travels five stops.
   Pure f(t) loop; IntersectionObserver-gated; reduced-motion renders final
   frame once. No deps, no console output. Colors read from CSS tokens. */
(function () {
  'use strict';
  var STOPS = [
    { x: 0.08, y: 0.62, label: 'Remember', cap: 'The memory map replays how the total was built — and the advisor warns Maya she tried this shortcut before.' },
    { x: 0.29, y: 0.34, label: 'Argue', cap: 'Two candidate fixes debate against strict checks. The weaker one visibly loses; the survivor merges into one fix.' },
    { x: 0.50, y: 0.55, label: 'Build', cap: 'The work lives in a saved workspace. The laptop dies mid-fix — reopen, every byte intact — then fuse with a teammate.' },
    { x: 0.71, y: 0.30, label: 'Check', cap: 'Four automatic checks pass, a signed proof is issued. One tampered byte? The independent inspector seals it off.' },
    { x: 0.90, y: 0.58, label: 'Act *', cap: 'One day the fix clicks through the shop itself and verifies the total. Drawn, not built — an early seed today.' }
  ];
  var LOOP_S = 20, DWELL = 0.12;

  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }
  function reduced() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function draw(cv, t, opts) {
    var W = 640, H = 320, ctx = cv.getContext('2d');
    if (!ctx) return;
    var ink = cssVar('--ink', '#e6edf3'), muted = cssVar('--muted', '#8b949e');
    var accent = cssVar('--accent', '#4493f8'), green = cssVar('--accent2', '#3fb950');
    var panel = cssVar('--panel', '#161b22');
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = panel;
    ctx.fillRect(0, 0, W, H);
    function px(s) { return { x: s.x * W, y: s.y * H }; }
    // Path
    ctx.strokeStyle = muted; ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.beginPath();
    STOPS.forEach(function (s, i) {
      var p = px(s);
      if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    // Token position: equal legs with dwells
    var legs = STOPS.length - 1, progress = (t % LOOP_S) / LOOP_S;
    var lit = 0;
    if (opts && opts.final) { progress = 1; }
    var segLen = 1 / legs, token = px(STOPS[0]);
    for (var i = 0; i < legs; i++) {
      var a = px(STOPS[i]), b = px(STOPS[i + 1]);
      var t0 = i * segLen, t1 = (i + 1) * segLen;
      var dt = t1 - t0, move = t0 + dt * (1 - DWELL);
      if (progress >= t1 || (opts && opts.final)) { lit = i + 1; token = b; continue; }
      if (progress <= t0) { token = a; break; }
      lit = i;
      var k = progress < move ? (progress - t0) / (move - t0) : 1;
      k = k * k * (3 - 2 * k);
      token = { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
      if (progress >= move) lit = i + 1;
      break;
    }
    if (progress >= 1 - 1e-6) lit = legs;
    // Stations
    STOPS.forEach(function (s, i) {
      var p = px(s), on = i <= lit, seed = i === STOPS.length - 1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, on ? 13 : 10, 0, Math.PI * 2);
      if (seed) {
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = cssVar('--warn-ink', '#f0c674'); ctx.lineWidth = 2.5;
        ctx.stroke(); ctx.setLineDash([]);
      } else {
        ctx.fillStyle = on ? accent : panel;
        ctx.fill();
        ctx.strokeStyle = on ? accent : muted; ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (on && !seed) {
        ctx.fillStyle = panel;
        ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = on ? ink : muted;
      ctx.font = '700 13px ' + getComputedStyle(document.body).fontFamily;
      ctx.textAlign = 'center';
      ctx.fillText(s.label, p.x, p.y + 32);
    });
    // Token
    if (!(opts && opts.final)) {
      ctx.beginPath();
      ctx.arc(token.x, token.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = green;
      ctx.fill();
      ctx.strokeStyle = panel; ctx.lineWidth = 2;
      ctx.stroke();
    }
    return lit;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var cv = document.getElementById('story-canvas');
    if (!cv) return;
    cv.width = 640; cv.height = 320;
    var cap = document.getElementById('story-cap');
    function setCap(lit) {
      if (!cap) return;
      var s = STOPS[Math.min(lit, STOPS.length - 1)];
      cap.innerHTML = '';
      var b = document.createElement('strong');
      b.textContent = 'Now: ' + s.label.replace(' *', '') + '. ';
      cap.appendChild(b);
      cap.appendChild(document.createTextNode(s.cap));
    }
    if (reduced()) {
      draw(cv, 0, { final: true });
      setCap(STOPS.length - 1);
      return;
    }
    setCap(0);
    var t0 = null, running = true, lastLit = -1;
    function frame(ts) {
      if (!running) return;
      if (t0 === null) t0 = ts;
      var lit = draw(cv, (ts - t0) / 1000);
      if (lit !== lastLit) { lastLit = lit; setCap(lit); }
      requestAnimationFrame(frame);
    }
    if ('IntersectionObserver' in window) {
      var started = false;
      new IntersectionObserver(function (en) {
        en.forEach(function (e) {
          if (e.isIntersecting && !started) {
            started = true; requestAnimationFrame(frame);
          }
        });
      }, { threshold: 0.2 }).observe(cv);
    } else {
      requestAnimationFrame(frame);
    }
  });
})();
