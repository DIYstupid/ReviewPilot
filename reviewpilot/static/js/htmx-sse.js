(function () {
  const STATUS_ORDER = [
    "pending",
    "fetching",
    "fetching_files",
    "building_context",
    "analyzing_summary",
    "analyzing_risks",
    "analyzing_lines",
    "validating_static",
    "postprocessing",
    "complete",
  ];

  const STATUS_LABELS = {
    pending: "Queued",
    fetching: "Fetching PR",
    fetching_files: "Fetching files",
    building_context: "Building context",
    analyzing_summary: "Generating summary",
    analyzing_risks: "Scanning risks",
    analyzing_lines: "Reviewing lines",
    validating_static: "Running static checks",
    postprocessing: "Post-processing",
    complete: "Complete",
    failed: "Failed",
  };

  function parseEvent(event) {
    if (!event.data) {
      return null;
    }
    try {
      return JSON.parse(event.data);
    } catch (_error) {
      return null;
    }
  }

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") {
      return fallback || "";
    }
    return String(value);
  }

  function node(tag, options, children) {
    const element = document.createElement(tag);
    const opts = options || {};
    if (opts.className) {
      element.className = opts.className;
    }
    if (opts.text !== undefined) {
      element.textContent = opts.text;
    }
    if (opts.id) {
      element.id = opts.id;
    }
    if (Array.isArray(children)) {
      for (const child of children) {
        element.append(child);
      }
    }
    return element;
  }

  function clearChildren(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function setHidden(element, hidden) {
    if (!element) {
      return;
    }
    element.classList.toggle("is-hidden", hidden);
  }

  function findingCard(finding) {
    const severity = text(finding.severity, "P3");
    const confidence = Math.round(Number(finding.confidence || 0) * 100);
    const location = finding.file_path
      ? `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}`
      : "";

    const header = node("header", { className: "finding-header" }, [
      node("span", { className: "severity-badge", text: severity }),
      node("h3", { text: text(finding.title, "Finding") }),
      node("span", { className: "confidence-badge", text: `${confidence}%` }),
    ]);

    const body = node("dl", { className: "finding-body" }, [
      node("dt", { text: "Evidence" }),
      node("dd", { text: text(finding.evidence, "No evidence provided.") }),
      node("dt", { text: "Recommendation" }),
      node("dd", { text: text(finding.recommendation, "No recommendation provided.") }),
    ]);

    const children = [header];
    if (location) {
      children.push(node("p", { className: "location break-anywhere", text: location }));
    }
    children.push(body);

    return node(
      "article",
      { className: `finding-card severity-${severity.toLowerCase()}` },
      children,
    );
  }

  function reportSection(title, children, count) {
    const headerChildren = [node("h2", { text: title })];
    if (count !== undefined) {
      headerChildren.push(node("span", { className: "count-badge", text: String(count) }));
    }
    return node("section", { className: "report-section" }, [
      node("div", { className: "section-header" }, headerChildren),
      ...children,
    ]);
  }

  function emptyState(message) {
    return node("p", { className: "empty-state", text: message });
  }

  function renderReport(report, elements) {
    clearChildren(elements.report);

    elements.report.append(
      reportSection("Summary", [
        node("p", { className: "summary-text", text: text(report.summary, "No summary returned.") }),
      ]),
      reportSection("Merge Conclusion", [
        node("p", {
          className: "conclusion-text",
          text: text(report.merge_conclusion, "No merge conclusion returned."),
        }),
      ]),
    );

    const risks = Array.isArray(report.risks) ? report.risks : [];
    const riskList = node("div", { className: "finding-list" });
    if (risks.length) {
      for (const finding of risks) {
        riskList.append(findingCard(finding));
      }
    } else {
      riskList.append(emptyState("No risk findings."));
    }
    elements.report.append(reportSection("Risks", [riskList], risks.length));

    const inlineReviews = Array.isArray(report.inline_reviews) ? report.inline_reviews : [];
    const inlineList = node("div", { className: "finding-list" });
    if (inlineReviews.length) {
      for (const finding of inlineReviews) {
        inlineList.append(findingCard(finding));
      }
    } else {
      inlineList.append(emptyState("No inline findings."));
    }
    elements.report.append(reportSection("Inline Review", [inlineList], inlineReviews.length));

    setHidden(elements.loading, true);
    setHidden(elements.error, true);
    setHidden(elements.report, false);
  }

  function updateStatus(status, elements) {
    const current = text(status, "pending");
    const currentIndex = STATUS_ORDER.indexOf(current);
    const terminalFailed = current === "failed";

    if (elements.pill) {
      elements.pill.textContent = STATUS_LABELS[current] || current.replaceAll("_", " ");
      elements.pill.classList.toggle("is-complete", current === "complete");
      elements.pill.classList.toggle("is-failed", terminalFailed);
    }
    if (elements.statusText) {
      elements.statusText.textContent = STATUS_LABELS[current] || current;
    }

    for (const step of document.querySelectorAll("[data-step]")) {
      const stepName = step.getAttribute("data-step");
      const stepIndex = STATUS_ORDER.indexOf(stepName);
      const isFailedStep = stepName === "failed";
      step.classList.toggle("is-current", stepName === current);
      step.classList.toggle("is-done", !terminalFailed && stepIndex !== -1 && stepIndex < currentIndex);
      if (terminalFailed) {
        step.classList.toggle("is-done", false);
        step.classList.toggle("is-current", isFailedStep);
      }
    }

    if (current === "complete" || terminalFailed) {
      setHidden(elements.loading, true);
    }
  }

  function showError(message, elements) {
    if (elements.errorMessage) {
      elements.errorMessage.textContent = text(message, "Review failed.");
    }
    setHidden(elements.loading, true);
    setHidden(elements.report, true);
    setHidden(elements.error, false);
    updateStatus("failed", elements);
  }

  function initReviewStream() {
    const root = document.querySelector("[data-review-stream-url]");
    if (!root) {
      return;
    }

    const elements = {
      loading: document.getElementById("loading-panel"),
      report: document.getElementById("report-content"),
      error: document.getElementById("error-panel"),
      errorMessage: document.querySelector("[data-error-message]"),
      pill: document.querySelector("[data-status-pill]"),
      statusText: document.querySelector("[data-status-text]"),
    };

    updateStatus(root.getAttribute("data-current-status") || "pending", elements);

    if (!window.EventSource) {
      return;
    }

    const source = new EventSource(root.getAttribute("data-review-stream-url"));
    source.addEventListener("status", function (event) {
      const payload = parseEvent(event);
      if (!payload || !payload.status) {
        return;
      }
      updateStatus(payload.status, elements);
      if (payload.status === "complete" || payload.status === "failed") {
        source.close();
      }
    });

    source.addEventListener("report", function (event) {
      const payload = parseEvent(event);
      if (payload) {
        renderReport(payload, elements);
      }
    });

    source.addEventListener("error", function (event) {
      const payload = parseEvent(event);
      if (payload && payload.message) {
        showError(payload.message, elements);
        source.close();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initReviewStream);
})();
