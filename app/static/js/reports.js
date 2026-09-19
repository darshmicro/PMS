/* Reports & Exports (M25): the consolidated, role-scoped appraisal status
   report (GET /reports/appraisal-status) plus the export catalog (GET
   /reports/catalog) - every export endpoint already shipped across the
   other 24 modules, filtered to what this caller's permissions actually
   reach. Catalog entries that operate on one specific record (a single
   self-assessment, review, approval, etc.) have no meaningful link from
   a catalog list - those are downloaded from that record's own screen
   (Assignments/Self-Assessment/Reviews) instead, via each row's own
   GET .../export endpoint, so this page marks them as such rather than
   guessing a record ID. */

// Maps a catalog entry's key to its real, parameter-free download path.
// (A few of REPORT_CATALOG's own endpoint_hint strings, e.g.
// "/performance-cycles/export" and "/scoring/scoring-rules/export",
// leave off the "/masters" router prefix those routes actually live
// under - this page links the real path rather than the hint literally.)
const PMS_DIRECT_EXPORTS = {
  employee_master: "/employees/export",
  performance_cycle: "/masters/performance-cycles/export",
  kpa_master: "/masters/kpa/export",
  kpi_master: "/masters/kpi/export",
  scoring_rules: "/masters/scoring-rules/export",
  rating_master: "/masters/ratings/export",
  competency_master: "/masters/competencies/export",
  attachments: "/attachments/export/list",
  notifications: "/notifications/export",
};

// org_masters bundles all 7 org-master types behind one catalog entry.
const PMS_ORG_MASTER_EXPORTS = [
  ["Companies", "/masters/companies/export"],
  ["Plants", "/masters/plants/export"],
  ["Departments", "/masters/departments/export"],
  ["Sections", "/masters/sections/export"],
  ["Designations", "/masters/designations/export"],
  ["Grades", "/masters/grades/export"],
  ["Employee Categories", "/masters/employee-categories/export"],
];

function pmsStatusPillClass(status) {
  if (!status) return "pms-pill-neutral";
  const s = status.toUpperCase();
  if (s.includes("APPROVED") || s.includes("COMPLETE")) return "pms-pill-mint";
  if (s.includes("DRAFT")) return "pms-pill-neutral";
  return "pms-pill-amber";
}

