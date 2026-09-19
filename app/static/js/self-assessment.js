/* Employee Self-Assessment workspace: acknowledge -> record achievement or
   self-score per KPI -> submit for Manager Review. Only the employee
   themselves may edit their own record (SELF_ASSESSMENT.EDIT). Every
   other visible role gets a read-only view (SELF_ASSESSMENT.VIEW). */

const PMS_NUMERIC_TARGET_TYPES = new Set(["NUMERIC", "PERCENTAGE", "RATIO", "QTY", "COST", "REDUCTION"]);

let pmsUser = null;
let pmsCanEdit = false;
let pmsExpanded = new Set();

function pmsStatusPillClass(status) {
  if (!status) return "pms-pill-neutral";
  const s = status.toUpperCase();
  if (s.includes("APPROVED") || s.includes("COMPLETE")) return "pms-pill-mint";
  if (s.includes("REJECT") || s.includes("RETURN")) return "pms-pill-red";
  if (s === "KPI_ASSIGNED" || s === "DRAFT") return "pms-pill-neutral";
  return "pms-pill-amber";
}

function pmsKpiRow(record, kpi) {
  const numeric = PMS_NUMERIC_TARGET_TYPES.has(kpi.measurement_type);
  const editable = pmsCanEdit && ["EMPLOYEE_ACKNOWLEDGED", "SELF_ASSESSMENT"].includes(record.status);
  const inputId = `pms-sa-${kpi.employee_kpi_id}`;

  return `
    <div class="pms-sa-kpi">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
        <div style="font-weight:600;font-size:13px;">${kpi.kpi_name}</div>
        <div style="font-size:11.5px;color:var(--pms-text-faint);">Target: ${kpi.target != null ? kpi.target : "—"} &middot; Weightage: ${kpi.weightage}%</div>
      </div>
      ${editable ? `
        <div class="pms-form-grid" style="margin-top:0;">
          ${numeric ? `
            <div>
              <label class="pms-label">Achievement</label>
              <input class="pms-field" type="number" id="${inputId}-achievement" value="${kpi.achievement != null ? kpi.achievement : ""}">
            </div>` : `
            <div>
              <label class="pms-label">Self Score (1-5)</label>
              <input class="pms-field" type="number" min="1" max="5" id="${inputId}-score" value="${kpi.self_score != null ? kpi.self_score : ""}">
            </div>`}
          <div style="grid-column:1/-1;">
            <label class="pms-label">Comments</label>
            <textarea class="pms-field" id="${inputId}-comments">${kpi.employee_comments || ""}</textarea>
          </div>
        </div>
        <button class="pms-btn-ghost" onclick="pmsSaveKpi(${record.performance_id}, ${kpi.employee_kpi_id})">Save</button>
      ` : `
        <div style="font-size:12.5px;color:var(--pms-text-muted);">
          ${numeric ? `Achievement: ${kpi.achievement != null ? kpi.achievement : "—"} (${kpi.achievement_pct != null ? kpi.achievement_pct + "%" : "—"})` : ""}
          Self Score: ${kpi.self_score != null ? kpi.self_score : "—"}
          ${kpi.employee_comments ? `<div style="margin-top:6px;color:var(--pms-text-faint);">${kpi.employee_comments}</div>` : ""}
        </div>
      `}
    </div>`;
}

function pmsRecordDetail(record) {
  if (record.status === "KPI_ASSIGNED") {
    return `
      <div style="margin-top:14px;">
        <button class="pms-btn-primary" onclick="pmsAcknowledge(${record.performance_id})">Acknowledge & Begin Self-Assessment</button>
      </div>`;
  }
  if (record.status === "RETURNED") {
    return `<div class="pms-inline-note" style="margin-top:14px;">This record was returned by your Manager/HOD. Re-editing a returned self-assessment isn't available in this build yet - contact your Manager for next steps.</div>`;
  }
  const canSubmit = pmsCanEdit && ["EMPLOYEE_ACKNOWLEDGED", "SELF_ASSESSMENT"].includes(record.status);
  return `
    <div style="margin-top:14px;">
      ${record.kpis.map((k) => pmsKpiRow(record, k)).join("")}
      ${canSubmit ? `
        <div style="margin-top:14px;">
          <button class="pms-btn-primary" onclick="pmsSubmitSelfAssessment(${record.performance_id})">Submit for Manager Review</button>
        </div>` : ""}
    </div>`;
}

