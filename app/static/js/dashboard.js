const PIPELINE_PHASES = ["prepare", "load", "analyzing", "ticketing", "finalize"];

function isSkipPositiveTicketsEnabled() {
  const csvPanel = document.getElementById("importPanelCsv");
  if (csvPanel && !csvPanel.classList.contains("d-none")) {
    return document.getElementById("skipPositiveTicketsSwitchCsv")?.checked ?? false;
  }
  return document.getElementById("skipPositiveTicketsSwitch")?.checked ?? false;
}

function appendSkipPositiveTickets(formData) {
  if (isSkipPositiveTicketsEnabled()) {
    formData.set("skip_positive_tickets", "1");
  }
}

function syncSkipPositiveTicketsSwitches(source) {
  const playSkip = document.getElementById("skipPositiveTicketsSwitch");
  const csvSkip = document.getElementById("skipPositiveTicketsSwitchCsv");
  if (!playSkip || !csvSkip) return;
  const checked = source ? source.checked : playSkip.checked;
  playSkip.checked = checked;
  csvSkip.checked = checked;
}

function getStickyNavScrollOffset() {
  const nav = document.getElementById("appNav");
  const navH = nav ? nav.getBoundingClientRect().height : 0;
  const gap = 16;
  return navH + gap;
}

function scrollToAnalysisPipeline() {
  const card = document.getElementById("analysisPipelineCard");
  if (!card) return;
  requestAnimationFrame(() => {
    const offset = getStickyNavScrollOffset();
    const top = card.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  });
}

const RB_SCROLL_PIPELINE_KEY = "rb_scroll_to_pipeline";

function markRestorePipelineScroll() {
  try {
    sessionStorage.setItem(RB_SCROLL_PIPELINE_KEY, "1");
  } catch (_err) {}
}

function consumeRestorePipelineScroll() {
  try {
    const should = sessionStorage.getItem(RB_SCROLL_PIPELINE_KEY) === "1";
    sessionStorage.removeItem(RB_SCROLL_PIPELINE_KEY);
    return should;
  } catch (_err) {
    return false;
  }
}

function setPipelineStepsPending(steps) {
  steps.forEach((step) => {
    step.classList.remove("is-done", "is-active", "is-pending", "is-error");
    step.classList.add("is-pending");
  });
}

