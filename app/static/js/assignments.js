/* KPA/KPI Assignment workspace. Manager/HR/Plant Head/MD/HR Admin hold
   ASSIGNMENT.EDIT (create, add/remove KPA/KPI, submit - "submit" is what
   moves a record out of DRAFT and is treated as the approval step).
   Employee holds ASSIGNMENT.PROPOSE - the same create/add/remove actions,
   scoped to their own record only, but never submit: a Manager reviewing
   and submitting an employee-proposed draft is what approves it. See
   app/api/routes/assignments.py's module docstring for the full design. */

let pmsUser = null;
let pmsCanEdit = false;
let pmsCanPropose = false;
let pmsKpaCatalog = [];
let pmsKpiCatalog = [];
let pmsExpanded = new Set();

function pmsStatusPillClass(status) {
  if (!status) return "pms-pill-neutral";
  const s = status.toUpperCase();
  if (s.includes("APPROVED") || s.includes("COMPLETE")) return "pms-pill-mint";
  if (s.includes("REJECT") || s.includes("PIP")) return "pms-pill-red";
  if (s === "DRAFT") return "pms-pill-neutral";
  return "pms-pill-amber";
}

async function pmsLoadCatalogs() {
  [pmsKpaCatalog, pmsKpiCatalog] = await Promise.all([
    PMS.get("/masters/kpa?active_only=true"),
    PMS.get("/masters/kpi?active_only=true"),
  ]);
}

function pmsKpisForKpa(kpaId) {
  return pmsKpiCatalog.filter((k) => k.kpa_id === kpaId);
}