function pmsCatalogRow(entry) {
  if (entry.key === "org_masters") {
    const links = PMS_ORG_MASTER_EXPORTS.map(([label, path]) => `<a class="pms-chip" href="${path}">${label}</a>`).join("");
    return `
      <div class="pms-list-item">
        <div>
          <div style="font-weight:600;font-size:13px;">${entry.name}</div>
          <div style="font-size:11.5px;color:var(--pms-text-faint);margin-top:2px;">${entry.module}</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">${links}</div>
      </div>`;
  }
  const directPath = PMS_DIRECT_EXPORTS[entry.key];
  return `
    <div class="pms-list-item">
      <div>
        <div style="font-weight:600;font-size:13px;">${entry.name}</div>
        <div style="font-size:11.5px;color:var(--pms-text-faint);margin-top:2px;">${entry.module}</div>
      </div>
      ${directPath
        ? `<a class="pms-btn-ghost" href="${directPath}">Download</a>`
        : entry.key === "appraisal_status"
          ? `<span class="pms-inline-note">See the table above</span>`
          : `<span class="pms-inline-note">Download from that record's own screen (Assignments / Self-Assessment / Reviews)</span>`}
    </div>`;
}

function pmsStatusRow(row) {
  return `
    <tr>
      <td>${row.employee_name} <span style="color:var(--pms-text-faint);">(${row.employee_code})</span></td>
      <td>${row.cycle_name}</td>
      <td><span class="pms-pill ${pmsStatusPillClass(row.status)}">${row.status.replace(/_/g, " ")}</span></td>
      <td>${row.final_score_pct != null ? row.final_score_pct.toFixed(1) + "%" : "—"}</td>
      <td>${row.final_rating_label || "—"}</td>
      <td>${row.is_locked ? "Yes" : "No"}</td>
    </tr>`;
}

function pmsFilterQuery() {
  const employeeId = document.getElementById("pms-filter-employee").value;
  const cycleId = document.getElementById("pms-filter-cycle").value;
  const year = document.getElementById("pms-filter-year").value;
  const params = new URLSearchParams();
  if (employeeId) params.set("employee_id", employeeId);
  if (cycleId) params.set("cycle_id", cycleId);
  if (year) params.set("year", year);
  return params;
}

function pmsUpdateDownloadLinks() {
  const params = pmsFilterQuery();
  ["csv", "xlsx", "pdf"].forEach((fmt) => {
    const p = new URLSearchParams(params);
    p.set("format", fmt);
    document.getElementById(`pms-dl-${fmt}`).href = `/reports/appraisal-status?${p.toString()}`;
  });
}

async function pmsReloadStatusReport() {
  const table = document.getElementById("pms-status-table");
  const emptyEl = document.getElementById("pms-status-empty");
  const errorEl = document.getElementById("pms-error");
  errorEl.classList.add("pms-hide");
  emptyEl.classList.add("pms-hide");
  pmsUpdateDownloadLinks();
  try {
    const statusReport = await PMS.get(`/reports/appraisal-status?${pmsFilterQuery().toString()}`);
    document.getElementById("pms-status-scope").textContent = `Scope: ${statusReport.scope}`;
    if (statusReport.rows.length === 0) {
      table.innerHTML = "";
      emptyEl.classList.remove("pms-hide");
    } else {
      table.innerHTML = `
        <thead><tr><th>Employee</th><th>Cycle</th><th>Status</th><th>Final Score</th><th>Rating</th><th>Locked</th></tr></thead>
        <tbody>${statusReport.rows.map(pmsStatusRow).join("")}</tbody>`;
    }
  } catch (err) {
    table.innerHTML = "";
    errorEl.textContent = err.message || "Could not load the appraisal status report.";
    errorEl.classList.remove("pms-hide");
  }
}

async function pmsInitReports() {
  let user;
  try {
    user = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(user, "reports");

  try {
    const [statusReport, catalog, employees, cycles] = await Promise.all([
      PMS.get("/reports/appraisal-status"),
      PMS.get("/reports/catalog"),
      PMS.get("/employees").catch(() => []),
      PMS.get("/masters/performance-cycles").catch(() => []),
    ]);

    document.getElementById("pms-loading").classList.add("pms-hide");

    // Employee filter - only the employees this caller can already see
    // (the same role-scoped /employees list every other page uses), so
    // this filter narrows visibility further, never widens it.
    const employeeSelect = document.getElementById("pms-filter-employee");
    employeeSelect.innerHTML = `<option value="">All employees in scope</option>` +
      employees.map((e) => `<option value="${e.employee_id}">${e.employee_code} — ${e.full_name}</option>`).join("");

    const cycleSelect = document.getElementById("pms-filter-cycle");
    cycleSelect.innerHTML = `<option value="">All cycles</option>` +
      cycles.map((c) => `<option value="${c.cycle_id}">${c.cycle_name}</option>`).join("");

    const years = [...new Set(cycles.map((c) => c.year).filter((y) => y != null))].sort((a, b) => b - a);
    const yearSelect = document.getElementById("pms-filter-year");
    yearSelect.innerHTML = `<option value="">All years</option>` +
      years.map((y) => `<option value="${y}">${y}</option>`).join("");

    employeeSelect.addEventListener("change", pmsReloadStatusReport);
    cycleSelect.addEventListener("change", pmsReloadStatusReport);
    yearSelect.addEventListener("change", pmsReloadStatusReport);
    document.getElementById("pms-filter-clear").addEventListener("click", () => {
      employeeSelect.value = ""; cycleSelect.value = ""; yearSelect.value = "";
      pmsReloadStatusReport();
    });

    document.getElementById("pms-status-scope").textContent = `Scope: ${statusReport.scope}`;
    const table = document.getElementById("pms-status-table");
    if (statusReport.rows.length === 0) {
      table.innerHTML = "";
      document.getElementById("pms-status-empty").classList.remove("pms-hide");
    } else {
      table.innerHTML = `
        <thead><tr><th>Employee</th><th>Cycle</th><th>Status</th><th>Final Score</th><th>Rating</th><th>Locked</th></tr></thead>
        <tbody>${statusReport.rows.map(pmsStatusRow).join("")}</tbody>`;
    }
    pmsUpdateDownloadLinks();

    document.getElementById("pms-catalog-list").innerHTML = catalog.map(pmsCatalogRow).join("");

    document.getElementById("pms-body").classList.remove("pms-hide");
  } catch (err) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-error").textContent = err.message || "Could not load reports.";
    document.getElementById("pms-error").classList.remove("pms-hide");
  }
}

pmsInitReports();
