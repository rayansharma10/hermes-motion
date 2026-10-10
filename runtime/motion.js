/* hermes-motion runtime: a deterministic, seekable timeline.
 *
 * Nothing here runs in real time. The renderer calls window.__seek(t) with an absolute time in
 * seconds and every visual property is recomputed as a pure function of t. Same t -> same pixels.
 *
 * Scene DOM contract (written by hermes_motion.scenes, or by hand for custom scenes):
 *   .scene[data-start][data-end][data-transition]      one per scene, absolute seconds
 *   [data-anim=TYPE][data-t=DELAY][data-d=DURATION]    animated element, scene-local seconds
 *   #captions .cap[data-start][data-end] .w[data-s][data-e]   burned-in captions
 * Anim types: fade rise pop draw flow grow-y grow-x wipe count hl
 * Config is read from window.__CFG__ = { easing, intensity }.
 */
(function () {
  "use strict";
  var CFG = window.__CFG__ || {};
  var INTENSITY = typeof CFG.intensity === "number" ? CFG.intensity : 1;

  var EASE = {
    linear: function (t) { return t; },
    smooth: function (t) { return 1 - Math.pow(1 - t, 3); },
    snappy: function (t) { return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t); },
    bounce: function (t) { var c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
    inout: function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  };
  var ease = EASE[CFG.easing] || EASE.smooth;

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function num(el, name, dflt) {
    var v = el.getAttribute(name);
    return v === null ? dflt : parseFloat(v);
  }

  var scenes = [].map.call(document.querySelectorAll(".scene"), function (el) {
    return {
      el: el,
      start: num(el, "data-start", 0),
      end: num(el, "data-end", 0),
      transition: el.getAttribute("data-transition") || "fade",
      anims: [].slice.call(el.querySelectorAll("[data-anim]")),
      isLast: false
    };
  });
  if (scenes.length) scenes[scenes.length - 1].isLast = true;

  var caps = [].map.call(document.querySelectorAll("#captions .cap"), function (el) {
    return {
      el: el, start: num(el, "data-start", 0), end: num(el, "data-end", 0),
      words: [].map.call(el.querySelectorAll(".w"), function (w) {
        return { el: w, s: num(w, "data-s", 0), e: num(w, "data-e", 0) };
      })
    };
  });

  var pathLen = new WeakMap();
  function lengthOf(el) {
    if (!pathLen.has(el)) pathLen.set(el, el.getTotalLength ? el.getTotalLength() : 0);
    return pathLen.get(el);
  }

  function applyAnim(el, local) {
    var type = el.getAttribute("data-anim");
    var t0 = num(el, "data-t", 0);
    var dur = Math.max(0.001, num(el, "data-d", 0.6));
    var p = clamp01((local - t0) / dur);
    var e = ease(p);
    var s = el.style;
    switch (type) {
      case "fade":
        s.opacity = p > 0 ? e : 0; break;
      case "rise":
        s.opacity = p > 0 ? Math.min(1, e * 1.4) : 0;
        s.transform = "translateY(" + ((1 - e) * 36 * INTENSITY).toFixed(2) + "px)"; break;
      case "pop":
        s.opacity = p > 0 ? Math.min(1, p * 3) : 0;
        s.transform = "scale(" + (0.82 + 0.18 * e).toFixed(4) + ")"; break;
      case "draw":
        var L = lengthOf(el);
        s.strokeDasharray = L; s.strokeDashoffset = L * (1 - ease(p));
        s.opacity = p > 0 ? 1 : 0; break;
      case "flow":
        // dashes travelling along an already drawn path; pure function of time
        s.opacity = local >= t0 ? 1 : 0;
        s.strokeDashoffset = -(Math.max(0, local - t0)) * 70; break;
      case "grow-y":
        s.transformOrigin = "50% 100%"; s.transform = "scaleY(" + e.toFixed(4) + ")";
        s.opacity = p > 0 ? 1 : 0; break;
      case "grow-x":
        s.transformOrigin = "0% 50%"; s.transform = "scaleX(" + e.toFixed(4) + ")";
        s.opacity = p > 0 ? 1 : 0; break;
      case "wipe":
        s.clipPath = "inset(0 " + ((1 - e) * 100).toFixed(2) + "% 0 0)";
        s.opacity = p > 0 ? 1 : 0; break;
      case "count":
        var to = num(el, "data-to", 0), dec = num(el, "data-dec", 0);
        el.textContent = (to * e).toFixed(dec) + (el.getAttribute("data-unit") || "");
        s.opacity = p > 0 ? 1 : 0; break;
      case "hl":
        s.setProperty("--hl", e.toFixed(4)); break;
    }
  }

  function seek(t) {
    for (var i = 0; i < scenes.length; i++) {
      var sc = scenes[i], local = t - sc.start;
      var visible = t >= sc.start - 1e-6 && (t < sc.end - 1e-6 || (sc.isLast && t <= sc.end + 1e-6));
      sc.el.style.visibility = visible ? "visible" : "hidden";
      if (!visible) continue;
      var fin = clamp01(local / 0.35), fout = sc.isLast ? 1 : clamp01((sc.end - t) / 0.3);
      var a = 1, tx = 0;
      if (sc.transition === "fade") a = Math.min(fin, fout);
      else if (sc.transition === "slide") { a = Math.min(fin, fout); tx = (1 - ease(fin)) * 80 * INTENSITY - (1 - fout) * 80 * INTENSITY; }
      sc.el.style.opacity = a;
      sc.el.style.transform = tx ? "translateX(" + tx.toFixed(2) + "px)" : "none";
      for (var k = 0; k < sc.anims.length; k++) applyAnim(sc.anims[k], local);
    }
    for (var c = 0; c < caps.length; c++) {
      var cp = caps[c], on = t >= cp.start && t < cp.end;
      cp.el.style.display = on ? "block" : "none";
      if (on) for (var w = 0; w < cp.words.length; w++) {
        cp.words[w].el.classList.toggle("on", t >= cp.words[w].s && t < cp.words[w].e + 0.05);
        cp.words[w].el.classList.toggle("done", t >= cp.words[w].e + 0.05);
      }
    }
    // custom hooks: window.__hooks.push(function (t, scenes) { ... })
    (window.__hooks || []).forEach(function (h) { h(t, scenes); });
    return t;
  }

  window.__seek = seek;
  window.__duration = scenes.length ? scenes[scenes.length - 1].end : 0;
  window.__ready = (document.fonts && document.fonts.ready) ? document.fonts.ready.then(function () { return true; }) : Promise.resolve(true);
  seek(0);
})();