function updateAnalysisPipeline(data) {
  const card = document.getElementById("analysisPipelineCard");
  if (!card) return;

  const currentAction = document.getElementById("pipelineCurrentAction");
  const percentEl = document.getElementById("pipelineProgressPercent");
  const bar = document.getElementById("pipelineProgressBar");
  const badge = document.getElementById("pipelineStatusBadge");
  const appNameEl = document.getElementById("pipelineAppName");
  const appIconEl = document.getElementById("pipelineAppIcon");
  const steps = document.querySelectorAll("#pipelineSteps .pipeline-step");

  const progress = Math.max(0, Math.min(100, Number(data.progress || 0)));
  const phase = data.phase || "prepare";
  const status = data.status || "running";
  const jobType = data.job_type || "play_fetch";
  const isIdle = status === "idle";

  card.classList.toggle("is-idle", isIdle);

  if (percentEl) percentEl.textContent = `${progress}%`;
  if (bar) {
    bar.style.width = `${progress}%`;
    bar.classList.toggle("progress-bar-striped", !isIdle && (status === "running" || status === "queued"));
    bar.classList.toggle("progress-bar-animated", !isIdle && (status === "running" || status === "queued"));
    bar.classList.toggle("bg-success", status === "completed");
    bar.classList.toggle("bg-danger", status === "error");
  }
  if (currentAction) {
    currentAction.textContent = data.message || (isIdle ? "No analysis running." : "Processing…");
  }
  if (appNameEl && data.app_name) appNameEl.textContent = data.app_name;
  if (appIconEl && data.app_icon) {
    appIconEl.src = data.app_icon;
    appIconEl.style.display = "";
  }

  const statFetched = document.getElementById("statFetched");
  const statProcessed = document.getElementById("statProcessed");
  const statRefreshed = document.getElementById("statRefreshed");
  const statSkipped = document.getElementById("statSkipped");
  const statTicketsNew = document.getElementById("statTicketsNew");
  const statJira = document.getElementById("statJira");
  const statZendesk = document.getElementById("statZendesk");
  if (statFetched) statFetched.textContent = String(data.fetched ?? 0);
  if (statProcessed) statProcessed.textContent = String(data.processed ?? 0);
  if (statRefreshed) statRefreshed.textContent = String(data.refreshed ?? 0);
  if (statSkipped) statSkipped.textContent = String(data.skipped ?? 0);
  const ticketsNew = (data.jira_tickets ?? 0) + (data.zendesk_tickets ?? 0);
  if (statTicketsNew) statTicketsNew.textContent = String(ticketsNew);
  if (statJira) statJira.textContent = String(data.jira_tickets ?? 0);
  if (statZendesk) statZendesk.textContent = String(data.zendesk_tickets ?? 0);

  if (isIdle) {
    setPipelineStepsPending(steps);
    if (badge) {
      badge.textContent = "Ready";
      badge.classList.remove("text-bg-primary", "text-bg-success", "text-bg-danger", "text-bg-warning");
      badge.classList.add("text-bg-secondary");
    }
    return;
  }

  const phaseIndex = PIPELINE_PHASES.indexOf(phase);
  const isComplete = status === "completed";
  const isError = status === "error";

  steps.forEach((step) => {
    const stepPhase = step.dataset.phase;
    const stepIdx = PIPELINE_PHASES.indexOf(stepPhase);
    const desc = step.querySelector(".pipeline-step-desc");
    if (desc) {
      const label = jobType === "csv_upload" ? desc.dataset.csv : desc.dataset.play;
      if (label) desc.textContent = label;
    }

    step.classList.remove("is-done", "is-active", "is-pending", "is-error");
    if (isComplete) {
      step.classList.add("is-done");
    } else if (isError && stepPhase === phase) {
      step.classList.add("is-error");
    } else if (stepIdx < phaseIndex) {
      step.classList.add("is-done");
    } else if (stepIdx === phaseIndex) {
      step.classList.add("is-active");
    } else {
      step.classList.add("is-pending");
    }
  });

  if (badge) {
    badge.classList.remove("text-bg-primary", "text-bg-success", "text-bg-danger", "text-bg-warning");
    if (isComplete) {
      badge.textContent = "Complete";
      badge.classList.add("text-bg-success");
    } else if (isError) {
      badge.textContent = "Failed";
      badge.classList.add("text-bg-danger");
    } else if (status === "cancelled") {
      badge.textContent = "Cancelled";
      badge.classList.add("text-bg-warning");
    } else {
      badge.textContent = status === "queued" ? "Queued" : "Running";
      badge.classList.add("text-bg-primary");
    }
  }
}

function isAnalysisJobRunning() {
  return Boolean(window.__rbJobRunning);
}

function setAnalysisJobRunning(running) {
  window.__rbJobRunning = running;
  const fetchBtn = document.getElementById("btnFetchLimited");
  const fetchAllBtn = document.getElementById("btnFetchAllReviews");
  const csvBtn = document.getElementById("btnCsvUpload");
  const searchInput = document.getElementById("appSearchInput");

  [fetchBtn, fetchAllBtn, csvBtn].forEach((btn) => {
    if (btn) btn.disabled = running;
  });
  if (searchInput) searchInput.readOnly = running;
}

function setAnalysisBackdrop(active) {
  const main = document.getElementById("dashboardMainContent");
  if (main) main.classList.toggle("analysis-backdrop-active", active);
}

