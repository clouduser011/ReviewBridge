(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof initNavScrolled === "function") {
      initNavScrolled("landingNav");
    }

    if (typeof initLandingNavScrollSpy === "function") {
      initLandingNavScrollSpy("landingNav");
    }

    document.querySelectorAll('#landingNav .rb-nav-primary a[href^="#"]').forEach(function (link) {
      link.addEventListener("click", function (e) {
        var id = link.getAttribute("href");
        if (!id || id === "#") return;
        var target = document.querySelector(id);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  });

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!prefersReduced && "IntersectionObserver" in window) {
    document.addEventListener("DOMContentLoaded", function () {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { rootMargin: "0px 0px -40px 0px", threshold: 0.08 }
      );
      document.querySelectorAll(".reveal").forEach(function (el) {
        observer.observe(el);
      });
    });
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll(".reveal").forEach(function (el) {
        el.classList.add("is-visible");
      });
    });
  }
})();
