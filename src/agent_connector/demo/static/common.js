/** Shared demo helpers — no page state lives here. */
window.DemoCommon = {
  chartColors: {
    grpc: "#0b6e4f",
    http: "#b45309",
    ink: "#121814",
    signal: "#cfef3a",
  },

  /** Keep filesystem paths and filenames out of the UI. */
  safeMessage(raw, fallback = "Request failed") {
    const text = typeof raw === "string" ? raw : "";
    if (!text.trim()) return fallback;
    return text
      .replace(/[A-Za-z]:\\[^\s"'<>]+/g, "[path]")
      .replace(/\/(?:[\w.-]+\/)+[\w.-]+/g, "[path]")
      .replace(/\b[\w.-]+\.(csv|env|json|py|md|txt|log|yml|yaml)\b/gi, "[file]")
      .replace(/\breport\/[^\s]+/gi, "[path]")
      .replace(/\bsecrets?[^\s]*/gi, "[hidden]");
  },

  scenarioLabel(name) {
    const raw = String(name || "")
      .replace(/^.*[\\/]/, "")
      .replace(/\.[^.]+$/, "")
      .trim();
    const key = raw.replace(/^inc-/, "").toLowerCase();
    const known = {
      "db-001": "Database connection failure",
      "db_001": "Database connection failure",
      db_connection_failure: "Database connection failure",
      "retry-001": "Payment retry storm",
      "retry_001": "Payment retry storm",
      retry_storm: "Payment retry storm",
      "cert-001": "Expired TLS certificate",
      "cert_001": "Expired TLS certificate",
      expired_certificate: "Expired TLS certificate",
      multi_signal_cascade: "Cascading multi-signal outage",
    };
    if (known[key]) return known[key];
    if (known[raw]) return known[raw];
    return key
      .replace(/[-_]+/g, " ")
      .replace(/\b\d+\b/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b\w/g, (c) => c.toUpperCase()) || "Live incident";
  },

  incidentLabel(id, scenario) {
    if (scenario) return DemoCommon.scenarioLabel(scenario);
    return DemoCommon.scenarioLabel(id);
  },

  severityBlurb(artifact) {
    if (!artifact) return "Flag status pending.";
    if (artifact.rationale && !/^score=\d+/i.test(artifact.rationale)) {
      return artifact.rationale;
    }
    const level = artifact.level || "UNKNOWN";
    const score = artifact.score == null ? "—" : `${artifact.score}/100`;
    const evidence = (artifact.evidence || []).slice(0, 2).join(" · ");
    return evidence
      ? `${level} (${score}). Signals: ${evidence}`
      : `${level} flag · ${score}.`;
  },

  async api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        DemoCommon.safeMessage(
          typeof data.detail === "string" ? data.detail : res.statusText
        )
      );
    }
    return data;
  },

  packageLine(report) {
    if (!report) return "No agent package yet.";
    const sev = report.severity
      ? `${report.severity.level}`
      : "severity pending";
    const cause = report.log_analysis?.likely_cause || "cause pending";
    const top = report.runbook && (report.runbook.recommendations || [])[0];
    const runbook = top ? top.title : "runbook pending";
    return `${sev} · ${cause} · ${runbook}`;
  },

  findings(report, wallMs, meanMs, concurrency) {
    if (!report) return "No report yet.";
    const sev = report.severity
      ? DemoCommon.severityBlurb({
          level: report.severity.level,
          score: report.severity.score,
          rationale: report.severity.rationale,
        })
      : "Severity still open.";
    return `<div><b>Agent package</b> — ${DemoCommon.packageLine(report)}</div>
      <div class="muted-line">${sev}</div>
      <div class="muted-line">Finished in ${wallMs.toFixed(0)}&nbsp;ms wall clock (mean request ${meanMs.toFixed(0)}&nbsp;ms · ${concurrency} parallel).</div>`;
  },

  /** Dead heat only when times match within eps (default 1 ms). No % fudge. */
  isDeadHeat(a, b, eps = 1) {
    if (a == null || b == null) return false;
    return Math.abs(Number(a) - Number(b)) <= eps;
  },

  /** Plain-English race story for someone with zero benchmark context. */
  raceStory(data) {
    const grpc = data.grpc.wall_latency_ms;
    const http = data.http.wall_latency_ms;
    const tie = DemoCommon.isDeadHeat(grpc, http);
    const winner = tie ? "TIE" : grpc < http ? "gRPC" : "HTTP";
    const loser = winner === "gRPC" ? "HTTP" : winner === "HTTP" ? "gRPC" : "—";
    const fast = Math.min(grpc, http);
    const slow = Math.max(grpc, http);
    const saved = slow - fast;
    const ratio =
      data.http_over_grpc_ratio != null
        ? data.http_over_grpc_ratio
        : slow / Math.max(fast, 0.001);
    const logs = data.log_count;
    const conc = data.concurrency;
    const sameWork =
      "Same agents, same logs, same severity + runbook job — only the wire format changed.";
    let headline;
    let detail;
    if (tie) {
      headline = `Dead heat — gRPC and HTTP finished together (~${grpc.toFixed(0)}&nbsp;ms).`;
      detail =
        `${sameWork} No meaningful gap this lap on ${logs.toLocaleString()} log lines` +
        (conc > 1 ? ` with ${conc} concurrent requests.` : ".");
    } else if (winner === "gRPC") {
      headline = `gRPC got the engineer package ${ratio.toFixed(1)}× sooner than HTTP.`;
      detail =
        `${sameWork} Lower wall time = the on-call sees the answer sooner. ` +
        `Here that gap is about ${saved.toFixed(0)}&nbsp;ms on ${logs.toLocaleString()} log lines` +
        (conc > 1 ? ` with ${conc} concurrent requests.` : ".");
    } else {
      headline = `HTTP finished first this lap (${(grpc / http).toFixed(1)}× vs gRPC).`;
      detail =
        `${sameWork} Lower wall time = the on-call sees the answer sooner. ` +
        `Here that gap is about ${saved.toFixed(0)}&nbsp;ms on ${logs.toLocaleString()} log lines` +
        (conc > 1 ? ` with ${conc} concurrent requests.` : ".");
    }
    return { winner, loser, headline, detail, ratio, saved, grpc, http, tie };
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
      opt.textContent = DemoCommon.scenarioLabel(name);
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

  flashButton(btn) {
    if (!btn) return;
    btn.classList.add("hit");
    setTimeout(() => btn.classList.remove("hit"), 220);
  },

  HANDOFF_KEY: "ac.agent-package-handoff",

  saveHandoff(payload) {
    try {
      sessionStorage.setItem(
        DemoCommon.HANDOFF_KEY,
        JSON.stringify({ ...payload, saved_at: Date.now() })
      );
    } catch (_) { /* ignore */ }
  },

  loadHandoff() {
    try {
      const raw = sessionStorage.getItem(DemoCommon.HANDOFF_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  },

  clearHandoff() {
    try {
      sessionStorage.removeItem(DemoCommon.HANDOFF_KEY);
    } catch (_) { /* ignore */ }
  },

  labHrefFromHandoff(handoff) {
    if (!handoff) return "/lab";
    const q = new URLSearchParams();
    q.set("from", "race-control");
    if (handoff.source) q.set("source", handoff.source);
    if (handoff.fixture) q.set("fixture", handoff.fixture);
    if (handoff.payload_size) q.set("payload", String(handoff.payload_size));
    return `/lab?${q.toString()}`;
  },

  /** Shared reactive chrome for every race-night page. */
  mountReactiveChrome() {
    document.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("pointerdown", () => DemoCommon.flashButton(btn));
    });

    document.querySelectorAll(".topnav .links a").forEach((link) => {
      link.addEventListener("pointerenter", () => link.classList.add("hot"));
      link.addEventListener("pointerleave", () => link.classList.remove("hot"));
    });

    document.querySelectorAll(".ops-card, .hub-card, .lab-lane").forEach((card) => {
      card.classList.add("reactive-card");
      card.addEventListener("pointermove", (ev) => {
        const r = card.getBoundingClientRect();
        const x = ((ev.clientX - r.left) / r.width) * 100;
        const y = ((ev.clientY - r.top) / r.height) * 100;
        card.style.setProperty("--mx", `${x}%`);
        card.style.setProperty("--my", `${y}%`);
        card.classList.add("lit");
      });
      card.addEventListener("pointerleave", () => {
        card.classList.remove("lit");
        card.style.removeProperty("--mx");
        card.style.removeProperty("--my");
      });
      card.addEventListener("click", () => {
        card.classList.add("selected");
        setTimeout(() => card.classList.remove("selected"), 700);
      });
    });

    document.querySelectorAll("select, input").forEach((el) => {
      el.addEventListener("focus", () => el.classList.add("select-hot"));
      el.addEventListener("blur", () => el.classList.remove("select-hot"));
      el.addEventListener("change", () => {
        el.classList.add("changed");
        setTimeout(() => el.classList.remove("changed"), 450);
      });
    });

    document.querySelectorAll(".start-lights").forEach((lights) => {
      lights.style.cursor = "pointer";
      lights.title = "Cycle lights";
      const modes = ["", "warmup", "armed", "go"];
      let i = modes.findIndex((m) => lights.classList.contains(m));
      if (i < 0) i = 0;
      lights.addEventListener("click", () => {
        i = (i + 1) % modes.length;
        lights.className =
          lights.className
            .split(/\s+/)
            .filter((c) => c && !["warmup", "armed", "go"].includes(c))
            .join(" ") + (modes[i] ? ` ${modes[i]}` : "");
      });
    });
  },
};

document.addEventListener("DOMContentLoaded", () => {
  if (document.body.classList.contains("race-night")) {
    DemoCommon.mountReactiveChrome();
  }
});
