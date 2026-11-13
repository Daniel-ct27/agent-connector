/** Shared demo helpers — no page state lives here. */
window.DemoCommon = {
  chartColors: {
    grpc: "#0b6e4f",
    http: "#b45309",
    ink: "#121814",
    signal: "#cfef3a",
  },

  async api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        typeof data.detail === "string" ? data.detail : res.statusText
      );
    }
    return data;
  },

  findings(report, wallMs, meanMs, concurrency) {
    if (!report) return "No report yet.";
    const sev = report.severity
      ? `${report.severity.level} · score ${report.severity.score}`
      : "severity pending";
    const cause = report.log_analysis?.likely_cause || "cause pending";
    const top = report.runbook && (report.runbook.recommendations || [])[0];
    const runbook = top
      ? `${top.title} (${Math.round((top.confidence || 0) * 100)}%)`
      : "runbook pending";
    const agents = (report.agent_outcomes || [])
      .map((o) => `${o.name}:${o.status}`)
      .join(" · ");
    return `<div><b>${sev}</b></div>
      <div>Cause: ${cause}</div>
      <div>Runbook: ${runbook}</div>
      <div>Wall ${wallMs.toFixed(1)} ms · mean ${meanMs.toFixed(1)} ms · x${concurrency}</div>
      <div>${agents || "no agent outcomes"}</div>`;
  },

  syncSource(sourceEl, fixtureField, payloadField, payloadCustomField) {
    const generated = sourceEl.value === "generated";
    fixtureField.classList.toggle("hidden", generated);
    if (payloadField) payloadField.classList.toggle("hidden", !generated);
    if (payloadCustomField) {
      payloadCustomField.classList.toggle("hidden", !generated);
    }
  },

  async loadFixtureOptions(fixtureEl, payloadEl, concurrencyEl, payloadCustom) {
    const data = await DemoCommon.api("/api/fixtures");
    fixtureEl.innerHTML = "";
    for (const name of data.fixtures) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name.replace(".json", "");
      fixtureEl.appendChild(opt);
    }
    if (payloadEl) {
      payloadEl.innerHTML = "";
      for (const size of data.payload_sizes) {
        const opt = document.createElement("option");
        opt.value = String(size);
        opt.textContent = size.toLocaleString();
        if (size === 1000) opt.selected = true;
        payloadEl.appendChild(opt);
      }
    }
    if (concurrencyEl) {
      concurrencyEl.innerHTML = "";
      for (const level of data.concurrency_levels) {
        const opt = document.createElement("option");
        opt.value = String(level);
        opt.textContent = String(level);
        if (level === 1) opt.selected = true;
        concurrencyEl.appendChild(opt);
      }
    }
    if (payloadCustom) {
      payloadCustom.max = data.max_log_entries;
    }
    return data;
  },
};