function resetPipelineCard() {
  const card = document.getElementById("analysisPipelineCard");
  if (card) card.classList.remove("is-idle");
  updateAnalysisPipeline({
    status: "running",
    phase: "prepare",
    progress: 0,
    message: "Starting analysis…",
    app_name: "App",
    app_icon: "https://cdn.simpleicons.org/googleplay/34A853",
    job_type: "play_fetch",
    fetched: 0,
    processed: 0,
    refreshed: 0,
    skipped: 0,
    jira_tickets: 0,
    zendesk_tickets: 0,
  });
  const bar = document.getElementById("pipelineProgressBar");
  if (bar) {
    bar.classList.remove("bg-success", "bg-danger");
    bar.classList.add("progress-bar-striped", "progress-bar-animated");
  }
}

function createCharts() {
  if (document.body.dataset.chartsEnabled === "false") {
    return;
  }
  const sentimentCanvas = document.getElementById("sentimentChart");
  if (sentimentCanvas && sentimentCanvas.offsetParent !== null) {
    const positive = Number(sentimentCanvas.dataset.positive || 0);
    const negative = Number(sentimentCanvas.dataset.negative || 0);
    const neutral = Number(sentimentCanvas.dataset.neutral || 0);

    new Chart(sentimentCanvas, {
      type: "doughnut",
      data: {
        labels: ["Positive", "Negative", "Neutral"],
        datasets: [{ data: [positive, negative, neutral], backgroundColor: ["#22c55e", "#ef4444", "#94a3b8"], borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
        cutout: "68%",
      },
    });
  }

  const categoryCanvas = document.getElementById("categoryChart");
  if (categoryCanvas && categoryCanvas.offsetParent !== null) {
    const bugs = Number(categoryCanvas.dataset.bugs || 0);
    const features = Number(categoryCanvas.dataset.features || 0);
    const support = Number(categoryCanvas.dataset.support || 0);
    const complaints = Number(categoryCanvas.dataset.complaints || 0);

    new Chart(categoryCanvas, {
      type: "bar",
      data: {
        labels: ["Bug", "Feature", "Support", "Complaint"],
        datasets: [{
          label: "Count",
          data: [bugs, features, support, complaints],
          backgroundColor: ["#f59e0b", "#3b82f6", "#8b5cf6", "#ef4444"],
          borderRadius: 6,
          barThickness: 18,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { font: { size: 10 } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { font: { size: 10 }, precision: 0 } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }
}

function updateSelectedAppChip() {
  const chip = document.getElementById("selectedAppPreview");
  const packageInput = document.getElementById("packageNameInput");
  const appNameInput = document.getElementById("appNameInput");
  if (!chip || !packageInput) return;
  const pkg = packageInput.value.trim();
  if (!pkg) {
    chip.textContent = "";
    chip.classList.add("d-none");
    return;
  }
  const name = (appNameInput?.value || "").trim() || pkg;
  chip.textContent = `${name} · ${pkg}`;
  chip.classList.remove("d-none");
}

function syncQuickPicksRowHeights() {
  const importCard = document.getElementById("dataImportCard");
  const quickCard = document.getElementById("quickPicksCard");
  const scroll = quickCard?.querySelector(".quick-picks-scroll");
  if (!importCard || !quickCard || !scroll) return;

  const stacked = !window.matchMedia("(min-width: 992px)").matches;
  if (stacked) {
    quickCard.style.height = "";
    quickCard.style.minHeight = "";
    scroll.style.maxHeight = "";
    scroll.style.flex = "";
    scroll.style.minHeight = "";
    return;
  }

  quickCard.style.height = "";
  quickCard.style.minHeight = "";

  const importH = Math.round(importCard.getBoundingClientRect().height);
  quickCard.style.height = `${importH}px`;
  scroll.style.maxHeight = "";
  scroll.style.flex = "1";
  scroll.style.minHeight = "0";

  requestAnimationFrame(() => {
    const diff = Math.round(quickCard.getBoundingClientRect().height - importCard.getBoundingClientRect().height);
    if (diff !== 0) {
      quickCard.style.height = `${importH - diff}px`;
    }
  });
}

function initQuickPicksHeightSync() {
  const importBody = document.querySelector("#dataImportCard .rb-card-body");
  const importPanelPlay = document.getElementById("importPanelPlay");
  const importPanelCsv = document.getElementById("importPanelCsv");
  if (!importBody) return;

  const runSync = () => {
    requestAnimationFrame(() => {
      requestAnimationFrame(syncQuickPicksRowHeights);
    });
  };

  runSync();

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(runSync);
    observer.observe(importBody);
    if (importPanelPlay) observer.observe(importPanelPlay);
    if (importPanelCsv) observer.observe(importPanelCsv);
  }

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(runSync, 100);
  });
}

function initImportTabs() {
  const card = document.getElementById("dataImportCard");
  const playPanel = document.getElementById("importPanelPlay");
  const csvPanel = document.getElementById("importPanelCsv");
  if (!card || !playPanel || !csvPanel) return;

  const tabs = card.querySelectorAll("[data-import-tab]");
  const setPanel = (name) => {
    const isPlay = name === "play";
    playPanel.classList.toggle("is-active", isPlay);
    playPanel.classList.toggle("d-none", !isPlay);
    csvPanel.classList.toggle("is-active", !isPlay);
    csvPanel.classList.toggle("d-none", isPlay);
    tabs.forEach((tab) => {
      const active = tab.dataset.importTab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    syncSkipPositiveTicketsSwitches();
    requestAnimationFrame(syncQuickPicksRowHeights);
  };

  const playSkip = document.getElementById("skipPositiveTicketsSwitch");
  const csvSkip = document.getElementById("skipPositiveTicketsSwitchCsv");
  playSkip?.addEventListener("change", () => syncSkipPositiveTicketsSwitches(playSkip));
  csvSkip?.addEventListener("change", () => syncSkipPositiveTicketsSwitches(csvSkip));
  syncSkipPositiveTicketsSwitches();

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setPanel(tab.dataset.importTab || "play");
    });
  });
}

function initCsvFileInput() {
  const input = document.getElementById("csvFileInput");
  const nameEl = document.getElementById("csvFileName");
  if (!input || !nameEl) return;
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    nameEl.textContent = file ? file.name : "No file chosen";
  });
}

function initPopularAppButtons() {
  const form = document.getElementById("liveFetchForm");
  const packageInput = document.getElementById("packageNameInput");
  const appNameInput = document.getElementById("appNameInput");
  const appIconInput = document.getElementById("appIconInput");
  const fetchAllFlag = document.getElementById("fetchAllFlag");
  const quickPickFetchAllToggle = document.getElementById("quickPickFetchAllToggle");

  if (!form || !packageInput || !appNameInput) return;

  document.querySelectorAll(".popular-app-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isAnalysisJobRunning()) return;
      packageInput.value = btn.dataset.package || "";
      appNameInput.value = btn.dataset.appName || "";
      if (appIconInput) appIconInput.value = btn.querySelector("img")?.getAttribute("src") || "";
      if (fetchAllFlag) fetchAllFlag.value = quickPickFetchAllToggle?.checked ? "1" : "";
      updateSelectedAppChip();
      form.requestSubmit();
    });
  });
}

