/** Show/hide Jira and Zendesk credential fields when integration toggles change. */
(function () {
  function syncCard(card) {
    var toggle = card.querySelector("[data-integration-toggle]");
    var fields = card.querySelector("[data-integration-fields]");
    if (!toggle || !fields) return;
    var enabled = toggle.checked;
    fields.hidden = !enabled;
    card.querySelectorAll("[data-integration-test]").forEach(function (btn) {
      btn.disabled = !enabled;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-integration-card]").forEach(function (card) {
      syncCard(card);
      var toggle = card.querySelector("[data-integration-toggle]");
      if (toggle) {
        toggle.addEventListener("change", function () {
          syncCard(card);
        });
      }
    });
  });
})();