function pmsKpaRow(record, employeeKpa) {
  const editable = record.status === "DRAFT" && (pmsCanEdit || pmsCanPropose);
  const usedKpiIds = new Set(employeeKpa.kpis.map((k) => k.kpi_id));
  const availableKpis = pmsKpisForKpa(employeeKpa.kpa_id).filter((k) => !usedKpiIds.has(k.kpi_id));

  const kpiRows = employeeKpa.kpis.map((kpi) => `
    <div class="pms-kpi-row-item">
      <div>
        <div style="font-weight:600;color:var(--pms-text-soft);">${kpi.kpi_name}</div>
        <div style="color:var(--pms-text-faint);margin-top:2px;">
          Target: ${kpi.target != null ? kpi.target : "—"}${kpi.unit ? " " + kpi.unit : ""} &middot; Weightage: ${kpi.weightage}%${kpi.due_date ? " &middot; Due " + kpi.due_date : ""}
        </div>
      </div>
      ${editable ? `<button class="pms-icon-btn" onclick="pmsRemoveKpi(${record.performance_id}, ${kpi.employee_kpi_id})">Remove</button>` : ""}
    </div>`).join("") || `<div class="pms-empty" style="padding:8px 0;">No KPIs added to this KPA yet.</div>`;

  const totalKpisForKpa = pmsKpisForKpa(employeeKpa.kpa_id).length;
  const addKpiForm = editable ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--pms-border-soft);">
      ${availableKpis.length === 0 ? `<div class="pms-inline-note">${
          totalKpisForKpa === 0
            ? "No KPIs exist under this KPA in the KPI Master yet - ask HR/Plant Head/MD to add one under Masters &gt; KPI before it can be assigned here."
            : "All catalog KPIs for this KPA are already added."
        }</div>` : `
      <div class="pms-form-grid" style="margin:0 0 8px 0;">
        <select class="pms-field" id="pms-kpi-select-${employeeKpa.employee_kpa_id}">
          ${availableKpis.map((k) => `<option value="${k.kpi_id}">${k.kpi_name} (${k.measurement_type})</option>`).join("")}
        </select>
        <input class="pms-field" type="number" placeholder="Weightage %" id="pms-kpi-weightage-${employeeKpa.employee_kpa_id}">
        <input class="pms-field" type="number" placeholder="Target" id="pms-kpi-target-${employeeKpa.employee_kpa_id}">
        <input class="pms-field" type="date" id="pms-kpi-duedate-${employeeKpa.employee_kpa_id}">
      </div>
      <button class="pms-btn-ghost" onclick="pmsAddKpi(${record.performance_id}, ${employeeKpa.employee_kpa_id})">+ Add KPI</button>
      `}
    </div>` : "";

  return `
    <div class="pms-kpa-block">
      <div class="pms-kpa-head">
        <div class="pms-kpa-name">${employeeKpa.kpa_name}</div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="font-size:11.5px;color:var(--pms-text-faint);">Rollup: ${employeeKpa.weightage}%</span>
          ${editable ? `<button class="pms-icon-btn" onclick="pmsRemoveKpa(${record.performance_id}, ${employeeKpa.employee_kpa_id})">Remove KPA</button>` : ""}
        </div>
      </div>
      ${kpiRows}
      ${addKpiForm}
    </div>`;
}

function pmsRecordDetail(record) {
  const editable = record.status === "DRAFT" && (pmsCanEdit || pmsCanPropose);
  const usedKpaIds = new Set(record.kpas.map((k) => k.kpa_id));
  const availableKpas = pmsKpaCatalog.filter((k) => !usedKpaIds.has(k.kpa_id));

  const addKpaForm = editable ? `
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--pms-border-soft);">
      ${availableKpas.length === 0 ? `<div class="pms-inline-note">All catalog KPAs are already added.</div>` : `
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <select class="pms-field" style="max-width:320px;" id="pms-kpa-select-${record.performance_id}">
          ${availableKpas.map((k) => `<option value="${k.kpa_id}">${k.kpa_name}</option>`).join("")}
        </select>
        <button class="pms-btn-ghost" onclick="pmsAddKpa(${record.performance_id})">+ Add KPA</button>
      </div>`}
    </div>` : "";

  const submitBtn = (record.status === "DRAFT" && pmsCanEdit) ? `
    <div style="margin-top:16px;">
      <button class="pms-btn-primary" onclick="pmsSubmitAssignment(${record.performance_id})">
        Submit${pmsCanPropose ? "" : " (approve & finalize KPI set)"}
      </button>
      <span class="pms-inline-note" style="margin-left:10px;">Total weightage must equal 100% (currently ${record.total_weightage}%).</span>
    </div>` : (record.status === "DRAFT" && pmsCanPropose ? `
    <div class="pms-inline-note" style="margin-top:16px;">Waiting on your Manager to review and submit this draft (current total weightage: ${record.total_weightage}%).</div>` : "");

  return `
    <div style="margin-top:14px;">
      ${record.kpas.map((ek) => pmsKpaRow(record, ek)).join("") || `<div class="pms-empty">No KPAs added yet.</div>`}
      ${addKpaForm}
      ${submitBtn}
    </div>`;
}

function pmsRecordCard(record) {
  const expanded = pmsExpanded.has(record.performance_id);
  return `
    <div class="pms-card pms-record-card">
      <div class="pms-record-head">
        <div>
          <div class="pms-record-title">${record.employee_name}</div>
          <div class="pms-record-sub">${record.cycle_name} &middot; Performance ID #${record.performance_id}${record.is_locked ? " &middot; Locked" : ""}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <span class="pms-pill ${pmsStatusPillClass(record.status)}">${record.status.replace(/_/g, " ")}</span>
          <button class="pms-btn-ghost" onclick="pmsToggleRecord(${record.performance_id})">${expanded ? "Hide" : "Manage"}</button>
        </div>
      </div>
      ${expanded ? pmsRecordDetail(record) : ""}
    </div>`;
}

async function pmsRenderRecords() {
  const recordsEl = document.getElementById("pms-records");
  const emptyEl = document.getElementById("pms-empty");
  try {
    const records = await PMS.get("/assignments");
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
    document.getElementById("pms-error").textContent = err.message || "Could not load assignments.";
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

async function pmsAddKpa(performanceId) {
  const select = document.getElementById(`pms-kpa-select-${performanceId}`);
  if (!select || !select.value) return;
  try {
    await PMS.post(`/assignments/${performanceId}/kpas`, { kpa_id: Number(select.value) });
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not add KPA.");
  }
}

async function pmsRemoveKpa(performanceId, employeeKpaId) {
  try {
    await fetch(`/assignments/${performanceId}/kpas/${employeeKpaId}`, { method: "DELETE", credentials: "same-origin" });
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not remove KPA.");
  }
}

async function pmsAddKpi(performanceId, employeeKpaId) {
  const kpiSelect = document.getElementById(`pms-kpi-select-${employeeKpaId}`);
  const weightageEl = document.getElementById(`pms-kpi-weightage-${employeeKpaId}`);
  const targetEl = document.getElementById(`pms-kpi-target-${employeeKpaId}`);
  const dueDateEl = document.getElementById(`pms-kpi-duedate-${employeeKpaId}`);
  if (!kpiSelect || !kpiSelect.value) return;
  const weightage = parseFloat(weightageEl.value);
  if (!weightage || weightage <= 0) {
    alert("Enter a weightage between 0 and 100 for this KPI.");
    return;
  }
  const payload = {
    kpi_id: Number(kpiSelect.value),
    weightage,
    target: targetEl.value ? parseFloat(targetEl.value) : null,
    due_date: dueDateEl.value || null,
  };
  try {
    await PMS.post(`/assignments/${performanceId}/kpas/${employeeKpaId}/kpis`, payload);
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not add KPI.");
  }
}

async function pmsRemoveKpi(performanceId, employeeKpiId) {
  try {
    await fetch(`/assignments/${performanceId}/kpis/${employeeKpiId}`, { method: "DELETE", credentials: "same-origin" });
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not remove KPI.");
  }
}

async function pmsSubmitAssignment(performanceId) {
  try {
    await PMS.post(`/assignments/${performanceId}/submit`);
    await pmsRenderRecords();
  } catch (err) {
    alert(err.message || "Could not submit this assignment.");
  }
}

async function pmsShowNewForm() {
  const form = document.getElementById("pms-new-form");
  form.classList.remove("pms-hide");

  const cycleSelect = document.getElementById("pms-new-cycle");
  const cycles = await PMS.get("/masters/performance-cycles?active_only=true");
  cycleSelect.innerHTML = cycles.map((c) => `<option value="${c.cycle_id}">${c.cycle_name}</option>`).join("")
    || `<option value="">No active cycle - ask HR to create one</option>`;

  const employeeField = document.getElementById("pms-employee-field");
  if (pmsCanEdit) {
    employeeField.classList.remove("pms-hide");
    const employeeSelect = document.getElementById("pms-new-employee");
    const employees = await PMS.get("/employees?active_only=true");
    employeeSelect.innerHTML = employees.map((e) => `<option value="${e.employee_id}">${e.full_name} (${e.employee_code})</option>`).join("");
  } else {
    employeeField.classList.add("pms-hide");
  }
}

async function pmsCreateAssignment() {
  const errorEl = document.getElementById("pms-new-error");
  errorEl.classList.add("pms-hide");
  const cycleSelect = document.getElementById("pms-new-cycle");
  if (!cycleSelect.value) {
    errorEl.textContent = "Select a performance cycle.";
    errorEl.classList.remove("pms-hide");
    return;
  }
  const employeeId = pmsCanEdit
    ? Number(document.getElementById("pms-new-employee").value)
    : pmsUser.employee_id;
  try {
    const created = await PMS.post("/assignments", { employee_id: employeeId, cycle_id: Number(cycleSelect.value) });
    document.getElementById("pms-new-form").classList.add("pms-hide");
    pmsExpanded.add(created.performance_id);
    await pmsRenderRecords();
  } catch (err) {
    errorEl.textContent = err.message || "Could not create assignment.";
    errorEl.classList.remove("pms-hide");
  }
}

async function pmsInitAssignments() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "assignments");

  pmsCanEdit = pmsHasCap(pmsUser.role_codes, "ASSIGNMENT_EDIT");
  pmsCanPropose = pmsHasCap(pmsUser.role_codes, "ASSIGNMENT_PROPOSE");

  if (pmsCanEdit || pmsCanPropose) {
    document.getElementById("pms-new-btn").classList.remove("pms-hide");
  }
  document.getElementById("pms-new-btn").addEventListener("click", pmsShowNewForm);
  document.getElementById("pms-new-cancel").addEventListener("click", () => {
    document.getElementById("pms-new-form").classList.add("pms-hide");
  });
  document.getElementById("pms-new-create").addEventListener("click", pmsCreateAssignment);

  document.getElementById("pms-header-sub").textContent = pmsCanEdit
    ? "Create draft assignments, add KPAs/KPIs and submit once weightage totals 100%."
    : pmsCanPropose
      ? "Propose your own KPAs/KPIs for the cycle - your Manager reviews and submits before it takes effect."
      : "View KPA/KPI assignments in your reporting scope.";

  try {
    await pmsLoadCatalogs();
    document.getElementById("pms-loading").classList.add("pms-hide");
    await pmsRenderRecords();
  } catch (err) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-error").textContent = err.message || "Could not load assignment data.";
    document.getElementById("pms-error").classList.remove("pms-hide");
  }
}

pmsInitAssignments();