function initFetchAllButton() {
  const form = document.getElementById("liveFetchForm");
  const btn = document.getElementById("btnFetchAllReviews");
  const btnLimited = document.getElementById("btnFetchLimited");
  const flag = document.getElementById("fetchAllFlag");
  if (!form || !btn || !flag) return;
  btnLimited?.addEventListener("click", () => {
    flag.value = "";
  });
  btn.addEventListener("click", () => {
    flag.value = "1";
    form.requestSubmit();
  });
}

function initAdvancedOptionsToggle() {
  const toggleSwitch = document.getElementById("toggleAdvancedOptionsSwitch");
  const panel = document.getElementById("advancedOptionsPanel");
  const packageManual = document.getElementById("packageNameManual");
  const packageHidden = document.getElementById("packageNameInput");
  if (!toggleSwitch || !panel) return;
  const advancedFields = panel.querySelectorAll(".advanced-field");
  advancedFields.forEach((el) => {
    el.disabled = true;
  });
  toggleSwitch.addEventListener("change", () => {
    const willShow = toggleSwitch.checked;
    panel.classList.toggle("d-none", !willShow);
    advancedFields.forEach((el) => {
      el.disabled = !toggleSwitch.checked;
    });
    requestAnimationFrame(() => {
      requestAnimationFrame(syncQuickPicksRowHeights);
    });
  });
  packageManual?.addEventListener("input", () => {
    if (packageHidden) packageHidden.value = packageManual.value.trim();
  });
}

