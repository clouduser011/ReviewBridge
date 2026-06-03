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

  function updateNavPillsIndicator(pillsEl, activeLink) {
    if (!pillsEl || !activeLink) return;
    var indicator = pillsEl.querySelector(".rb-nav-pills-indicator");
    if (!indicator) return;
    var x = activeLink.offsetLeft;
    var w = activeLink.offsetWidth;
    indicator.style.setProperty("--nav-indicator-x", x + "px");
    indicator.style.setProperty("--nav-indicator-w", w + "px");
    indicator.classList.add("is-visible");
  }

  function setActiveNavLink(links, sectionId, pillsEl) {
    var activeLink = null;
    links.forEach(function (link) {
      var isActive = link.getAttribute("data-nav-section") === sectionId;
      link.classList.toggle("is-active", isActive);
      if (isActive) {
        link.setAttribute("aria-current", "location");
        activeLink = link;
      } else {
        link.removeAttribute("aria-current");
      }
    });
    if (activeLink) {
      updateNavPillsIndicator(pillsEl, activeLink);
    }
  }

  function initLandingNavScrollSpy(navId) {
    var nav = typeof navId === "string" ? document.getElementById(navId) : navId;
    if (!nav) return;

    var pillsEl = nav.querySelector("[data-nav-pills]");
    if (!pillsEl) return;

    var links = Array.prototype.slice.call(pillsEl.querySelectorAll("[data-nav-section]"));
    if (!links.length) return;

    var sections = [];
    links.forEach(function (link) {
      var sectionId = link.getAttribute("data-nav-section");
      var sectionEl = document.getElementById(sectionId);
      if (sectionEl) {
        sections.push({ id: sectionId, el: sectionEl, link: link });
      }
    });
    if (!sections.length) return;

    var currentSection = "";
    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      pillsEl.classList.add("is-reduced-motion");
    }

    function resolveActiveSection() {
      if (window.scrollY < 80) {
        return "top";
      }

      var visible = sections.filter(function (section) {
        var rect = section.el.getBoundingClientRect();
        var viewportMid = window.innerHeight * 0.35;
        return rect.top <= viewportMid && rect.bottom > viewportMid;
      });

      if (!visible.length) {
        var closest = null;
        var closestDist = Infinity;
        sections.forEach(function (section) {
          var rect = section.el.getBoundingClientRect();
          var dist = Math.abs(rect.top - window.innerHeight * 0.25);
          if (dist < closestDist) {
            closestDist = dist;
            closest = section;
          }
        });
        return closest ? closest.id : "top";
      }

      visible.sort(function (a, b) {
        return a.el.getBoundingClientRect().top - b.el.getBoundingClientRect().top;
      });
      return visible[0].id;
    }

    function syncFromScroll() {
      var next = resolveActiveSection();
      if (next === currentSection) return;
      currentSection = next;
      setActiveNavLink(links, next, pillsEl);
    }

    if ("IntersectionObserver" in window) {
      var ratios = new Map();
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            ratios.set(entry.target.id, entry.intersectionRatio);
          });

          if (window.scrollY < 80) {
            if (currentSection !== "top") {
              currentSection = "top";
              setActiveNavLink(links, "top", pillsEl);
            }
            return;
          }

          var bestId = "";
          var bestRatio = 0;
          var bestTop = Infinity;
          ratios.forEach(function (ratio, id) {
            if (ratio <= 0) return;
            var el = document.getElementById(id);
            if (!el) return;
            var top = el.getBoundingClientRect().top;
            if (ratio > bestRatio || (ratio === bestRatio && top < bestTop)) {
              bestRatio = ratio;
              bestTop = top;
              bestId = id;
            }
          });

          if (!bestId) {
            syncFromScroll();
            return;
          }
          if (bestId === currentSection) return;
          currentSection = bestId;
          setActiveNavLink(links, bestId, pillsEl);
        },
        { rootMargin: "-45% 0px -45% 0px", threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] }
      );

      sections.forEach(function (section) {
        observer.observe(section.el);
      });
    }

    window.addEventListener("scroll", syncFromScroll, { passive: true });
    window.addEventListener("resize", function () {
      var active = pillsEl.querySelector(".rb-nav-link.is-active");
      if (active) {
        updateNavPillsIndicator(pillsEl, active);
      }
    });

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        var active = pillsEl.querySelector(".rb-nav-link.is-active");
        if (active) {
          updateNavPillsIndicator(pillsEl, active);
        }
      });
    }

    currentSection = resolveActiveSection();
    setActiveNavLink(links, currentSection, pillsEl);
  }

  global.initNavScrolled = initNavScrolled;
  global.initLandingNavScrollSpy = initLandingNavScrollSpy;
  global.updateNavPillsIndicator = updateNavPillsIndicator;
})(typeof window !== "undefined" ? window : globalThis);
