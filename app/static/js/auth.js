(function () {
  "use strict";

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initEntrance() {
    document.body.classList.add("is-ready");
    if (prefersReduced) {
      document.querySelectorAll(".auth-stagger > *").forEach(function (el) {
        el.style.opacity = "1";
        el.style.transform = "none";
      });
    }
  }

  function initPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach(function (btn) {
      var inputId = btn.getAttribute("data-password-toggle");
      var input = document.getElementById(inputId);
      if (!input) return;

      var showIcon = btn.querySelector(".auth-field-toggle-show");
      var hideIcon = btn.querySelector(".auth-field-toggle-hide");

      btn.addEventListener("click", function () {
        var isHidden = input.type === "password";
        input.type = isHidden ? "text" : "password";
        btn.setAttribute("aria-pressed", isHidden ? "true" : "false");
        btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
        if (showIcon) showIcon.hidden = isHidden;
        if (hideIcon) hideIcon.hidden = !isHidden;
      });
    });
  }

  function initSubmitLoading() {
    document.querySelectorAll("[data-auth-form]").forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector("[data-auth-submit]");
        if (btn && !btn.classList.contains("is-loading")) {
          btn.classList.add("is-loading");
          btn.disabled = true;
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initEntrance();
    initPasswordToggles();
    initSubmitLoading();
  });
})();