function initAnalysisPipeline() {
  const form = document.getElementById("liveFetchForm");
  const csvForm = document.getElementById("csvUploadForm");
  const card = document.getElementById("analysisPipelineCard");
  const searchInput = document.getElementById("appSearchInput");
  const packageInput = document.getElementById("packageNameInput");
  const appNameInput = document.getElementById("appNameInput");
  const appIconInput = document.getElementById("appIconInput");
  const langEl = document.getElementById("fetchLangInput");
  const countryEl = document.getElementById("fetchCountryInput");
  if (!card) return;

  const hasReviewResults = card.dataset.hasReviewResults === "true";

  let polling = null;
  let completing = false;
  let currentJobId = null;

  const showPipeline = () => {
    card.classList.remove("d-none", "opacity-0");
    setAnalysisBackdrop(true);
  };

  const hidePipelineBackdrop = () => {
    setAnalysisBackdrop(false);
    setAnalysisJobRunning(false);
  };

  const showPipelineIdle = () => {
    card.classList.remove("d-none", "opacity-0");
    hidePipelineBackdrop();
    updateAnalysisPipeline({
      status: "idle",
      progress: 0,
      message: "No analysis running. Start a fetch or upload above.",
      app_name: "App",
      app_icon: "https://cdn.simpleicons.org/googleplay/34A853",
      job_type: "play_fetch",
      fetched: 0,
      processed: 0,
      refreshed: 0,
      skipped: 0,
      jira_tickets: 0,
      zendesk_tickets: 0,
    });
  };

  const hydrateSnapshot = () => {
    const raw = card.dataset.pipelineSnapshot;
    if (!raw || raw === "null" || raw === "") return null;
    try {
      return JSON.parse(raw);
    } catch (_err) {
      return null;
    }
  };

  const showPipelineBridge = (snapshot) => {
    card.classList.remove("d-none", "opacity-0");
    hidePipelineBackdrop();
    if (snapshot) updateAnalysisPipeline(snapshot);
  };

  const activateCompletedBatch = async (jobId) => {
    const res = await fetch(`/fetch/activate/${encodeURIComponent(jobId)}`, { method: "POST", credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!data.ok) {
      alert(data.error || "Could not activate this batch.");
      window.location.href = "/analysis";
      return;
    }
    const since = data.batch_started_at;
    if (since) {
      markRestorePipelineScroll();
      window.location.href = `/analysis?since=${encodeURIComponent(since)}`;
    } else {
      window.location.href = "/analysis";
    }
  };

  const abortToDashboard = async () => {
    if (polling) clearInterval(polling);
    polling = null;
    currentJobId = null;
    completing = false;
    setAnalysisJobRunning(false);
    try {
      await fetch("/fetch/dismiss-active", { method: "POST", credentials: "same-origin" });
    } catch (_err) {
    }
    window.location.href = "/analysis";
  };

  const finishAndActivate = async (jobId, data) => {
    completing = true;
    clearInterval(polling);
    polling = null;
    currentJobId = null;
    setAnalysisJobRunning(false);
    updateAnalysisPipeline({ ...data, status: data.status, phase: "finalize", progress: 100 });
    await new Promise((r) => setTimeout(r, 800));
    await activateCompletedBatch(jobId);
  };

  const handleJobStatus = async (jobId, data) => {
    updateAnalysisPipeline(data);

    if (data.status === "completed" && !completing) {
      await finishAndActivate(jobId, data);
    } else if (data.status === "cancelled") {
      await abortToDashboard();
    } else if (data.status === "error") {
      clearInterval(polling);
      polling = null;
      currentJobId = null;
      completing = false;
      card.classList.remove("d-none", "opacity-0");
      hidePipelineBackdrop();
      alert(`Analysis failed: ${data.message || "Unknown error"}`);
    }
  };

  const recoverFromStaleJob = async () => {
    if (polling) clearInterval(polling);
    polling = null;
    currentJobId = null;
    completing = false;
    card.dataset.activeJobId = "";

    try {
      await fetch("/fetch/dismiss-active", { method: "POST", credentials: "same-origin" });
    } catch (_err) {
    }

    if (hasReviewResults) {
      const snapshot = hydrateSnapshot();
      if (snapshot) {
        showPipelineBridge(snapshot);
      } else {
        showPipelineIdle();
      }
    } else {
      showPipelineIdle();
    }
  };

  const pollJobOnce = async (jobId) => {
    const res = await fetch(`/fetch/status/${encodeURIComponent(jobId)}`, { credentials: "same-origin" });
    let data = {};
    try {
      data = await res.json();
    } catch (_err) {
      data = {};
    }

    if (res.status === 404 || data.stale || !data.ok) {
      await recoverFromStaleJob();
      return false;
    }

    await handleJobStatus(jobId, data);
    return true;
  };

  const startPolling = (jobId) => {
    showPipeline();
    if (polling) clearInterval(polling);
    completing = false;
    currentJobId = jobId;
    setAnalysisJobRunning(true);

    pollJobOnce(jobId);

    polling = setInterval(() => {
      pollJobOnce(jobId).catch(() => {});
    }, 1000);
  };

  const startJob = async (url, formData, initialMessage) => {
    if (isAnalysisJobRunning()) return;

    showPipeline();

    updateAnalysisPipeline({
      status: "running",
      phase: "prepare",
      progress: 2,
      message: initialMessage,
      app_name: formData.get("app_name") || "App",
      app_icon: formData.get("app_icon") || "",
      fetched: 0,
      processed: 0,
      refreshed: 0,
      skipped: 0,
      jira_tickets: 0,
      zendesk_tickets: 0,
    });
    scrollToAnalysisPipeline();

    try {
      const res = await fetch(url, { method: "POST", body: formData, credentials: "same-origin" });
      const data = await res.json();
      if (!data.ok) {
        showPipelineIdle();
        alert(data.error || "Unable to start analysis job.");
        return;
      }
      const jobId = data.job_id;
      if (jobId) {
        card.dataset.activeJobId = jobId;
        startPolling(jobId);
      }
    } catch (_err) {
      showPipelineIdle();
      alert("Network error while starting analysis.");
    }
  };

  const activeJobId = card.dataset.activeJobId;

  if (activeJobId) {
    showPipeline();
    scrollToAnalysisPipeline();
    startPolling(activeJobId);
  } else if (hasReviewResults) {
    const snapshot = hydrateSnapshot();
    if (snapshot) {
      showPipelineBridge(snapshot);
    } else {
      showPipelineIdle();
    }
  } else {
    showPipelineIdle();
  }

  if (consumeRestorePipelineScroll()) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => scrollToAnalysisPipeline());
    });
  }

  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && isAnalysisJobRunning()) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isAnalysisJobRunning()) return;

      if (packageInput && !packageInput.value.trim()) {
        const query = (searchInput?.value || "").trim();
        if (!query) {
          alert("Please type app name or choose an app from suggestions.");
          return;
        }
        try {
          const langHidden = document.getElementById("fetchLangHidden");
    const lang = langEl ? langEl.value.trim() : (langHidden ? langHidden.value.trim() : "");
          const country = countryEl ? countryEl.value.trim() : "ww";
          const lookupUrl = `/api/app-suggestions?q=${encodeURIComponent(query)}&limit=1&lang=${encodeURIComponent(lang)}&country=${encodeURIComponent(country)}`;
          const lookupRes = await fetch(lookupUrl, { credentials: "same-origin" });
          const lookupApps = await lookupRes.json();
          if (Array.isArray(lookupApps) && lookupApps.length > 0) {
            const top = lookupApps[0];
            packageInput.value = top.package_name || "";
            if (appNameInput) appNameInput.value = top.app_name || query;
            if (appIconInput) appIconInput.value = top.icon || "";
            updateSelectedAppChip();
          }
        } catch (_err) {
        }
      }

      if (packageInput && !packageInput.value.trim()) {
        alert("Package name is required. Please select an app from suggestions.");
        return;
      }

      const langHidden = document.getElementById("fetchLangHidden");
      const langInput = document.getElementById("fetchLangInput");
      const advPanel = document.getElementById("advancedOptionsPanel");
      const advToggle = document.getElementById("toggleAdvancedOptionsSwitch");
      if (langHidden) {
        const advancedOpen = advToggle?.checked && advPanel && !advPanel.classList.contains("d-none");
        langHidden.value = advancedOpen && langInput ? langInput.value.trim() : "";
      }

      const sortHidden = document.getElementById("fetchSortHidden");
      const sortInput = document.getElementById("fetchSortInput");
      if (sortHidden) {
        const advancedOpen = advToggle?.checked && advPanel && !advPanel.classList.contains("d-none");
        sortHidden.value = advancedOpen && sortInput ? sortInput.value : "newest";
      }

      const advancedFields = form.querySelectorAll(".advanced-field");
      advancedFields.forEach((el) => {
        el.disabled = false;
      });
      const formData = new FormData(form);
      advancedFields.forEach((el) => {
        const panel = document.getElementById("advancedOptionsPanel");
        const toggle = document.getElementById("toggleAdvancedOptionsSwitch");
        if (panel?.classList.contains("d-none") && toggle && !toggle.checked) {
          el.disabled = true;
        }
      });

      const appName = formData.get("app_name") || appNameInput?.value || "App";
      const appIcon = formData.get("app_icon") || appIconInput?.value || "";
      formData.set("app_name", appName);
      if (appIcon) formData.set("app_icon", appIcon);
      appendSkipPositiveTickets(formData);

      await startJob("/fetch/start", formData, "Starting Google Play fetch…");
    });
  }

  if (csvForm) {
    csvForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isAnalysisJobRunning()) return;
      const formData = new FormData(csvForm);
      const appName = (formData.get("app_name") || "My App").toString().trim();
      formData.set("app_name", appName);
      appendSkipPositiveTickets(formData);
      await startJob("/upload/start", formData, "Starting CSV analysis…");
    });
  }
}

