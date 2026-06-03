(function () {
  "use strict";

  function removeFlashRootIfEmpty(root) {
    if (!root || !root.hasAttribute("data-flash-root") || root.children.length > 0) {
      return;
    }
    var parent = root.parentElement;
    root.remove();
    if (
      parent &&
      parent.classList.contains("landing-container") &&
      parent.children.length === 0 &&
      parent.closest("main")
    ) {
      parent.remove();
    }
  }

  function initFlashMessages() {
    document.querySelectorAll("[data-flash-root] .alert").forEach(function (el) {
      el.addEventListener("closed.bs.alert", function () {
        var root = el.closest("[data-flash-root]");
        el.remove();
        removeFlashRootIfEmpty(root);
      });
    });

    document.querySelectorAll(".js-alert-auto-hide[data-auto-hide-ms]").forEach(function (el) {
      var ms = parseInt(el.getAttribute("data-auto-hide-ms"), 10);
      if (!ms || ms < 1000) ms = 4000;
      window.setTimeout(function () {
        try {
          bootstrap.Alert.getOrCreateInstance(el).close();
        } catch (_e) {
          var root = el.closest("[data-flash-root]");
          el.remove();
          removeFlashRootIfEmpty(root);
        }
      }, ms);
    });
  }

  document.addEventListener("DOMContentLoaded", initFlashMessages);
})();