function pmsRecordCard(record) {
  const expanded = pmsExpanded.has(record.performance_id);
  return `
    <div class="pms-card pms-record-card">
      <div class="pms-record-head">
        <div>
          <div class="pms-record-title">${record.cycle_name}</div>
          <div class="pms-record-sub">${record.employee_name} &middot; Performance ID #${record.performance_id}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <span class="pms-pill ${pmsStatusPillClass(record.status)}">${record.status.replace(/_/g, " ")}</span>
          <button class="pms-btn-ghost" onclick="pmsToggleRecord(${record.performance_id})">${expanded ? "Hide" : "Open"}</button>
        </div>
      </div>
      ${expanded ? pmsRecordDetail(record) : ""}
    </div>`;
}

async function pmsRenderRecords() {
  const recordsEl = document.getElementById("pms-records");
  const emptyEl = document.getElementById("pms-empty");
  try {
    const records = await PMS.get("/self-assessments");
    records.sort((a, b) => b.performance_id - a.performance_id);
    if (records.length === 0) {
      recordsEl.classList.add("pms-hide");
      emptyEl.classList.remove("pms-hide");
      return;
    }
    emptyEl.classList.add("pms-hide");
    recordsEl.innerHTML = records.map(pmsRecordCard).join("");
    recordsEl.classList.remove("pms-hide");
  } catch (err) {
    document.getElementById("pms-error").textContent = err.message || "Could not load self-assessments.";
    document.getElementById("pms-error").classList.remove("pms-hide");
  }
}

async function pmsToggleRecord(performanceId) {
  if (pmsExpanded.has(performanceId)) {
    pmsExpanded.delete(performanceId);
  } else {
    pmsExpanded.add(performanceId);
  }
  await pmsRenderRecords();
}

async function pmsAcknowledge(performanceId) {
  try {
    await PMS.post(`/self-assessments/${performanceId}/acknowledge`);
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not acknowledge this assignment.");
  }
}

async function pmsSaveKpi(performanceId, employeeKpiId) {
  const base = `pms-sa-${employeeKpiId}`;
  const achievementEl = document.getElementById(`${base}-achievement`);
  const scoreEl = document.getElementById(`${base}-score`);
  const commentsEl = document.getElementById(`${base}-comments`);
  const payload = { employee_comments: commentsEl ? commentsEl.value : null };
  if (achievementEl) payload.achievement = achievementEl.value ? parseFloat(achievementEl.value) : null;
  if (scoreEl) payload.self_score = scoreEl.value ? parseInt(scoreEl.value, 10) : null;
  try {
    await PMS.put(`/self-assessments/${performanceId}/kpis/${employeeKpiId}`, payload);
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not save this KPI.");
  }
}

async function pmsSubmitSelfAssessment(performanceId) {
  try {
    await PMS.post(`/self-assessments/${performanceId}/submit`);
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not submit your self-assessment.");
  }
}

async function pmsInitSelfAssessment() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "self-assessment");
  pmsCanEdit = pmsHasCap(pmsUser.role_codes, "SELF_ASSESSMENT_EDIT");

  document.getElementById("pms-header-sub").textContent = pmsCanEdit
    ? "Acknowledge your appraisal, record achievement against each KPI, and submit for Manager Review."
    : "Self-assessment records visible in your review scope (read-only).";

  try {
    document.getElementById("pms-loading").classList.add("pms-hide");
    await pmsRenderRecords();
  } catch (err) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-error").textContent = err.message || "Could not load self-assessment data.";
    document.getElementById("pms-error").classList.remove("pms-hide");
  }
}

pmsInitSelfAssessment();
