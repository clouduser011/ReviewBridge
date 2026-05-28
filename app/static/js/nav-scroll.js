(function (global) {
  "use strict";

  function initNavScrolled(navId, threshold) {
    var nav = typeof navId === "string" ? document.getElementById(navId) : navId;
    if (!nav) return;
    var limit = typeof threshold === "number" ? threshold : 24;
    var onScroll = function () {
      nav.classList.toggle("is-scrolled", window.scrollY > limit);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  global.initNavScrolled = initNavScrolled;
})(typeof window !== "undefined" ? window : globalThis);
