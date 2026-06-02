(function () {
  function mountReviewTableFilter(root) {
    if (!root) return;

    const categorySelect = root.querySelector(".rb-review-filter-select");
    const clearBtn = root.querySelector(".rb-review-filter-clear");
    const countEl = root.querySelector(".rb-review-filter-count");
    const tbody = root.querySelector(".rb-review-filter-body") || root.querySelector("tbody");
    const emptyRow = root.querySelector(".rb-review-filter-empty");
    if (!categorySelect || !tbody) return;

    const dataRows = () =>
      Array.from(tbody.querySelectorAll("tr.rb-review-row")).filter(
        (row) => !row.classList.contains("rb-review-empty-data")
      );

    const emptyColspan = () => {
      const firstRow = tbody.querySelector("tr");
      if (!firstRow) return 6;
      return firstRow.children.length || 6;
    };

    const updateClearVisibility = () => {
      if (!clearBtn) return;
      clearBtn.classList.toggle("d-none", !categorySelect.value);
    };

    const applyFilter = () => {
      const category = categorySelect.value;
      const rows = dataRows();
      let visible = 0;

      rows.forEach((row) => {
        const show = !category || row.getAttribute("data-category") === category;
        row.classList.toggle("is-filtered-out", !show);
        if (show) visible += 1;
      });

      if (emptyRow) {
        const showEmpty = rows.length > 0 && visible === 0;
        const td = emptyRow.querySelector("td");
        if (td) td.colSpan = emptyColspan();
        emptyRow.classList.toggle("d-none", !showEmpty);
        if (showEmpty) {
          emptyRow.removeAttribute("hidden");
        } else {
          emptyRow.setAttribute("hidden", "");
        }
      }

      if (countEl) {
        countEl.textContent =
          rows.length > 0 ? `${visible} / ${rows.length} shown` : "";
      }
      updateClearVisibility();
    };

    categorySelect.addEventListener("change", applyFilter);

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        categorySelect.value = "";
        applyFilter();
        categorySelect.focus();
      });
    }

    applyFilter();
  }

  window.mountReviewTableFilter = mountReviewTableFilter;
})();
