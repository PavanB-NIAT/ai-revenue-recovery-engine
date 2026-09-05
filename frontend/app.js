/**
 * Recovery Control Center — Frontend Application Logic
 * Zero-dependency, offline-ready vanilla JS controller.
 */

// Global Application State
let appState = {
  benchmark: null,
  portfolio: null,
  transactions: [],
  filteredTransactions: [],
  selectedTransactionId: "txn_fail_1001",
  selectedTransaction: null,
  selectedTxId: "txn_fail_1001",
  searchTerm: "",
  categoryFilter: "ALL",
  statusFilter: "ALL"
};

// Format currency in INR
function formatINR(amount) {
  if (amount === undefined || amount === null) return "₹0.00";
  return "₹" + Number(amount).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

// Format percentages
function formatPct(val) {
  if (val === undefined || val === null) return "0.0%";
  return Number(val).toFixed(1) + "%";
}

// Lifecycle Stage Definition (1-10)
const LIFECYCLE_STAGES = [
  { step: 1, key: "FAILURE", name: "Failure" },
  { step: 2, key: "CONTEXT", name: "Context" },
  { step: 3, key: "CANDIDATES", name: "Candidates" },
  { step: 4, key: "RANK", name: "Rank" },
  { step: 5, key: "ALLOCATE", name: "Allocate" },
  { step: 6, key: "GUARDRAIL", name: "Guardrail" },
  { step: 7, key: "EXECUTE", name: "Execute" },
  { step: 8, key: "OUTCOME", name: "Outcome" },
  { step: 9, key: "REASSESS", name: "Reassess" },
  { step: 10, key: "TERMINATE", name: "Terminate" }
];

// Initialize Dashboard
async function initDashboard() {
  const errorOverlay = document.getElementById("errorOverlay");
  try {
    errorOverlay.classList.remove("visible");

    // Parallel fetch from server endpoints
    const [benchRes, portRes, txRes] = await Promise.all([
      fetch("/api/benchmark"),
      fetch("/api/portfolio-experiment"),
      fetch("/api/transactions")
    ]);

    if (!benchRes.ok || !portRes.ok || !txRes.ok) {
      throw new Error("One or more backend API endpoints returned an error");
    }

    appState.benchmark = await benchRes.json();
    appState.portfolio = await portRes.json();
    appState.transactions = await txRes.json();
    appState.filteredTransactions = [...appState.transactions];

    // Render all components
    renderExecutiveMetrics();
    renderBaselineVsContextual();
    renderPortfolioSection();
    renderSensitivitySection();
    renderTransactionTable();
    selectTransaction(appState.selectedTransactionId);
    setupEventListeners();

  } catch (err) {
    console.error("Dashboard initialization error:", err);
    errorOverlay.classList.add("visible");
  }
}

// 1. Executive Metrics
function renderExecutiveMetrics() {
  const b = appState.benchmark;
  if (!b) return;

  const ctx = b.contextual_engine;
  document.getElementById("metricRisk").textContent = formatINR(b.gross_revenue_at_risk);
  document.getElementById("metricRecovered").textContent = formatINR(ctx.gross_recovered);
  document.getElementById("metricRate").textContent = formatPct(ctx.recovery_rate_pct);
  document.getElementById("metricAttempts").textContent = ctx.attempts;
  document.getElementById("metricSuccesses").textContent = ctx.successful_recoveries;
  document.getElementById("metricEfficiency").textContent = formatPct(ctx.efficiency_pct);
}

// 2. Baseline vs Contextual Comparison Table
function renderBaselineVsContextual() {
  const b = appState.benchmark;
  if (!b) return;

  const base = b.baseline;
  const ctx = b.contextual_engine;

  document.getElementById("baseGmv").textContent = formatINR(base.gross_recovered);
  document.getElementById("baseRate").textContent = formatPct(base.recovery_rate_pct);
  document.getElementById("baseAttempts").textContent = base.attempts;
  document.getElementById("baseSuccesses").textContent = base.successful_recoveries;
  document.getElementById("baseFails").textContent = base.failed_executions;
  document.getElementById("baseEff").textContent = formatPct(base.efficiency_pct);
  document.getElementById("basePenalties").textContent = formatINR(base.simulated_penalties);
  document.getElementById("baseNet").textContent = formatINR(base.net_financial_recovery) + " (Net Loss)";

  document.getElementById("ctxGmv").textContent = formatINR(ctx.gross_recovered);
  document.getElementById("ctxRate").textContent = formatPct(ctx.recovery_rate_pct);
  document.getElementById("ctxAttempts").textContent = ctx.attempts;
  document.getElementById("ctxSuccesses").textContent = ctx.successful_recoveries;
  document.getElementById("ctxFails").textContent = ctx.failed_executions;
  document.getElementById("ctxEff").textContent = formatPct(ctx.efficiency_pct);
  document.getElementById("ctxNet").textContent = "+" + formatINR(ctx.net_financial_recovery);
}

// 3. Portfolio Allocation (K=20 Primary Experiment)
function renderPortfolioSection() {
  const p = appState.portfolio;
  if (!p) return;

  const comp = p.policy_comparison_primary_k;
  const fifo = comp.fifo_policy;
  const port = comp.portfolio_policy;
  const delta = comp.metrics_delta;

  document.getElementById("fifoSuccess").textContent = fifo.successful_recoveries;
  document.getElementById("fifoGmv").textContent = formatINR(fifo.recovered_gmv);
  document.getElementById("fifoNet").textContent = formatINR(fifo.net_recovered);
  document.getElementById("fifoEff").textContent = formatPct(fifo.recovery_efficiency_pct);

  document.getElementById("portSuccess").textContent = `${port.successful_recoveries} (+${port.successful_recoveries - fifo.successful_recoveries})`;
  document.getElementById("portGmv").textContent = formatINR(port.recovered_gmv);
  document.getElementById("portNet").textContent = formatINR(port.net_recovered);
  document.getElementById("portEff").textContent = `${formatPct(port.recovery_efficiency_pct)} (+${(port.recovery_efficiency_pct - fifo.recovery_efficiency_pct).toFixed(1)}%)`;

  document.getElementById("portDeltaGmv").textContent = `+${formatINR(delta.gmv_recovered_delta)} (+${delta.percentage_gain.toFixed(1)}% GMV)`;
}

// 4. Capacity Sensitivity Section
function renderSensitivitySection() {
  const p = appState.portfolio;
  if (!p || !p.capacity_sensitivity) return;

  const container = document.getElementById("sensitivityBarsContainer");
  container.innerHTML = "";

  const sens = p.capacity_sensitivity;
  const maxGmv = 120000; // Reference max for scale

  Object.values(sens).forEach(item => {
    const kVal = item.capacity_k;
    const fifoW = Math.min((item.fifo_recovered / maxGmv) * 100, 100);
    const portW = Math.min((item.portfolio_recovered / maxGmv) * 100, 100);

    let kSubtitle = "Strict Quota";
    if (kVal === 20) kSubtitle = "Primary Constraint";
    if (kVal === 30) kSubtitle = "Moderate Capacity";
    if (kVal === 43) kSubtitle = "0.0% measured difference";

    const isGain = item.delta_gmv > 0;
    const deltaText = isGain ? `+${formatINR(item.delta_gmv)} (+${item.pct_gain.toFixed(1)}%)` : "₹0.00 (0.0%)";

    const row = document.createElement("div");
    row.className = "sensitivity-row";
    row.innerHTML = `
      <div class="sensitivity-k-label">
        <span>Capacity K = ${kVal}</span>
        <small>${kSubtitle}</small>
      </div>
      <div class="sensitivity-bars">
        <div class="bar-track" title="FIFO: ${formatINR(item.fifo_recovered)}">
          <div class="bar-fill fifo" style="width: ${fifoW}%;"></div>
          <span class="bar-label">FIFO: ${formatINR(item.fifo_recovered)} (${item.fifo_successes} won)</span>
        </div>
        <div class="bar-track" title="Portfolio: ${formatINR(item.portfolio_recovered)}">
          <div class="bar-fill port" style="width: ${portW}%;"></div>
          <span class="bar-label">Portfolio: ${formatINR(item.portfolio_recovered)} (${item.portfolio_successes} won)</span>
        </div>
      </div>
      <div class="sensitivity-delta-chip ${isGain ? 'gain' : 'neutral'}">
        ${deltaText}
      </div>
    `;
    container.appendChild(row);
  });
}

// 5. Transaction Table Rendering & Filtering
function renderTransactionTable() {
  const tbody = document.getElementById("txTableBody");
  tbody.innerHTML = "";

  const txs = appState.filteredTransactions;
  document.getElementById("filteredTxCount").textContent = txs.length;

  txs.forEach(tx => {
    const tr = document.createElement("tr");
    tr.id = `row-${tx.transaction_id}`;
    if (tx.transaction_id === (appState.selectedTransactionId || appState.selectedTxId)) {
      tr.classList.add("selected");
    }

    // Status Pill calculation
    const status = tx.lifecycle?.final_status || "PENDING";
    let pillClass = "failed";
    let pillText = status;

    if (status === "RECOVERED") {
      pillClass = "recovered";
      pillText = "Recovered";
    } else if (status.includes("SUPPRESSED") || status.includes("CIRCUIT")) {
      pillClass = "suppressed";
      pillText = "Suppressed";
    } else if (tx.portfolio?.portfolio_status === "STARVED_CAPACITY_EXHAUSTED") {
      pillClass = "starved";
      pillText = "Starved (K=20)";
    } else if (status.includes("EXHAUSTED") || status.includes("ABANDONED")) {
      pillClass = "failed";
      pillText = "Failed Hop";
    }

    const sessionActive = tx.context?.session_active;
    const posturePill = sessionActive
      ? `<span class="pill active-session">In Checkout</span>`
      : `<span class="pill cold-session">Abandoned</span>`;

    const actionText = tx.portfolio?.portfolio_action || tx.lifecycle?.lifecycle_trace?.[0]?.action_executed || "None";

    tr.innerHTML = `
      <td class="tx-id-cell">${tx.transaction_id}</td>
      <td class="amount-cell">${formatINR(tx.amount)}</td>
      <td>${tx.primary_rail}</td>
      <td><code>${tx.error_code}</code></td>
      <td>${posturePill}</td>
      <td><small>${formatActionName(actionText)}</small></td>
      <td><span class="pill ${pillClass}">${pillText}</span></td>
    `;

    tr.addEventListener("click", () => {
      selectTransaction(tx.transaction_id);
    });

    tbody.appendChild(tr);
  });
}

function formatActionName(action) {
  if (!action || action === "None") return "None (Stopped)";
  return action
    .replace("SWITCH_SECONDARY_PG", "Switch Secondary PG")
    .replace("TRIGGER_CROSS_RAIL_UPI", "Cross-Rail UPI Intent")
    .replace("DISPATCH_FRICTIONLESS_AUTH_LINK", "1-Click Auth Link")
    .replace("DISPATCH_ASYNC_RECOVERY_LINK", "Async WhatsApp Link")
    .replace("SCHEDULE_MANDATE_BATCH", "Schedule Mandate")
    .replace("BLIND_SAME_RAIL_RETRY", "Blind Same-Rail Retry");
}

// 6. Filter & Search Controls
function setupEventListeners() {
  const searchInput = document.getElementById("txSearchInput");
  const categoryFilter = document.getElementById("categoryFilter");
  const statusFilter = document.getElementById("statusFilter");

  function applyFilters() {
    const q = searchInput.value.trim().toLowerCase();
    const cat = categoryFilter.value;
    const stat = statusFilter.value;

    appState.filteredTransactions = appState.transactions.filter(tx => {
      // Text match
      const matchText = !q || (
        tx.transaction_id.toLowerCase().includes(q) ||
        tx.error_code.toLowerCase().includes(q) ||
        tx.issuing_bank.toLowerCase().includes(q) ||
        (tx.error_description && tx.error_description.toLowerCase().includes(q))
      );

      // Category match
      const matchCat = (cat === "ALL") || (tx.failure_category === cat);

      // Status match
      let matchStat = true;
      const finalStatus = tx.lifecycle?.final_status || "";
      const portStatus = tx.portfolio?.portfolio_status || "";

      if (stat === "RECOVERED") {
        matchStat = finalStatus === "RECOVERED";
      } else if (stat === "SUPPRESSED") {
        matchStat = finalStatus.includes("SUPPRESSED") || finalStatus.includes("CIRCUIT");
      } else if (stat === "FAILED") {
        matchStat = finalStatus.includes("EXHAUSTED") || finalStatus.includes("ABANDONED");
      } else if (stat === "STARVED") {
        matchStat = portStatus === "STARVED_CAPACITY_EXHAUSTED";
      }

      return matchText && matchCat && matchStat;
    });

    renderTransactionTable();
    const currentId = appState.selectedTransactionId || appState.selectedTxId;
    const activeRow = document.getElementById(`row-${currentId}`);
    if (activeRow) activeRow.classList.add("selected");
  }

  searchInput.addEventListener("input", applyFilters);
  categoryFilter.addEventListener("change", applyFilters);
  statusFilter.addEventListener("change", applyFilters);
}

// 7. Authoritative Transaction Selection & State Binding
function selectTransaction(txId) {
  if (!txId) return;

  // 1. Authoritative selected ID
  appState.selectedTransactionId = txId;
  appState.selectedTxId = txId;

  // 2. Exact transaction object from authoritative transactions list
  const selectedTransaction = appState.transactions.find(t => t.transaction_id === txId);
  if (!selectedTransaction) {
    console.warn(`[State] Transaction ${txId} not found in authoritative dataset.`);
    return;
  }
  appState.selectedTransaction = selectedTransaction;

  // 3. Ensure transaction is visible in table; if currently filtered out, reset filters
  const isVisible = appState.filteredTransactions.some(t => t.transaction_id === txId);
  if (!isVisible) {
    const searchInput = document.getElementById("txSearchInput");
    const categoryFilter = document.getElementById("categoryFilter");
    const statusFilter = document.getElementById("statusFilter");
    if (searchInput) searchInput.value = "";
    if (categoryFilter) categoryFilter.value = "ALL";
    if (statusFilter) statusFilter.value = "ALL";
    appState.filteredTransactions = [...appState.transactions];
    renderTransactionTable();
  }

  // 4. Update table selection highlight
  document.querySelectorAll(".tx-table tr").forEach(r => r.classList.remove("selected"));
  const row = document.getElementById(`row-${txId}`);
  if (row) {
    row.classList.add("selected");
    row.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // 5. Update exemplar buttons highlight
  document.querySelectorAll(".exemplar-btn").forEach(btn => {
    const btnTx = btn.getAttribute("data-tx");
    if (btnTx === txId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // 6. ALL Inspector rendering derives STRICTLY from selectedTransaction
  renderInspector(selectedTransaction);

  // 7. Lifecycle stepper derives STRICTLY from selectedTransaction
  updateLifecycleStepper(selectedTransaction);
}

// 8. Render Inspector (Strictly derived from selectedTransaction)
function renderInspector(tx) {
  if (!tx) return;
  const panel = document.getElementById("inspectorPanel");
  if (!panel) return;

  // Status & recovery revenue
  const finalStatus = tx.lifecycle?.final_status || "PENDING";
  const recoveredAmt = tx.lifecycle?.recovered_revenue || 0;
  const isRecovered = finalStatus === "RECOVERED";

  // Build the "Why this action?" story from actual fields
  const whyActionStory = buildWhyActionStory(tx);

  // Build the "Why did this opportunity receive / miss capacity?" story
  const whyCapacityStory = buildWhyCapacityStory(tx);

  // Context snapshot items
  const ctx = tx.context || {};
  const pgHealth = ctx.secondary_pg_health !== undefined ? `${Math.round(ctx.secondary_pg_health * 100)}%` : "N/A";
  const cbsHealth = ctx.bank_cbs_health !== undefined ? `${Math.round(ctx.bank_cbs_health * 100)}%` : "N/A";
  const intentScore = ctx.intent_score !== undefined ? ctx.intent_score.toFixed(2) : "N/A";
  const timeSec = ctx.time_since_failure_sec !== undefined ? `${ctx.time_since_failure_sec}s` : "0s";
  const prefRail = ctx.customer_preferred_rail || "CARDS";

  // Lifecycle trace hops
  const traces = tx.lifecycle?.lifecycle_trace || [];
  let hopHtml = "";
  traces.forEach(t => {
    if (t.action_executed) {
      hopHtml += `
        <div class="hop-item">
          <div class="hop-header">
            <span>Hop ${t.hop}: ${formatActionName(t.action_executed)}</span>
            <span style="color: ${t.success ? 'var(--color-success)' : 'var(--color-danger)'};">${t.downstream_result}</span>
          </div>
          <div class="hop-desc">${t.rationale || "Executed recovery strategy."}</div>
          <div style="font-size: 11px; color: var(--text-muted);">
            Confidence: ${(t.confidence_score * 100).toFixed(1)}% &bull; EV: ${formatINR(t.expected_value)}
          </div>
        </div>
      `;
    } else if (t.event === "REASSESSMENT_TRIGGERED") {
      hopHtml += `
        <div class="hop-item reassessment">
          <div class="hop-header" style="color: var(--color-warning);">
            <span>State Reassessment Triggered (Hop ${t.hop})</span>
            <span>Posture: ${t.updated_posture || "MUTATED"}</span>
          </div>
          <div class="hop-desc">
            Failed action excluded from Hop 2. Intent score decayed to ${t.state_mutations?.new_intent_score || "N/A"}. Session active: ${t.state_mutations?.session_active ? 'True' : 'False'}.
          </div>
        </div>
      `;
    } else if (t.reason) {
      hopHtml += `
        <div class="hop-item" style="border-left-color: var(--text-muted);">
          <div class="hop-header"><span>Event: ${t.event || "HALTED"}</span></div>
          <div class="hop-desc">${t.reason}</div>
        </div>
      `;
    }
  });

  if (!hopHtml) {
    hopHtml = `<div style="color: var(--text-muted); font-size: 12px; font-style: italic;">Zero attempts executed (suppressed by guardrail).</div>`;
  }

  panel.innerHTML = `
    <div class="inspector-hero">
      <div class="inspector-id-block">
        <span class="inspector-tx-id">${tx.transaction_id}</span>
        <div class="inspector-meta-row">
          <span class="pill ${isRecovered ? 'recovered' : (finalStatus.includes('SUPPRESSED') ? 'suppressed' : 'failed')}">${finalStatus}</span>
          <span style="color: var(--text-muted); font-size: 12px;">${tx.primary_rail} &bull; ${tx.issuing_bank}</span>
        </div>
      </div>
      <div style="text-align: right;">
        <div class="inspector-amount">${formatINR(tx.amount)}</div>
        <span style="font-size: 11px; color: ${isRecovered ? 'var(--color-success)' : 'var(--text-muted)'};">
          ${isRecovered ? `Recovered: ${formatINR(recoveredAmt)}` : 'Recovered: ₹0.00'}
        </span>
      </div>
    </div>

    <!-- Why This Action? -->
    <div class="why-section">
      <div class="why-card">
        <div class="why-header">
          <span style="color: var(--accent-primary);">&bull;</span> Why this recovery action?
        </div>
        <div class="why-flow-steps">
          ${whyActionStory}
        </div>
      </div>
    </div>

    <!-- Why This Opportunity Received/Missed Capacity? -->
    <div class="why-section">
      <div class="why-card" style="border-left: 3px solid var(--color-cyan);">
        <div class="why-header">
          <span style="color: var(--color-cyan);">&bull;</span> Why did this opportunity receive / miss recovery capacity?
        </div>
        <div class="why-flow-steps">
          ${whyCapacityStory}
        </div>
      </div>
    </div>

    <!-- Context Signals Snapshot -->
    <div class="why-section">
      <span style="font-weight: 700; font-size: 12px; color: var(--text-secondary); text-transform: uppercase;">Contextual Telemetry Snapshot</span>
      <div class="context-grid">
        <div class="ctx-item">
          <span class="ctx-label">Session Posture</span>
          <span class="ctx-val" style="color: ${ctx.session_active ? 'var(--color-cyan)' : 'var(--text-muted)'};">
            ${ctx.session_active ? 'Active (Hot in Checkout)' : 'Abandoned (Warm/Cold)'}
          </span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Intent Score</span>
          <span class="ctx-val">${intentScore}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Secondary PG Health</span>
          <span class="ctx-val">${pgHealth}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Bank CBS Health</span>
          <span class="ctx-val">${cbsHealth}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">UPI Intent Viable</span>
          <span class="ctx-val">${ctx.customer_upi_intent_supported ? 'Yes' : 'No'}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Saved Mandate</span>
          <span class="ctx-val">${ctx.customer_has_saved_mandate ? 'Yes' : 'No'}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Preferred Rail</span>
          <span class="ctx-val">${prefRail}</span>
        </div>
        <div class="ctx-item">
          <span class="ctx-label">Latency Since Failure</span>
          <span class="ctx-val">${timeSec}</span>
        </div>
      </div>
    </div>

    <!-- Hop-by-Hop Trace History -->
    <div class="why-section">
      <span style="font-weight: 700; font-size: 12px; color: var(--text-secondary); text-transform: uppercase;">Lifecycle Execution &amp; Reassessment History</span>
      <div class="hop-trace-list">
        ${hopHtml}
      </div>
    </div>
  `;
}

// Helper: Build "Why this action?" explanation from actual fields
function buildWhyActionStory(tx) {
  const cat = tx.failure_category;
  const code = tx.error_code;
  const ctx = tx.context || {};
  const trace = tx.lifecycle?.lifecycle_trace?.[0];
  const finalStatus = tx.lifecycle?.final_status || "";

  let step1 = `<div class="flow-step"><span class="step-bullet">1</span><div class="step-text"><strong>Failure Observed:</strong> <code>${code}</code> (${cat}). ${tx.error_description || ""}</div></div>`;

  // Terminal case
  if (cat === "TERMINAL_FAILURE" || ctx.is_terminal_failure) {
    return `
      ${step1}
      <div class="flow-step"><span class="step-bullet">2</span><div class="step-text"><strong>Security Analysis:</strong> Failure code indicates permanent decline (card blocked or marked stolen).</div></div>
      <div class="flow-step"><span class="step-bullet">3</span><div class="step-text"><strong>Guardrail Triggered:</strong> <code>CIRCUIT_BREAKER_TERMINAL_FAILURE</code> executed. Completely blocks automated recovery attempts to eliminate fraud liability.</div></div>
      <div class="flow-step"><span class="step-bullet">4</span><div class="step-text"><strong>Outcome:</strong> 0 attempts dispatched &rarr; <code>SUPPRESSED_TERMINAL_FAILURE</code>.</div></div>
    `;
  }

  // Context signal step
  let step2Context = `User session ${ctx.session_active ? 'is active in checkout modal' : 'was abandoned'}; Secondary PG health is ${Math.round((ctx.secondary_pg_health||0)*100)}%; Issuing bank CBS is ${Math.round((ctx.bank_cbs_health||1)*100)}%.`;
  let step2 = `<div class="flow-step"><span class="step-bullet">2</span><div class="step-text"><strong>Context Evaluated:</strong> ${step2Context}</div></div>`;

  // Negative EV case
  if (finalStatus.includes("NEGATIVE_EV") || (trace && trace.expected_value <= 0)) {
    const candAction = trace?.action_evaluated || tx.portfolio?.portfolio_action || "DISPATCH_ASYNC_RECOVERY_LINK";
    return `
      ${step1}
      ${step2}
      <div class="flow-step"><span class="step-bullet">3</span><div class="step-text"><strong>Economic EV Guardrail:</strong> Order amount (${formatINR(tx.amount)}) with low intent (${(ctx.intent_score||0).toFixed(2)}) yields non-positive expected value (EV ≤ 0). Candidate strategy <code>${candAction}</code> routing fees exceed expected recovery.</div></div>
      <div class="flow-step"><span class="step-bullet">4</span><div class="step-text"><strong>Outcome:</strong> 0 attempts dispatched &rarr; <code>SUPPRESSED_NEGATIVE_EV</code> (protected merchant margin).</div></div>
    `;
  }

  // Normal contextual path
  const action = trace?.action_executed || tx.portfolio?.portfolio_action || "Selected Candidate";
  const rationale = trace?.rationale || "Evaluated best contextual fit.";
  const conf = trace?.confidence_score ? `${(trace.confidence_score * 100).toFixed(0)}%` : "High";
  const ev = trace?.expected_value ? formatINR(trace.expected_value) : "Positive";
  const downstreamResult = trace?.downstream_result || "EXECUTION_COMPLETE";

  let step3 = `<div class="flow-step"><span class="step-bullet">3</span><div class="step-text"><strong>Candidate Selected:</strong> <code>${action}</code> selected with ${conf} confidence and Expected Value ${ev}.</div></div>`;
  let step4 = `<div class="flow-step"><span class="step-bullet">4</span><div class="step-text"><strong>Algorithmic Rationale:</strong> ${rationale}</div></div>`;
  let step5 = `<div class="flow-step"><span class="step-bullet">5</span><div class="step-text"><strong>Execution Result:</strong> Downstream network returned <code>${downstreamResult}</code>. Final status: <strong>${finalStatus}</strong>.</div></div>`;

  return `${step1}${step2}${step3}${step4}${step5}`;
}

// Helper: Build "Why this opportunity received / missed capacity?" explanation
function buildWhyCapacityStory(tx) {
  const port = tx.portfolio || {};
  const rank = port.allocation_rank;
  const isEligible = port.is_eligible;
  const portStatus = port.portfolio_status;
  const ev = port.expected_value;

  if (!isEligible) {
    if (tx.failure_category === "TERMINAL_FAILURE" || tx.context?.is_terminal_failure) {
      return `<div class="flow-step"><span class="step-bullet" style="background-color: var(--color-danger); color: #fff;">!</span><div class="step-text"><strong>Excluded by Security Guardrail:</strong> Terminal decline (card stolen/blocked). Ineligible for capacity allocation under any policy.</div></div>`;
    }
    return `<div class="flow-step"><span class="step-bullet" style="background-color: var(--color-warning); color: #fff;">!</span><div class="step-text"><strong>Excluded by Economic Guardrail:</strong> Evaluated Expected Value is non-positive (EV ≤ 0). Excluded to avoid burning recovery budget on margin-dilutive attempts.</div></div>`;
  }

  if (rank && rank <= 20) {
    return `
      <div class="flow-step"><span class="step-bullet" style="background-color: var(--color-success); color: #fff;">&check;</span><div class="step-text"><strong>Allocated Capacity (Priority Rank #${rank} of 40):</strong> Opportunity ranked within top 20 by Expected Value (${formatINR(ev)}). Policy B allocated attempt quota to this transaction before capacity was exhausted.</div></div>
      <div class="flow-step"><span class="step-bullet">&bull;</span><div class="step-text"><strong>Execution Status under K=20:</strong> Dispatched attempt &rarr; Outcome: <strong>${portStatus}</strong>.</div></div>
    `;
  } else if (rank && rank > 20) {
    return `
      <div class="flow-step"><span class="step-bullet" style="background-color: var(--color-warning); color: #fff;">&minus;</span><div class="step-text"><strong>Starved of Capacity (Priority Rank #${rank} of 40):</strong> Eligible opportunity with positive EV (${formatINR(ev)}), but priority rank #${rank} fell outside the scarce capacity quota (K = 20).</div></div>
      <div class="flow-step"><span class="step-bullet">&bull;</span><div class="step-text"><strong>Economic Rationale:</strong> 20 higher-yield opportunities consumed available operational quota first. Status under K=20: <strong>STARVED_CAPACITY_EXHAUSTED</strong>.</div></div>
    `;
  }

  return `<div class="flow-step"><span class="step-bullet">&bull;</span><div class="step-text">Evaluated in portfolio experiment: Status <strong>${portStatus}</strong>.</div></div>`;
}

// 8. Update Lifecycle Stepper Flow
function updateLifecycleStepper(tx) {
  const nodes = document.querySelectorAll(".stepper-node");
  const caption = document.getElementById("activeTxLifecycleCaption");

  nodes.forEach(n => {
    n.classList.remove("active", "completed");
  });

  const finalStatus = tx.lifecycle?.final_status || "";
  const cat = tx.failure_category;
  const isTerminal = cat === "TERMINAL_FAILURE" || tx.context?.is_terminal_failure;
  const isNegativeEV = finalStatus.includes("NEGATIVE_EV");
  const traces = tx.lifecycle?.lifecycle_trace || [];
  const hasReassessment = traces.some(t => t.event === "REASSESSMENT_TRIGGERED");

  if (isTerminal) {
    caption.textContent = `Traversal: Terminal Security Short-Circuit (Halted at Guardrail)`;
    // 1 (Failure) -> 2 (Context) -> 6 (Guardrail) -> 10 (Terminate)
    setNodeState(1, "completed");
    setNodeState(2, "completed");
    setNodeState(6, "completed");
    setNodeState(10, "active");
  } else if (isNegativeEV) {
    caption.textContent = `Traversal: Economic EV Suppression (EV <= 0 at Guardrail)`;
    // 1 -> 2 -> 3 -> 4 -> 6 -> 10
    setNodeState(1, "completed");
    setNodeState(2, "completed");
    setNodeState(3, "completed");
    setNodeState(4, "completed");
    setNodeState(6, "completed");
    setNodeState(10, "active");
  } else if (hasReassessment) {
    caption.textContent = `Traversal: Multi-Hop Reassessment Loop (Hop 1 Failed -> Mutated -> Hop 2)`;
    // Full 1..10
    for (let i = 1; i <= 9; i++) setNodeState(i, "completed");
    setNodeState(10, "active");
  } else {
    // Single-hop path
    caption.textContent = `Traversal: Single-Hop Contextual Execution (Resolved at Hop 1)`;
    for (let i = 1; i <= 7; i++) setNodeState(i, "completed");
    setNodeState(8, "active");
  }
}

function setNodeState(stepNum, state) {
  const node = document.querySelector(`.stepper-node[data-step="${stepNum}"]`);
  if (node) node.classList.add(state);
}

// Global aliases for event handlers & backwards-compatibility
window.selectTransaction = selectTransaction;
window.selectExemplar = selectTransaction;
window.inspectTransaction = selectTransaction;

// Start application when DOM loads
window.addEventListener("DOMContentLoaded", () => {
  initDashboard();
});
