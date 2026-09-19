/* Reviews & Approvals: one page covering all five review/approval stages
   (Manager Review -> HOD Review -> HR Review & Calibration -> Plant Head
   Approval -> MD Final Approval). Which tabs a person sees follows the
   same VIEW/EDIT role grants the server enforces (roles.js); each tab
   only lists records currently sitting at that exact stage - a "queue"
   of work waiting on this person, not the full history (My Performance /
   performance-history already covers the full cross-stage history). */

const PMS_STAGES = [
  { key: "manager", label: "Manager Review", capView: "MANAGER_REVIEW_VIEW", capEdit: "MANAGER_REVIEW_EDIT", listPath: "/manager-reviews", matchStatus: "MANAGER_REVIEW" },
  { key: "hod", label: "HOD Review", capView: "HOD_REVIEW_VIEW", capEdit: "HOD_REVIEW_EDIT", listPath: "/hod-reviews", matchStatus: "HOD_REVIEW" },
  { key: "hr", label: "HR Review & Calibration", capView: "HR_REVIEW_VIEW", capEdit: "HR_REVIEW_EDIT", listPath: "/hr-reviews", matchStatus: "HR_REVIEW" },
  { key: "planthead", label: "Plant Head Approval", capView: "PLANT_HEAD_APPROVAL_VIEW", capEdit: "PLANT_HEAD_APPROVAL_EDIT", listPath: "/plant-head-approvals", matchStatus: "PLANT_HEAD_APPROVAL" },
  { key: "md", label: "MD Final Approval", capView: "MD_APPROVAL_VIEW", capEdit: "MD_APPROVAL_EDIT", listPath: "/md-approvals", matchStatus: "MD_APPROVAL" },
];

let pmsUser = null;
let pmsAvailableStages = [];
let pmsActiveStage = null;
let pmsExpanded = new Set();

function pmsStatusPillClass(status) {
  if (!status) return "pms-pill-neutral";
  const s = status.toUpperCase();
  if (s.includes("APPROVED") || s.includes("COMPLETE")) return "pms-pill-mint";
  return "pms-pill-amber";
}

async function pmsAskReason(promptText) {
  const reason = window.prompt(promptText);
  if (reason === null) return null;
  if (!reason.trim()) {
    alert("A reason is required.");
    return null;
  }
  return reason.trim();
}

/* ---------- Manager Review ---------- */

function pmsManagerKpiRow(record, kpi, editable) {
  const base = `pms-mrk-${kpi.employee_kpi_id}`;
  return `
    <div class="pms-mr-kpi">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
        <div style="font-weight:600;font-size:13px;">${kpi.kpi_name}</div>
        <div style="font-size:11.5px;color:var(--pms-text-faint);">Weightage: ${kpi.weightage}% &middot; Self Score: ${kpi.self_score != null ? kpi.self_score : "—"} (${kpi.self_achievement_pct != null ? kpi.self_achievement_pct + "%" : "—"})</div>
      </div>
      ${editable ? `
        <div class="pms-form-grid" style="margin-top:0;">
          <div>
            <label class="pms-label">Manager Score (1-5)</label>
            <input class="pms-field" type="number" min="1" max="5" id="${base}-score" value="${kpi.manager_score != null ? kpi.manager_score : ""}">
          </div>
          <div style="grid-column:1/-1;">
            <label class="pms-label">Manager Comments${kpi.manager_score != null && kpi.self_score != null && kpi.manager_score !== kpi.self_score ? " (required - score differs from self score)" : ""}</label>
            <textarea class="pms-field" id="${base}-comments">${kpi.manager_comments || ""}</textarea>
          </div>
          <div style="grid-column:1/-1;">
            <label class="pms-label">Development Requirement</label>
            <textarea class="pms-field" id="${base}-dev">${kpi.development_requirement || ""}</textarea>
          </div>
        </div>
        <button class="pms-btn-ghost" onclick="pmsSaveManagerKpi(${record.performance_id}, ${kpi.employee_kpi_id})">Save</button>
      ` : `
        <div style="font-size:12.5px;color:var(--pms-text-muted);">Manager Score: ${kpi.manager_score != null ? kpi.manager_score : "—"}${kpi.manager_comments ? " — " + kpi.manager_comments : ""}</div>
      `}
    </div>`;
}