function initAppSuggestions() {
  const input = document.getElementById("appSearchInput");
  const suggestionsBox = document.getElementById("appSuggestions");
  const form = document.getElementById("liveFetchForm");
  const packageInput = document.getElementById("packageNameInput");
  const appNameInput = document.getElementById("appNameInput");
  const appIconInput = document.getElementById("appIconInput");

  if (!input || !suggestionsBox || !form || !packageInput || !appNameInput) return;

  let debounceTimer = null;
  let inFlight = null;
  let defaults = [];
  try {
    defaults = JSON.parse(input.dataset.defaultApps || "[]");
  } catch (_err) {
    defaults = [];
  }

  const hideSuggestions = () => {
    suggestionsBox.classList.add("d-none");
    suggestionsBox.innerHTML = "";
  };

  const searchWrap = input.closest(".app-search-wrap");

  const renderSuggestions = (apps, opts = {}) => {
    if (!apps.length) {
      hideSuggestions();
      return;
    }

    const headerLabel = opts.defaults ? "Suggested apps" : "Matching apps";

    suggestionsBox.innerHTML = `
      <div class="suggestion-list-header text-uppercase small text-muted px-3 py-2 border-bottom">${headerLabel}</div>
      <div class="suggestion-list-body">
        ${apps
          .map(
            (app) => `
          <button type="button" class="suggestion-item" role="option" data-package="${app.package_name}" data-app-name="${app.app_name}" data-app-icon="${app.icon || ""}">
            <div class="d-flex align-items-center gap-3">
              <img src="${app.icon || ""}" alt="" class="app-icon suggestion-app-icon" onerror="this.style.display='none'">
              <span class="suggestion-text-block">
                <span class="suggestion-title d-block">${app.app_name}</span>
                <span class="suggestion-meta d-block">${app.package_name}${app.developer ? " · " + app.developer : ""}</span>
              </span>
            </div>
          </button>
        `
          )
          .join("")}
      </div>`;

    suggestionsBox.classList.remove("d-none");

    suggestionsBox.querySelectorAll(".suggestion-item").forEach((item) => {
      item.addEventListener("click", () => {
        if (isAnalysisJobRunning()) return;
        packageInput.value = item.dataset.package || "";
        appNameInput.value = item.dataset.appName || "";
        input.value = item.dataset.appName || "";
        if (appIconInput) appIconInput.value = item.dataset.appIcon || "";
        const ff = document.getElementById("fetchAllFlag");
        if (ff) ff.value = "";
        const pkgManual = document.getElementById("packageNameManual");
        if (pkgManual) pkgManual.value = packageInput.value;
        updateSelectedAppChip();
        hideSuggestions();
      });
    });
  };

  const renderDefaultSuggestions = () => {
    if (!defaults.length) {
      hideSuggestions();
      return;
    }
    const shuffled = [...defaults].sort(() => Math.random() - 0.5);
    renderSuggestions(shuffled.slice(0, 6), { defaults: true });
  };

  input.addEventListener("input", () => {
    const query = input.value.trim();
    const langEl = document.getElementById("fetchLangInput");
    const countryEl = document.getElementById("fetchCountryInput");
    const langHidden = document.getElementById("fetchLangHidden");
    const lang = langEl ? langEl.value.trim() : (langHidden ? langHidden.value.trim() : "");
    const country = countryEl ? countryEl.value.trim() : "ww";

    if (debounceTimer) clearTimeout(debounceTimer);
    if (query.length < 1) {
      renderDefaultSuggestions();
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        if (inFlight) inFlight.abort();
        inFlight = new AbortController();
        const url = `/api/app-suggestions?q=${encodeURIComponent(query)}&limit=20&lang=${encodeURIComponent(lang)}&country=${encodeURIComponent(country)}`;
        const response = await fetch(url, { signal: inFlight.signal, credentials: "same-origin" });
        const apps = await response.json();
        renderSuggestions(Array.isArray(apps) ? apps : []);
      } catch (_err) {
        if (_err && _err.name === "AbortError") return;
        hideSuggestions();
      }
    }, 80);
  });

  document.addEventListener("click", (event) => {
    if (searchWrap && !searchWrap.contains(event.target)) {
      hideSuggestions();
    }
  });

  input.addEventListener("focus", () => {
    if (!input.value.trim()) {
      renderDefaultSuggestions();
    }
  });
}

function initReviewResultsFilter() {
  const root = document.getElementById("reviewsResultsCard");
  if (root && typeof window.mountReviewTableFilter === "function") {
    window.mountReviewTableFilter(root);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  createCharts();
  initQuickPicksHeightSync();
  initImportTabs();
  initCsvFileInput();
  initPopularAppButtons();
  initFetchAllButton();
  initAdvancedOptionsToggle();
  initAnalysisPipeline();
  initAppSuggestions();
  initReviewResultsFilter();
});
