(function () {
  function getChips(strip) {
    return Array.from(strip.querySelectorAll(".rb-history-app-chip[role='tab']"));
  }

  function getPanels(detail) {
    return Array.from(detail.querySelectorAll(".rb-history-app-panel[data-app-panel]"));
  }

  function activateHistoryApp(strip, detail, index) {
    const chips = getChips(strip);
    const panels = getPanels(detail);
    if (!chips.length || index < 0 || index >= chips.length) return;

    chips.forEach((chip, i) => {
      const isActive = i === index;
      chip.classList.toggle("is-active", isActive);
      chip.setAttribute("aria-selected", isActive ? "true" : "false");
      chip.setAttribute("tabindex", isActive ? "0" : "-1");
    });

    panels.forEach((panel, i) => {
      const isActive = i === index;
      panel.classList.toggle("d-none", !isActive);
      if (isActive) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
    });

    const activeChip = chips[index];
    if (activeChip && typeof activeChip.scrollIntoView === "function") {
      activeChip.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  }

  function chipIndexFromKey(event, currentIndex, chipCount) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      return (currentIndex + 1) % chipCount;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      return (currentIndex - 1 + chipCount) % chipCount;
    }
    return null;
  }

  function initHistoryAppTabs() {
    const strip = document.getElementById("historyAppStrip");
    const detail = document.getElementById("historyAppDetail");
    if (!strip || !detail) return;

    const chips = getChips(strip);
    if (!chips.length) return;

    strip.addEventListener("click", (event) => {
      const chip = event.target.closest(".rb-history-app-chip");
      if (!chip || !strip.contains(chip)) return;
      const index = parseInt(chip.getAttribute("data-app-index"), 10);
      if (Number.isNaN(index)) return;
      activateHistoryApp(strip, detail, index);
    });

    strip.addEventListener("keydown", (event) => {
      const chip = event.target.closest(".rb-history-app-chip");
      if (!chip || !strip.contains(chip)) return;

      const chipsList = getChips(strip);
      const currentIndex = chipsList.indexOf(chip);
      if (currentIndex < 0) return;

      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activateHistoryApp(strip, detail, currentIndex);
        return;
      }

      const nextIndex = chipIndexFromKey(event, currentIndex, chipsList.length);
      if (nextIndex === null) return;

      event.preventDefault();
      activateHistoryApp(strip, detail, nextIndex);
      chipsList[nextIndex].focus();
    });
  }

  function initHistoryReviewFilters() {
    if (typeof window.mountReviewTableFilter !== "function") return;
    document.querySelectorAll("[data-review-filter-root]").forEach((root) => {
      window.mountReviewTableFilter(root);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initHistoryAppTabs();
    initHistoryReviewFilters();
  });
})();
