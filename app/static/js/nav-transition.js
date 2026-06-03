(function (global) {
  "use strict";

  var STORAGE_KEY = "rb-nav-from";
  var PHASE_COLLAPSE_MS = 200;
  var PHASE_FLIGHT_MS = 460;
  var PHASE_EXPAND_MS = 500;
  var PHASE_SETTLE_MS = 220;
  var EASE = "cubic-bezier(0.4, 0, 0.2, 1)";

  (function primeExpandPending() {
    try {
      var path = window.location.pathname;
      var isLanding = path === "/" || path === "";
      if (isLanding && sessionStorage.getItem(STORAGE_KEY) === "app") {
        document.documentElement.setAttribute("data-nav-expand-pending", "true");
      }
    } catch (err) {
      /* sessionStorage unavailable */
    }
  })();

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function delay(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function isPillsVisible(nav) {
    var primary = nav && nav.querySelector(".rb-nav-primary");
    if (!primary) return false;
    return window.getComputedStyle(primary).display !== "none";
  }

  function getNavHeader() {
    return document.querySelector("[data-nav-mode]");
  }

  function getFlightLayer(nav) {
    var layer = nav.querySelector("[data-nav-flight-layer]");
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "rb-nav-flight-layer";
      layer.setAttribute("aria-hidden", "true");
      layer.setAttribute("data-nav-flight-layer", "");
      nav.appendChild(layer);
    }
    return layer;
  }

  function waitForTransition(el, timeoutMs, propertyName) {
    return new Promise(function (resolve) {
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        el.removeEventListener("transitionend", onEnd);
        clearTimeout(timer);
        resolve();
      }
      function onEnd(e) {
        if (e.target !== el) return;
        if (propertyName && e.propertyName !== propertyName) return;
        finish();
      }
      var timer = setTimeout(finish, timeoutMs);
      el.addEventListener("transitionend", onEnd);
    });
  }

  function measureNavMetrics(nav) {
    if (!nav) return null;

    var pills = nav.querySelector("[data-nav-pills]");
    var sections = nav.querySelector("[data-nav-sections]");
    var homeCenter = nav.querySelector("[data-nav-home].rb-nav-home-center");
    var homeAction = nav.querySelector(".rb-nav-home-action");
    var homeTarget = nav.querySelector("[data-nav-home-target]");
    var primary = nav.querySelector("[data-nav-primary]");

    var metrics = {
      pillsExpandedW: 0,
      pillsCollapsedW: 0,
      sectionsExpandedW: 0,
      homeDeltaX: 0,
      centerSlot: null,
      homeTargetRect: null,
    };

    if (pills) {
      metrics.pillsExpandedW = pills.offsetWidth;
      nav.style.setProperty("--rb-nav-pills-expanded-w", metrics.pillsExpandedW + "px");
    }

    if (homeCenter) {
      metrics.pillsCollapsedW = homeCenter.offsetWidth + 24;
      nav.style.setProperty("--rb-nav-pills-collapsed-w", metrics.pillsCollapsedW + "px");
    }

    if (sections) {
      metrics.sectionsExpandedW = sections.scrollWidth;
      nav.style.setProperty("--rb-nav-sections-expanded-w", metrics.sectionsExpandedW + "px");
    }

    if (homeCenter && (homeAction || homeTarget)) {
      var targetEl = homeAction || homeTarget;
      metrics.homeTargetRect = targetEl.getBoundingClientRect();
      metrics.homeDeltaX = metrics.homeTargetRect.left - homeCenter.getBoundingClientRect().left;
      nav.style.setProperty("--rb-nav-home-delta-x", metrics.homeDeltaX + "px");
    }

    if (primary && homeCenter) {
      var primaryRect = primary.getBoundingClientRect();
      var homeRect = homeCenter.getBoundingClientRect();
      metrics.centerSlot = {
        left: primaryRect.left + primaryRect.width / 2 - homeRect.width / 2,
        top: homeRect.top,
        width: homeRect.width,
        height: homeRect.height,
      };
    } else if (primary && homeAction) {
      var actionRect = homeAction.getBoundingClientRect();
      var pRect = primary.getBoundingClientRect();
      metrics.centerSlot = {
        left: pRect.left + pRect.width / 2 - actionRect.width / 2,
        top: actionRect.top,
        width: actionRect.width,
        height: actionRect.height,
      };
    }

    return metrics;
  }

  function createFlightClone(sourceEl, variant) {
    var layer = getFlightLayer(getNavHeader());
    var rect = sourceEl.getBoundingClientRect();
    var computed = window.getComputedStyle(sourceEl);
    var clone = document.createElement("div");
    clone.className = "rb-nav-flight rb-nav-flight--" + variant;
    clone.textContent = sourceEl.textContent.trim();

    clone.style.position = "fixed";
    clone.style.left = rect.left + "px";
    clone.style.top = rect.top + "px";
    clone.style.width = rect.width + "px";
    clone.style.height = rect.height + "px";
    clone.style.margin = "0";
    clone.style.boxSizing = "border-box";
    clone.style.fontSize = computed.fontSize;
    clone.style.fontWeight = computed.fontWeight;
    clone.style.fontFamily = computed.fontFamily;
    clone.style.lineHeight = computed.lineHeight;
    clone.style.letterSpacing = computed.letterSpacing;
    clone.style.display = "flex";
    clone.style.alignItems = "center";
    clone.style.justifyContent = "center";
    clone.style.borderRadius = computed.borderRadius;
    clone.style.zIndex = "1041";
    clone.style.pointerEvents = "none";
    clone.style.willChange = "transform, opacity";

    if (variant === "pill") {
      clone.style.color = computed.color;
      clone.style.background = "#fff";
      clone.style.boxShadow = "var(--rb-nav-active-shadow), 0 0 0 1px rgba(59, 130, 246, 0.15)";
      clone.style.border = "1px solid transparent";
    } else {
      clone.style.color = computed.color;
      clone.style.background = computed.backgroundColor;
      clone.style.border = computed.border;
      clone.style.boxShadow = computed.boxShadow;
    }

    layer.appendChild(clone);
    return clone;
  }

  function rectToObject(rect) {
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
  }

  function animateFlight(clone, fromRect, toRect, durationMs) {
    var dx = toRect.left - fromRect.left;
    var dy = toRect.top - fromRect.top;
    var sx = toRect.width / fromRect.width;
    var sy = toRect.height / fromRect.height;

    if (clone.animate) {
      return clone
        .animate(
          [
            { transform: "translate(0, 0) scale(1, 1)", opacity: 1 },
            { transform: "translate(" + dx + "px, " + dy + "px) scale(" + sx + ", " + sy + ")", opacity: 1 },
          ],
          { duration: durationMs, easing: EASE, fill: "forwards" }
        )
        .finished.catch(function () {
          return delay(durationMs);
        });
    }

    clone.style.transition = "transform " + durationMs + "ms " + EASE;
    requestAnimationFrame(function () {
      clone.style.transform = "translate(" + dx + "px, " + dy + "px) scale(" + sx + ", " + sy + ")";
    });
    return delay(durationMs);
  }

  function removeFlightClones(nav) {
    var layer = nav.querySelector("[data-nav-flight-layer]");
    if (!layer) return;
    while (layer.firstChild) {
      layer.removeChild(layer.firstChild);
    }
  }

  function navigatePlain(url) {
    window.location.assign(url);
  }

  function handleLeaveLanding(nav, url) {
    if (!isPillsVisible(nav) || prefersReducedMotion()) {
      sessionStorage.setItem(STORAGE_KEY, "landing");
      navigatePlain(url);
      return;
    }

    var metrics = measureNavMetrics(nav);
    var homeCenter = nav.querySelector("[data-nav-home].rb-nav-home-center");
    var homeTarget = nav.querySelector("[data-nav-home-target]");
    var pills = nav.querySelector("[data-nav-pills]");
    var sections = nav.querySelector("[data-nav-sections]");

    if (!homeCenter || !homeTarget || !pills) {
      sessionStorage.setItem(STORAGE_KEY, "landing");
      navigatePlain(url);
      return;
    }

    nav.classList.add("is-nav-leaving-landing");

    var collapsePromise = sections
      ? waitForTransition(sections, PHASE_COLLAPSE_MS + 80, "width")
      : delay(PHASE_COLLAPSE_MS);

    collapsePromise.then(function () {
      var fromRect = rectToObject(homeCenter.getBoundingClientRect());
      var toRect = rectToObject(homeTarget.getBoundingClientRect());
      homeCenter.classList.add("is-nav-home-hidden");
      pills.classList.add("is-nav-pills-collapsed");

      var clone = createFlightClone(homeCenter, "pill");
      return animateFlight(clone, fromRect, toRect, PHASE_FLIGHT_MS);
    }).then(function () {
      sessionStorage.setItem(STORAGE_KEY, "landing");
      try {
        sessionStorage.setItem("rb-nav-home-delta-x", String(metrics.homeDeltaX || 0));
      } catch (err) {
        /* ignore */
      }
      removeFlightClones(nav);
      navigatePlain(url);
    });
  }

  function handleLeaveApp(nav, url) {
    if (prefersReducedMotion()) {
      sessionStorage.setItem(STORAGE_KEY, "app");
      navigatePlain(url);
      return;
    }

    var metrics = measureNavMetrics(nav);
    var homeAction = nav.querySelector(".rb-nav-home-action");

    if (!homeAction || !metrics || !metrics.centerSlot) {
      sessionStorage.setItem(STORAGE_KEY, "app");
      navigatePlain(url);
      return;
    }

    nav.classList.add("is-nav-leaving-app");

    var fromRect = rectToObject(homeAction.getBoundingClientRect());
    var toRect = {
      left: metrics.centerSlot.left,
      top: metrics.centerSlot.top,
      width: fromRect.width,
      height: fromRect.height,
    };

    homeAction.classList.add("is-nav-home-hidden");
    var clone = createFlightClone(homeAction, "action");

    animateFlight(clone, fromRect, toRect, PHASE_FLIGHT_MS).then(function () {
      sessionStorage.setItem(STORAGE_KEY, "app");
      removeFlightClones(nav);
      navigatePlain(url);
    });
  }

  function handleEnterLanding(nav) {
    var from = sessionStorage.getItem(STORAGE_KEY);
    if (from !== "app" || prefersReducedMotion() || !isPillsVisible(nav)) {
      sessionStorage.removeItem(STORAGE_KEY);
      document.documentElement.removeAttribute("data-nav-expand-pending");
      if (typeof global.initLandingNavScrollSpy === "function") {
        global.initLandingNavScrollSpy(nav.id || "landingNav");
      }
      return;
    }

    document.documentElement.setAttribute("data-nav-expand-pending", "true");
    measureNavMetrics(nav);

    var pills = nav.querySelector("[data-nav-pills]");
    var sections = nav.querySelector("[data-nav-sections]");
    var homeCenter = nav.querySelector("[data-nav-home].rb-nav-home-center");

    nav.classList.add("is-nav-entering-landing");
    if (pills) pills.classList.add("is-nav-pills-collapsed");
    if (sections) sections.classList.add("is-nav-sections-collapsed");
    if (homeCenter) homeCenter.classList.add("is-nav-home-at-target");

    nav.offsetHeight;

    requestAnimationFrame(function () {
      nav.classList.add("is-nav-expanded");
      if (pills) pills.classList.remove("is-nav-pills-collapsed");
      if (sections) sections.classList.remove("is-nav-sections-collapsed");
      if (homeCenter) homeCenter.classList.remove("is-nav-home-at-target");
    });

    waitForTransition(pills, PHASE_EXPAND_MS + 100, "width").then(function () {
      nav.classList.remove("is-nav-entering-landing", "is-nav-expanded");
      sessionStorage.removeItem(STORAGE_KEY);
      document.documentElement.removeAttribute("data-nav-expand-pending");
      if (typeof global.initLandingNavScrollSpy === "function") {
        global.initLandingNavScrollSpy(nav.id || "landingNav");
      }
    });
  }

  function handleEnterApp(nav) {
    var from = sessionStorage.getItem(STORAGE_KEY);
    if (from !== "landing" || prefersReducedMotion()) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }

    measureNavMetrics(nav);
    try {
      var storedDelta = sessionStorage.getItem("rb-nav-home-delta-x");
      if (storedDelta !== null) {
        nav.style.setProperty("--rb-nav-home-delta-x", storedDelta + "px");
      }
    } catch (err) {
      /* ignore */
    }

    var homeAction = nav.querySelector(".rb-nav-home-action");
    if (!homeAction) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }

    nav.classList.add("is-nav-entering-app");
    homeAction.classList.add("is-nav-home-awaiting");

    nav.offsetHeight;

    requestAnimationFrame(function () {
      nav.classList.add("is-nav-settled");
      homeAction.classList.remove("is-nav-home-awaiting");
    });

    delay(PHASE_SETTLE_MS).then(function () {
      nav.classList.remove("is-nav-entering-app", "is-nav-settled");
      sessionStorage.removeItem(STORAGE_KEY);
      try {
        sessionStorage.removeItem("rb-nav-home-delta-x");
      } catch (err) {
        /* ignore */
      }
    });
  }

  function initNavTransition() {
    var nav = getNavHeader();
    if (!nav) return;

    var mode = nav.getAttribute("data-nav-mode");

    measureNavMetrics(nav);
    window.addEventListener(
      "resize",
      function () {
        measureNavMetrics(nav);
      },
      { passive: true }
    );

    if (mode === "landing") {
      handleEnterLanding(nav);
    } else if (mode === "app") {
      handleEnterApp(nav);
    }

    document.addEventListener("click", function (e) {
      var link = e.target.closest("[data-nav-transition]");
      if (!link || link.tagName !== "A") return;

      var transition = link.getAttribute("data-nav-transition");
      var href = link.getAttribute("href");
      if (!href || href.charAt(0) === "#") return;

      var currentNav = getNavHeader();
      if (!currentNav) return;

      var currentMode = currentNav.getAttribute("data-nav-mode");

      if (transition === "to-app" && currentMode === "landing") {
        e.preventDefault();
        handleLeaveLanding(currentNav, link.href);
        return;
      }

      if (transition === "to-landing" && currentMode === "app") {
        e.preventDefault();
        handleLeaveApp(currentNav, link.href);
      }
    });
  }

  global.initNavTransition = initNavTransition;
  global.measureNavMetrics = measureNavMetrics;
  global.createFlightClone = createFlightClone;
  global.animateFlight = animateFlight;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNavTransition);
  } else {
    initNavTransition();
  }
})(typeof window !== "undefined" ? window : globalThis);