function pmsManagerDetail(record, editable) {
  return `
    <div style="margin-top:14px;">
      ${record.kpis.map((k) => pmsManagerKpiRow(record, k, editable)).join("")}
      ${editable ? `
        <div style="margin-top:14px;display:flex;gap:10px;">
          <button class="pms-btn-primary" onclick="pmsManagerSubmit(${record.performance_id})">Submit to HOD Review</button>
          <button class="pms-btn-ghost" onclick="pmsManagerReturn(${record.performance_id})">Return to Employee</button>
        </div>` : ""}
    </div>`;
}

async function pmsSaveManagerKpi(performanceId, employeeKpiId) {
  const base = `pms-mrk-${employeeKpiId}`;
  const payload = {
    manager_score: document.getElementById(`${base}-score`).value ? parseInt(document.getElementById(`${base}-score`).value, 10) : null,
    manager_comments: document.getElementById(`${base}-comments`).value,
    development_requirement: document.getElementById(`${base}-dev`).value,
  };
  try {
    await PMS.put(`/manager-reviews/${performanceId}/kpis/${employeeKpiId}`, payload);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not save this KPI review.");
  }
}

async function pmsManagerSubmit(performanceId) {
  try {
    await PMS.post(`/manager-reviews/${performanceId}/submit`);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not submit this review.");
  }
}

async function pmsManagerReturn(performanceId) {
  const reason = await pmsAskReason("Reason for returning this record to the employee:");
  if (reason === null) return;
  try {
    await PMS.post(`/manager-reviews/${performanceId}/return`, { reason });
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not return this record.");
  }
}

/* ---------- Rating breakdown (shared: HOD/HR/Plant Head/MD all see the
   full chain of ratings so far - self assessment, manager score per KPI,
   plus HOD/HR/Plant Head summary scores once each stage has run). A field
   still null just means that stage hasn't happened yet. ---------- */

function pmsRatingBreakdownBlock(breakdown) {
  if (!breakdown) return "";
  const kpiRows = (breakdown.kpis || []).map((k) => `
    <tr>
      <td>${k.kpi_name}</td>
      <td>${k.weightage != null ? k.weightage + "%" : "—"}</td>
      <td>${k.self_score != null ? k.self_score : "—"}${k.self_achievement_pct != null ? " (" + k.self_achievement_pct + "%)" : ""}</td>
      <td>${k.manager_score != null ? k.manager_score : "—"}</td>
    </tr>`).join("");
  const summaryItems = [
    breakdown.hod_score != null ? `<div><span class="pms-label" style="display:inline;">HOD Score:</span> ${breakdown.hod_score}${breakdown.hod_comments ? " — " + breakdown.hod_comments : ""}</div>` : "",
    breakdown.hr_score != null ? `<div><span class="pms-label" style="display:inline;">HR Score:</span> ${breakdown.hr_score}${breakdown.calibration_adjustment ? " (adj " + breakdown.calibration_adjustment + (breakdown.adjustment_reason ? ": " + breakdown.adjustment_reason : "") + ")" : ""}${breakdown.hr_comments ? " — " + breakdown.hr_comments : ""}</div>` : "",
    breakdown.plant_head_decision != null ? `<div><span class="pms-label" style="display:inline;">Plant Head Decision:</span> ${breakdown.plant_head_decision}${breakdown.plant_head_comments ? " — " + breakdown.plant_head_comments : ""}</div>` : "",
  ].filter(Boolean).join("");
  return `
    <details class="pms-inline-note" style="margin-bottom:10px;">
      <summary style="cursor:pointer;font-weight:600;">Full rating breakdown (all stages so far)</summary>
      <div style="margin-top:8px;overflow-x:auto;">
        <table class="pms-table" style="min-width:480px;">
          <thead><tr><th>KPI</th><th>Weightage</th><th>Self Score</th><th>Manager Score</th></tr></thead>
          <tbody>${kpiRows || `<tr><td colspan="4">No KPI-level scores yet.</td></tr>`}</tbody>
        </table>
      </div>
      ${summaryItems ? `<div style="margin-top:8px;font-size:12.5px;line-height:1.7;">${summaryItems}</div>` : ""}
    </details>`;
}

/* ---------- HOD Review ---------- */

function pmsHodDetail(record, editable) {
  const base = `pms-hod-${record.performance_id}`;
  if (!editable) {
    return `<div style="margin-top:14px;font-size:12.5px;color:var(--pms-text-muted);">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      Manager weighted score: ${record.manager_weighted_score_pct != null ? record.manager_weighted_score_pct + "%" : "—"} &middot;
      HOD score: ${record.hod_score != null ? record.hod_score : "—"}
      ${record.hod_comments ? "<div style='margin-top:6px;'>" + record.hod_comments + "</div>" : ""}
    </div>`;
  }
  return `
    <div style="margin-top:14px;">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      <div class="pms-inline-note" style="margin-bottom:10px;">Manager weighted score (reference): ${record.manager_weighted_score_pct != null ? record.manager_weighted_score_pct + "%" : "—"}</div>
      <div class="pms-form-grid" style="margin-top:0;">
        <div>
          <label class="pms-label">HOD Score</label>
          <input class="pms-field" type="number" id="${base}-score" value="${record.hod_score != null ? record.hod_score : ""}">
        </div>
        <div style="grid-column:1/-1;">
          <label class="pms-label">HOD Comments${record.manager_weighted_score_pct != null ? " (required if score overrides the manager weighted score)" : ""}</label>
          <textarea class="pms-field" id="${base}-comments">${record.hod_comments || ""}</textarea>
        </div>
        <div>
          <label class="pms-label">Development Recommendation</label>
          <textarea class="pms-field" id="${base}-dev">${record.development_recommendation || ""}</textarea>
        </div>
        <div>
          <label class="pms-label">Training Requirement</label>
          <textarea class="pms-field" id="${base}-training">${record.training_requirement || ""}</textarea>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
        <button class="pms-btn-ghost" onclick="pmsSaveHod(${record.performance_id})">Save</button>
        <button class="pms-btn-primary" onclick="pmsHodApprove(${record.performance_id})">Approve & Forward to HR</button>
        <button class="pms-btn-ghost" onclick="pmsHodReturn(${record.performance_id}, 'return-to-manager')">Return to Manager</button>
        <button class="pms-btn-ghost" onclick="pmsHodReturn(${record.performance_id}, 'return-to-employee')">Return to Employee</button>
      </div>
    </div>`;
}

async function pmsSaveHod(performanceId) {
  const base = `pms-hod-${performanceId}`;
  const payload = {
    hod_score: document.getElementById(`${base}-score`).value ? parseFloat(document.getElementById(`${base}-score`).value) : null,
    hod_comments: document.getElementById(`${base}-comments`).value,
    development_recommendation: document.getElementById(`${base}-dev`).value,
    training_requirement: document.getElementById(`${base}-training`).value,
  };
  try {
    await PMS.put(`/hod-reviews/${performanceId}`, payload);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not save this HOD review.");
  }
}

async function pmsHodApprove(performanceId) {
  try {
    await PMS.post(`/hod-reviews/${performanceId}/approve`);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not approve this record.");
  }
}

async function pmsHodReturn(performanceId, endpoint) {
  const reason = await pmsAskReason("Reason for returning this record:");
  if (reason === null) return;
  try {
    await PMS.post(`/hod-reviews/${performanceId}/${endpoint}`, { reason });
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not return this record.");
  }
}

/* ---------- HR Review & Calibration ---------- */

function pmsHrDetail(record, editable) {
  const base = `pms-hr-${record.performance_id}`;
  if (!editable) {
    return `<div style="margin-top:14px;font-size:12.5px;color:var(--pms-text-muted);">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      HOD score: ${record.hod_score != null ? record.hod_score : "—"} &middot; HR score: ${record.hr_score != null ? record.hr_score : "—"}
      ${record.hr_comments ? "<div style='margin-top:6px;'>" + record.hr_comments + "</div>" : ""}
    </div>`;
  }
  return `
    <div style="margin-top:14px;">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      <div class="pms-inline-note" style="margin-bottom:10px;">HOD score (reference): ${record.hod_score != null ? record.hod_score : "—"}</div>
      <div class="pms-form-grid" style="margin-top:0;">
        <div>
          <label class="pms-label">Calibration Adjustment</label>
          <input class="pms-field" type="number" id="${base}-adj" value="${record.calibration_adjustment}">
        </div>
        <div>
          <label class="pms-label">HR Score (computed)</label>
          <input class="pms-field" type="number" value="${record.hr_score != null ? record.hr_score : ""}" disabled>
        </div>
        <div style="grid-column:1/-1;">
          <label class="pms-label">Adjustment Reason (required if adjustment is non-zero)</label>
          <textarea class="pms-field" id="${base}-reason">${record.adjustment_reason || ""}</textarea>
        </div>
        <div style="grid-column:1/-1;">
          <label class="pms-label">HR Comments</label>
          <textarea class="pms-field" id="${base}-comments">${record.hr_comments || ""}</textarea>
        </div>
        <div>
          <label class="pms-label">Training Recommendation</label>
          <textarea class="pms-field" id="${base}-training">${record.training_recommendation || ""}</textarea>
        </div>
        <div>
          <label class="pms-label">Career Development Recommendation</label>
          <textarea class="pms-field" id="${base}-career">${record.career_development_recommendation || ""}</textarea>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
        <button class="pms-btn-ghost" onclick="pmsSaveHr(${record.performance_id})">Save</button>
        <button class="pms-btn-primary" onclick="pmsHrComplete(${record.performance_id})">Complete Calibration & Forward to Plant Head</button>
      </div>
    </div>`;
}

async function pmsSaveHr(performanceId) {
  const base = `pms-hr-${performanceId}`;
  const payload = {
    calibration_adjustment: parseFloat(document.getElementById(`${base}-adj`).value || "0"),
    adjustment_reason: document.getElementById(`${base}-reason`).value,
    hr_comments: document.getElementById(`${base}-comments`).value,
    training_recommendation: document.getElementById(`${base}-training`).value,
    career_development_recommendation: document.getElementById(`${base}-career`).value,
  };
  try {
    await PMS.put(`/hr-reviews/${performanceId}`, payload);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not save this HR review.");
  }
}

async function pmsHrComplete(performanceId) {
  try {
    await PMS.post(`/hr-reviews/${performanceId}/complete`);
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not complete calibration for this record.");
  }
}

/* ---------- Plant Head Approval / MD Final Approval (same shape) ---------- */

function pmsApprovalDetail(record, editable, stageKey) {
  const base = `pms-${stageKey}-${record.performance_id}`;
  const isMd = stageKey === "md";
  if (!editable) {
    return `<div style="margin-top:14px;font-size:12.5px;color:var(--pms-text-muted);">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      HR score: ${record.hr_score != null ? record.hr_score : "—"} &middot; Decision: ${record.decision || "—"}
      ${record.comments ? "<div style='margin-top:6px;'>" + record.comments + "</div>" : ""}
    </div>`;
  }
  return `
    <div style="margin-top:14px;">
      ${pmsRatingBreakdownBlock(record.rating_breakdown)}
      <div class="pms-inline-note" style="margin-bottom:10px;">HR score (reference): ${record.hr_score != null ? record.hr_score : "—"}</div>
      <label class="pms-label">Comments${isMd ? "" : " (required to return)"}</label>
      <textarea class="pms-field" id="${base}-comments">${record.comments || ""}</textarea>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
        <button class="pms-btn-primary" onclick="pmsApprovalApprove('${stageKey}', ${record.performance_id})">
          ${isMd ? "Approve & Finalize (locks record, runs scoring)" : "Approve & Forward to MD"}
        </button>
        <button class="pms-btn-ghost" onclick="pmsApprovalReturn('${stageKey}', ${record.performance_id})">
          Return to ${isMd ? "Plant Head" : "HR"}
        </button>
      </div>
    </div>`;
}

async function pmsApprovalApprove(stageKey, performanceId) {
  const path = stageKey === "planthead" ? "/plant-head-approvals" : "/md-approvals";
  const comments = document.getElementById(`pms-${stageKey}-${performanceId}-comments`).value;
  try {
    await PMS.post(`${path}/${performanceId}/approve`, { comments: comments || null });
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not approve this record.");
  }
}

async function pmsApprovalReturn(stageKey, performanceId) {
  const path = stageKey === "planthead" ? "/plant-head-approvals" : "/md-approvals";
  const comments = document.getElementById(`pms-${stageKey}-${performanceId}-comments`).value;
  if (!comments || !comments.trim()) {
    alert("Comments are required to return this record.");
    return;
  }
  try {
    await PMS.post(`${path}/${performanceId}/return`, { comments });
    await pmsRenderActiveStage();
  } catch (err) {
    alert(err.message || "Could not return this record.");
  }
}

/* ---------- shared rendering ---------- */

function pmsRenderDetail(stage, record, editable) {
  if (stage.key === "manager") return pmsManagerDetail(record, editable);
  if (stage.key === "hod") return pmsHodDetail(record, editable);
  if (stage.key === "hr") return pmsHrDetail(record, editable);
  return pmsApprovalDetail(record, editable, stage.key);
}

function pmsRecordCard(stage, record, editable) {
  const expanded = pmsExpanded.has(record.performance_id);
  return `
    <div class="pms-card pms-record-card">
      <div class="pms-record-head">
        <div style="display:flex;align-items:center;gap:12px;">
          ${pmsAvatarHtml(record.employee_photo_url, record.employee_name)}
          <div>
            <div class="pms-record-title">${record.employee_name}</div>
            <div class="pms-record-sub">${record.cycle_name} &middot; Performance ID #${record.performance_id}</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <span class="pms-pill ${pmsStatusPillClass(record.status)}">${record.status.replace(/_/g, " ")}</span>
          <button class="pms-btn-ghost" onclick="pmsToggleRecord(${record.performance_id})">${expanded ? "Hide" : "Open"}</button>
        </div>
      </div>
      ${expanded ? pmsRenderDetail(stage, record, editable) : ""}
    </div>`;
}

async function pmsToggleRecord(performanceId) {
  if (pmsExpanded.has(performanceId)) {
    pmsExpanded.delete(performanceId);
  } else {
    pmsExpanded.add(performanceId);
  }
  await pmsRenderActiveStage();
}

function pmsRenderTabs() {
  const tabsEl = document.getElementById("pms-tabs");
  if (pmsAvailableStages.length <= 1) {
    tabsEl.classList.add("pms-hide");
    return;
  }
  tabsEl.classList.remove("pms-hide");
  tabsEl.innerHTML = pmsAvailableStages.map((s) =>
    `<button class="pms-chip ${s.key === pmsActiveStage.key ? "active" : ""}" onclick="pmsSwitchStage('${s.key}')">${s.label}</button>`
  ).join("");
}

async function pmsSwitchStage(key) {
  pmsActiveStage = pmsAvailableStages.find((s) => s.key === key) || pmsActiveStage;
  pmsExpanded.clear();
  pmsRenderTabs();
  await pmsRenderActiveStage();
}

async function pmsRenderActiveStage() {
  const recordsEl = document.getElementById("pms-records");
  const emptyEl = document.getElementById("pms-empty");
  const errorEl = document.getElementById("pms-error");
  errorEl.classList.add("pms-hide");
  const stage = pmsActiveStage;
  const editable = pmsHasCap(pmsUser.role_codes, stage.capEdit);
  try {
    const all = await PMS.get(stage.listPath);
    const records = all.filter((r) => r.status === stage.matchStatus);
    records.sort((a, b) => b.performance_id - a.performance_id);
    if (records.length === 0) {
      recordsEl.classList.add("pms-hide");
      emptyEl.classList.remove("pms-hide");
      return;
    }
    emptyEl.classList.add("pms-hide");
    recordsEl.innerHTML = records.map((r) => pmsRecordCard(stage, r, editable)).join("");
    recordsEl.classList.remove("pms-hide");
  } catch (err) {
    recordsEl.classList.add("pms-hide");
    emptyEl.classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load this review queue.";
    errorEl.classList.remove("pms-hide");
  }
}

async function pmsInitReviews() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "reviews");

  pmsAvailableStages = PMS_STAGES.filter((s) => pmsHasCap(pmsUser.role_codes, s.capView));
  document.getElementById("pms-loading").classList.add("pms-hide");

  if (pmsAvailableStages.length === 0) {
    document.getElementById("pms-no-access").classList.remove("pms-hide");
    return;
  }

  pmsActiveStage = pmsAvailableStages.find((s) => pmsHasCap(pmsUser.role_codes, s.capEdit)) || pmsAvailableStages[0];
  pmsRenderTabs();
  await pmsRenderActiveStage();
}

pmsInitReviews();
