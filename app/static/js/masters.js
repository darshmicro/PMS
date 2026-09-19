/* Masters administration: one page covering every master-data type in
   the app (Company, Plant, Department, Section, Designation, Grade,
   Employee Category, KPA, KPI, Scoring Rules, Ratings, Competency,
   Performance Cycles). The backend already gates all of these behind a
   single shared MASTERS.EDIT / MASTERS.DEACTIVATE permission pair
   (granted to HR, Plant Head, MD, HR Admin - see sql/005) - this page is
   simply the UI that was missing for using that right.

   Two real inconsistencies in the underlying API are handled explicitly
   here rather than papered over:
   1. Org masters' Update payload has NO reason field (reason only shows
      up on the separate activate/deactivate calls, as a JSON body
      {reason}); KPA/KPI/Scoring Rule/Rating/Competency/Performance Cycle
      Update payloads all require reason directly on the update body, and
      their activate/deactivate calls take reason as a bare query
      parameter instead of a JSON body.
   2. Scoring Rules, Ratings and Performance Cycles have NO activate
      route at all (deactivate-only) - reactivating one of those means
      creating a fresh record with an HR/Plant Head-authored reason,
      which the UI states plainly rather than showing a dead button. */

const MEASUREMENT_TYPES = ["NUMERIC", "PERCENTAGE", "RATIO", "YESNO", "DATE", "MILESTONE", "QTY", "COST", "REDUCTION", "QUALITATIVE"];
const TARGET_TYPES = ["HIGHER_IS_BETTER", "LOWER_IS_BETTER"];

function pmsOptText(cfg, record) {
  const code = cfg.codeField ? record[cfg.codeField] : null;
  const label = record[cfg.labelField];
  return code ? `${code} — ${label}` : label;
}

function pmsLookup(refKey, id) {
  if (id === null || id === undefined) return null;
  const cfg = MASTERS_CONFIG.find((c) => c.key === refKey);
  const rows = pmsCache[refKey] || [];
  const row = rows.find((r) => r[cfg.idField] === id);
  return row ? pmsOptText(cfg, row) : `#${id}`;
}

const MASTERS_CONFIG = [
  {
    key: "company", label: "Company", listPath: "/masters/companies", createPath: "/masters/companies",
    idField: "company_id", codeField: "company_code", labelField: "company_name",
    updatePath: (id) => `/masters/companies/${id}`,
    deactivatePath: (id) => `/masters/companies/${id}/deactivate`, activatePath: (id) => `/masters/companies/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "company_code", label: "Company Code", type: "text", required: true },
      { name: "company_name", label: "Company Name", type: "text", required: true },
    ],
    editFields: [{ name: "company_name", label: "Company Name", type: "text", required: true }],
    subtitle: () => "",
  },
  {
    key: "plant", label: "Plant", listPath: "/masters/plants", createPath: "/masters/plants",
    idField: "plant_id", codeField: "plant_code", labelField: "plant_name",
    updatePath: (id) => `/masters/plants/${id}`,
    deactivatePath: (id) => `/masters/plants/${id}/deactivate`, activatePath: (id) => `/masters/plants/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "plant_code", label: "Plant Code", type: "text", required: true },
      { name: "plant_name", label: "Plant Name", type: "text", required: true },
      { name: "company_id", label: "Company", type: "select", refKey: "company", required: true },
    ],
    editFields: [
      { name: "plant_name", label: "Plant Name", type: "text", required: true },
      { name: "company_id", label: "Company", type: "select", refKey: "company", required: true },
    ],
    subtitle: (r) => `Company: ${pmsLookup("company", r.company_id) || "—"}`,
  },
  {
    key: "department", label: "Department", listPath: "/masters/departments", createPath: "/masters/departments",
    idField: "department_id", codeField: "dept_code", labelField: "dept_name",
    updatePath: (id) => `/masters/departments/${id}`,
    deactivatePath: (id) => `/masters/departments/${id}/deactivate`, activatePath: (id) => `/masters/departments/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "dept_code", label: "Dept Code", type: "text", required: true },
      { name: "dept_name", label: "Dept Name", type: "text", required: true },
      { name: "plant_id", label: "Plant", type: "select", refKey: "plant", required: true },
    ],
    editFields: [
      { name: "dept_name", label: "Dept Name", type: "text", required: true },
      { name: "plant_id", label: "Plant", type: "select", refKey: "plant", required: true },
    ],
    subtitle: (r) => `Plant: ${pmsLookup("plant", r.plant_id) || "—"}`,
  },
  {
    key: "section", label: "Section", listPath: "/masters/sections", createPath: "/masters/sections",
    idField: "section_id", codeField: "section_code", labelField: "section_name",
    updatePath: (id) => `/masters/sections/${id}`,
    deactivatePath: (id) => `/masters/sections/${id}/deactivate`, activatePath: (id) => `/masters/sections/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "section_code", label: "Section Code", type: "text", required: true },
      { name: "section_name", label: "Section Name", type: "text", required: true },
      { name: "department_id", label: "Department", type: "select", refKey: "department", required: true },
    ],
    editFields: [
      { name: "section_name", label: "Section Name", type: "text", required: true },
      { name: "department_id", label: "Department", type: "select", refKey: "department", required: true },
    ],
    subtitle: (r) => `Department: ${pmsLookup("department", r.department_id) || "—"}`,
  },
  {
    key: "designation", label: "Designation", listPath: "/masters/designations", createPath: "/masters/designations",
    idField: "designation_id", codeField: "designation_code", labelField: "designation_name",
    updatePath: (id) => `/masters/designations/${id}`,
    deactivatePath: (id) => `/masters/designations/${id}/deactivate`, activatePath: (id) => `/masters/designations/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "designation_code", label: "Designation Code", type: "text", required: true },
      { name: "designation_name", label: "Designation Name", type: "text", required: true },
    ],
    editFields: [{ name: "designation_name", label: "Designation Name", type: "text", required: true }],
    subtitle: () => "",
  },
  {
    key: "grade", label: "Grade", listPath: "/masters/grades", createPath: "/masters/grades",
    idField: "grade_id", codeField: "grade_code", labelField: "grade_name",
    updatePath: (id) => `/masters/grades/${id}`,
    deactivatePath: (id) => `/masters/grades/${id}/deactivate`, activatePath: (id) => `/masters/grades/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "grade_code", label: "Grade Code", type: "text", required: true },
      { name: "grade_name", label: "Grade Name", type: "text", required: true },
    ],
    editFields: [{ name: "grade_name", label: "Grade Name", type: "text", required: true }],
    subtitle: () => "",
  },
  {
    key: "employee_category", label: "Employee Category", listPath: "/masters/employee-categories", createPath: "/masters/employee-categories",
    idField: "employee_category_id", codeField: "category_code", labelField: "category_name",
    updatePath: (id) => `/masters/employee-categories/${id}`,
    deactivatePath: (id) => `/masters/employee-categories/${id}/deactivate`, activatePath: (id) => `/masters/employee-categories/${id}/activate`,
    hasActivate: true, updateReasonInBody: false, statusReasonMode: "body",
    createFields: [
      { name: "category_code", label: "Category Code", type: "text", required: true },
      { name: "category_name", label: "Category Name", type: "text", required: true },
    ],
    editFields: [{ name: "category_name", label: "Category Name", type: "text", required: true }],
    subtitle: () => "",
  },
  {
    key: "kpa", label: "KPA", listPath: "/masters/kpa", createPath: "/masters/kpa",
    idField: "kpa_id", codeField: "kpa_code", labelField: "kpa_name",
    updatePath: (id) => `/masters/kpa/${id}`,
    deactivatePath: (id) => `/masters/kpa/${id}/deactivate`, activatePath: (id) => `/masters/kpa/${id}/activate`,
    hasActivate: true, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "kpa_code", label: "KPA Code", type: "text", required: true },
      { name: "kpa_name", label: "KPA Name", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea" },
      { name: "department_id", label: "Department (optional)", type: "select", refKey: "department", allowEmpty: true },
      { name: "designation_id", label: "Designation (optional)", type: "select", refKey: "designation", allowEmpty: true },
      { name: "category", label: "Category", type: "text" },
      { name: "default_weightage", label: "Default Weightage (%)", type: "number" },
      { name: "effective_from", label: "Effective From", type: "date" },
      { name: "effective_to", label: "Effective To", type: "date" },
    ],
    editFields: [
      { name: "kpa_name", label: "KPA Name", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea" },
      { name: "department_id", label: "Department (optional)", type: "select", refKey: "department", allowEmpty: true },
      { name: "designation_id", label: "Designation (optional)", type: "select", refKey: "designation", allowEmpty: true },
      { name: "category", label: "Category", type: "text" },
      { name: "default_weightage", label: "Default Weightage (%)", type: "number" },
      { name: "effective_from", label: "Effective From", type: "date" },
      { name: "effective_to", label: "Effective To", type: "date" },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    subtitle: (r) => `${r.department_name ? "Dept: " + r.department_name + " · " : ""}${r.category || ""}`,
  },
  {
    key: "kpi", label: "KPI", listPath: "/masters/kpi", createPath: "/masters/kpi",
    idField: "kpi_id", codeField: "kpi_code", labelField: "kpi_name",
    updatePath: (id) => `/masters/kpi/${id}`,
    deactivatePath: (id) => `/masters/kpi/${id}/deactivate`, activatePath: (id) => `/masters/kpi/${id}/activate`,
    hasActivate: true, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "kpi_code", label: "KPI Code", type: "text", required: true },
      { name: "kpi_name", label: "KPI Name", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea" },
      { name: "kpa_id", label: "KPA", type: "select", refKey: "kpa", required: true },
      { name: "department_id", label: "Department (optional)", type: "select", refKey: "department", allowEmpty: true },
      { name: "designation_id", label: "Designation (optional)", type: "select", refKey: "designation", allowEmpty: true },
      { name: "measurement_type", label: "Measurement Type", type: "select", staticOptions: MEASUREMENT_TYPES, required: true },
      { name: "unit", label: "Unit", type: "text" },
      { name: "target_type", label: "Target Type", type: "select", staticOptions: TARGET_TYPES, allowEmpty: true },
      { name: "default_target", label: "Default Target", type: "number" },
      { name: "minimum_target", label: "Minimum Target", type: "number" },
      { name: "expected_target", label: "Expected Target", type: "number" },
      { name: "stretch_target", label: "Stretch Target", type: "number" },
      { name: "weightage", label: "Weightage (%)", type: "number" },
      { name: "scoring_method", label: "Scoring Method", type: "text" },
    ],
    editFields: [
      { name: "kpi_name", label: "KPI Name", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea" },
      { name: "kpa_id", label: "KPA", type: "select", refKey: "kpa", required: true },
      { name: "department_id", label: "Department (optional)", type: "select", refKey: "department", allowEmpty: true },
      { name: "designation_id", label: "Designation (optional)", type: "select", refKey: "designation", allowEmpty: true },
      { name: "measurement_type", label: "Measurement Type", type: "select", staticOptions: MEASUREMENT_TYPES, required: true },
      { name: "unit", label: "Unit", type: "text" },
      { name: "target_type", label: "Target Type", type: "select", staticOptions: TARGET_TYPES, allowEmpty: true },
      { name: "default_target", label: "Default Target", type: "number" },
      { name: "minimum_target", label: "Minimum Target", type: "number" },
      { name: "expected_target", label: "Expected Target", type: "number" },
      { name: "stretch_target", label: "Stretch Target", type: "number" },
      { name: "weightage", label: "Weightage (%)", type: "number" },
      { name: "scoring_method", label: "Scoring Method", type: "text" },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    subtitle: (r) => `KPA: ${r.kpa_name || "—"} · ${r.measurement_type}${r.weightage != null ? " · Weightage: " + r.weightage + "%" : ""}`,
  },
  {
    key: "scoring_rule", label: "Scoring Rules", listPath: "/masters/scoring-rules", createPath: "/masters/scoring-rules",
    idField: "rule_id", codeField: null, labelField: null,
    updatePath: (id) => `/masters/scoring-rules/${id}`,
    deactivatePath: (id) => `/masters/scoring-rules/${id}/deactivate`, activatePath: null,
    hasActivate: false, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "kpi_id", label: "KPI (leave blank for the global default rule set)", type: "select", refKey: "kpi", allowEmpty: true },
      { name: "min_achievement", label: "Min Achievement (%)", type: "number", required: true },
      { name: "max_achievement", label: "Max Achievement (%)", type: "number", required: true },
      { name: "score", label: "Score (1-5)", type: "number", required: true },
    ],
    editFields: [
      { name: "min_achievement", label: "Min Achievement (%)", type: "number", required: true },
      { name: "max_achievement", label: "Max Achievement (%)", type: "number", required: true },
      { name: "score", label: "Score (1-5)", type: "number", required: true },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    itemTitle: (r) => `${r.kpi_name ? r.kpi_name : "Global default"} — ${r.min_achievement}% to ${r.max_achievement}% → Score ${r.score}`,
    subtitle: () => "",
  },
  {
    key: "rating", label: "Ratings", listPath: "/masters/ratings", createPath: "/masters/ratings",
    idField: "rating_id", codeField: null, labelField: "rating_label",
    updatePath: (id) => `/masters/ratings/${id}`,
    deactivatePath: (id) => `/masters/ratings/${id}/deactivate`, activatePath: null,
    hasActivate: false, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "rating_label", label: "Rating Label", type: "text", required: true },
      { name: "min_percent", label: "Min %", type: "number", required: true },
      { name: "max_percent", label: "Max %", type: "number", required: true },
    ],
    editFields: [
      { name: "rating_label", label: "Rating Label", type: "text", required: true },
      { name: "min_percent", label: "Min %", type: "number", required: true },
      { name: "max_percent", label: "Max %", type: "number", required: true },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    itemTitle: (r) => `${r.rating_label} (${r.min_percent}% – ${r.max_percent}%)`,
    subtitle: () => "",
  },
  {
    key: "competency", label: "Competency", listPath: "/masters/competencies", createPath: "/masters/competencies",
    idField: "competency_id", codeField: "competency_code", labelField: "competency_name",
    updatePath: (id) => `/masters/competencies/${id}`,
    deactivatePath: (id) => `/masters/competencies/${id}/deactivate`, activatePath: (id) => `/masters/competencies/${id}/activate`,
    hasActivate: true, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "competency_code", label: "Competency Code", type: "text", required: true },
      { name: "competency_name", label: "Competency Name", type: "text", required: true },
      { name: "category", label: "Category", type: "text" },
      { name: "weightage", label: "Weightage (%)", type: "number" },
    ],
    editFields: [
      { name: "competency_name", label: "Competency Name", type: "text", required: true },
      { name: "category", label: "Category", type: "text" },
      { name: "weightage", label: "Weightage (%)", type: "number" },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    subtitle: (r) => `${r.category || ""}${r.weightage != null ? " · Weightage: " + r.weightage + "%" : ""}`,
  },
  {
    key: "performance_cycle", label: "Performance Cycles", listPath: "/masters/performance-cycles", createPath: "/masters/performance-cycles",
    idField: "cycle_id", codeField: null, labelField: "cycle_name",
    updatePath: (id) => `/masters/performance-cycles/${id}`,
    deactivatePath: (id) => `/masters/performance-cycles/${id}/deactivate`, activatePath: null,
    hasActivate: false, updateReasonInBody: true, statusReasonMode: "query",
    createFields: [
      { name: "cycle_name", label: "Cycle Name", type: "text", required: true },
      { name: "year", label: "Year (used by report search)", type: "number" },
      { name: "kpi_setting_start", label: "KPI Setting Start", type: "date" },
      { name: "kpi_setting_end", label: "KPI Setting End", type: "date" },
      { name: "self_assessment_start", label: "Self-Assessment Start", type: "date" },
      { name: "self_assessment_end", label: "Self-Assessment End", type: "date" },
      { name: "manager_review_start", label: "Manager Review Start", type: "date" },
      { name: "manager_review_end", label: "Manager Review End", type: "date" },
      { name: "hod_review_start", label: "HOD Review Start", type: "date" },
      { name: "hod_review_end", label: "HOD Review End", type: "date" },
      { name: "hr_review_start", label: "HR Review Start", type: "date" },
      { name: "hr_review_end", label: "HR Review End", type: "date" },
      { name: "plant_head_approval_start", label: "Plant Head Approval Start", type: "date" },
      { name: "plant_head_approval_end", label: "Plant Head Approval End", type: "date" },
      { name: "md_approval_start", label: "MD Approval Start", type: "date" },
      { name: "md_approval_end", label: "MD Approval End", type: "date" },
    ],
    editFields: [
      { name: "year", label: "Year (used by report search)", type: "number" },
      { name: "kpi_setting_start", label: "KPI Setting Start", type: "date" },
      { name: "kpi_setting_end", label: "KPI Setting End", type: "date" },
      { name: "self_assessment_start", label: "Self-Assessment Start", type: "date" },
      { name: "self_assessment_end", label: "Self-Assessment End", type: "date" },
      { name: "manager_review_start", label: "Manager Review Start", type: "date" },
      { name: "manager_review_end", label: "Manager Review End", type: "date" },
      { name: "hod_review_start", label: "HOD Review Start", type: "date" },
      { name: "hod_review_end", label: "HOD Review End", type: "date" },
      { name: "hr_review_start", label: "HR Review Start", type: "date" },
      { name: "hr_review_end", label: "HR Review End", type: "date" },
      { name: "plant_head_approval_start", label: "Plant Head Approval Start", type: "date" },
      { name: "plant_head_approval_end", label: "Plant Head Approval End", type: "date" },
      { name: "md_approval_start", label: "MD Approval Start", type: "date" },
      { name: "md_approval_end", label: "MD Approval End", type: "date" },
      { name: "reason", label: "Reason for change (required)", type: "textarea", required: true },
    ],
    subtitle: (r) => `${r.year ? "Year: " + r.year + " · " : ""}KPI Setting: ${r.kpi_setting_start || "—"} to ${r.kpi_setting_end || "—"}`,
  },
];

let pmsUser = null;
let pmsCache = {};
let pmsActiveKey = "company";
let pmsShowCreate = false;
let pmsEditingId = null;

function pmsCfg(key) {
  return MASTERS_CONFIG.find((c) => c.key === key);
}

function pmsFieldValue(field, record) {
  const v = record[field.name];
  if (field.type === "date") return v || "";
  if (v === null || v === undefined) return "";
  return v;
}

function pmsFieldInput(field, idPrefix, record) {
  const elId = `${idPrefix}-${field.name}`;
  const value = record ? pmsFieldValue(field, record) : "";
  if (field.type === "textarea") {
    return `<div><label class="pms-label">${field.label}</label><textarea class="pms-field" id="${elId}">${value}</textarea></div>`;
  }
  if (field.type === "select") {
    let options = "";
    if (field.allowEmpty) options += `<option value="">— None —</option>`;
    if (field.staticOptions) {
      options += field.staticOptions.map((o) => `<option value="${o}" ${String(value) === o ? "selected" : ""}>${o}</option>`).join("");
    } else if (field.refKey) {
      const refCfg = pmsCfg(field.refKey);
      const rows = (pmsCache[field.refKey] || []).filter((r) => r.is_active !== false || r[refCfg.idField] === value);
      options += rows.map((r) => `<option value="${r[refCfg.idField]}" ${value === r[refCfg.idField] ? "selected" : ""}>${pmsOptText(refCfg, r)}</option>`).join("");
    }
    return `<div><label class="pms-label">${field.label}</label><select class="pms-field" id="${elId}">${options}</select></div>`;
  }
  const type = field.type === "number" ? "number" : field.type === "date" ? "date" : "text";
  return `<div><label class="pms-label">${field.label}</label><input class="pms-field" type="${type}" id="${elId}" value="${value}"></div>`;
}

function pmsReadField(field, idPrefix) {
  const el = document.getElementById(`${idPrefix}-${field.name}`);
  if (!el) return undefined;
  const raw = el.value;
  if (raw === "") return field.required ? "" : null;
  if (field.type === "number") return parseFloat(raw);
  if (field.type === "select" && field.refKey) return parseInt(raw, 10);
  return raw;
}

function pmsBuildPayload(cfg, fields, idPrefix) {
  const payload = {};
  for (const field of fields) {
    const value = pmsReadField(field, idPrefix);
    if (field.required && (value === "" || value === null || value === undefined)) {
      alert(`${field.label} is required.`);
      return null;
    }
    payload[field.name] = value;
  }
  return payload;
}

function pmsRenderForm(cfg, fields, idPrefix, record, onSubmit, submitLabel) {
  return `
    <div class="pms-form-grid">${fields.map((f) => pmsFieldInput(f, idPrefix, record)).join("")}</div>
    <div class="pms-form-actions">
      <button class="pms-btn-primary" onclick="${onSubmit}">${submitLabel}</button>
      <button class="pms-btn-ghost" onclick="pmsCancelForm('${cfg.key}')">Cancel</button>
    </div>`;
}

function pmsCancelForm(key) {
  pmsShowCreate = false;
  pmsEditingId = null;
  pmsRenderActiveTab();
}

function pmsToggleCreate() {
  pmsShowCreate = !pmsShowCreate;
  pmsEditingId = null;
  pmsRenderActiveTab();
}

function pmsToggleEdit(id) {
  pmsEditingId = pmsEditingId === id ? null : id;
  pmsShowCreate = false;
  pmsRenderActiveTab();
}

async function pmsCreateRecord() {
  const cfg = pmsCfg(pmsActiveKey);
  const payload = pmsBuildPayload(cfg, cfg.createFields, "create");
  if (payload === null) return;
  try {
    await PMS.post(cfg.createPath, payload);
    pmsShowCreate = false;
    await pmsReloadAndRender(cfg.key);
  } catch (err) {
    alert(err.message || "Could not create this record.");
  }
}

async function pmsUpdateRecord(id) {
  const cfg = pmsCfg(pmsActiveKey);
  const idPrefix = `edit-${id}`;
  const payload = pmsBuildPayload(cfg, cfg.editFields, idPrefix);
  if (payload === null) return;
  try {
    await PMS.put(cfg.updatePath(id), payload);
    pmsEditingId = null;
    await pmsReloadAndRender(cfg.key);
  } catch (err) {
    alert(err.message || "Could not save changes.");
  }
}

async function pmsSetActive(id, makeActive) {
  const cfg = pmsCfg(pmsActiveKey);
  const reason = window.prompt(`Reason to ${makeActive ? "reactivate" : "deactivate"} this record:`);
  if (reason === null) return;
  if (!reason.trim()) { alert("A reason is required."); return; }
  try {
    if (cfg.statusReasonMode === "body") {
      const path = makeActive ? cfg.activatePath(id) : cfg.deactivatePath(id);
      await PMS.post(path, { reason: reason.trim() });
    } else {
      const path = makeActive ? cfg.activatePath(id) : cfg.deactivatePath(id);
      await PMS.post(`${path}?reason=${encodeURIComponent(reason.trim())}`);
    }
    await pmsReloadAndRender(cfg.key);
  } catch (err) {
    alert(err.message || "Could not change status.");
  }
}

async function pmsReloadAndRender(key) {
  const cfg = pmsCfg(key);
  try {
    pmsCache[key] = await PMS.get(cfg.listPath);
  } catch (err) {
    // fall through - render will show whatever is cached, error surfaces via the list fetch below
  }
  await pmsRenderActiveTab();
}

function pmsItemTitle(cfg, record) {
  if (cfg.itemTitle) return cfg.itemTitle(record);
  const code = cfg.codeField ? record[cfg.codeField] : null;
  const name = cfg.labelField ? record[cfg.labelField] : `#${record[cfg.idField]}`;
  return code ? `${code} — ${name}` : name;
}

function pmsRenderItem(cfg, record) {
  const id = record[cfg.idField];
  const editable = pmsHasCap(pmsUser.role_codes, "MASTERS_EDIT");
  const canDeactivate = pmsHasCap(pmsUser.role_codes, "MASTERS_DEACTIVATE");
  const editing = pmsEditingId === id;
  const isActive = record.is_active !== false;
  const subtitle = cfg.subtitle ? cfg.subtitle(record) : "";
  let statusActions = "";
  if (canDeactivate) {
    if (isActive) {
      statusActions = `<button class="pms-btn-ghost" onclick="pmsSetActive(${id}, false)">Deactivate</button>`;
    } else if (cfg.hasActivate) {
      statusActions = `<button class="pms-btn-ghost" onclick="pmsSetActive(${id}, true)">Reactivate</button>`;
    } else {
      statusActions = `<span class="pms-inline-note" style="margin-top:0;">No reactivate option here — create a new record instead.</span>`;
    }
  }
  return `
    <div class="pms-list-item" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;">
        <div>
          <div style="font-weight:600;font-size:13.5px;">${pmsItemTitle(cfg, record)}</div>
          ${subtitle ? `<div style="font-size:12px;color:var(--pms-text-faint);margin-top:3px;">${subtitle}</div>` : ""}
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="pms-pill ${isActive ? "pms-pill-mint" : "pms-pill-neutral"}">${isActive ? "Active" : "Inactive"}</span>
          ${editable ? `<button class="pms-btn-ghost" onclick="pmsToggleEdit(${id})">${editing ? "Close" : "Edit"}</button>` : ""}
          ${statusActions}
        </div>
      </div>
      ${editing ? (cfg.key === "company" ? pmsCompanyLogoControl(record) : "") : ""}
      ${editing ? pmsRenderForm(cfg, cfg.editFields, `edit-${id}`, record, `pmsUpdateRecord(${id})`, "Save Changes") : ""}
    </div>`;
}

// Company logo upload ("provision to add company logo by HR or plant
// head" - gated the same way as every other company edit here, by
// MASTERS_EDIT, which roles.js already maps to HR/Plant Head/MD/HR
// Admin). Kept as its own small control rather than folding "logo" into
// MASTERS_CONFIG's generic text-field-driven form, since a file upload
// doesn't fit that config shape.
function pmsCompanyLogoControl(record) {
  const id = record.company_id;
  return `
    <div style="display:flex;align-items:center;gap:12px;margin:10px 0;">
      ${record.logo_url ? `<img src="${record.logo_url}" alt="${record.company_name} logo" style="height:40px;max-width:140px;object-fit:contain;border-radius:6px;background:#fff;padding:4px;">` : `<div class="pms-inline-note" style="margin-top:0;">No logo uploaded yet.</div>`}
      <input type="file" id="company-logo-input-${id}" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none;" onchange="pmsUploadCompanyLogo(${id})">
      <button class="pms-btn-ghost" onclick="document.getElementById('company-logo-input-${id}').click()">${record.logo_url ? "Change Logo" : "Add Logo"}</button>
      ${record.logo_url ? `<button class="pms-btn-ghost" onclick="pmsRemoveCompanyLogo(${id})">Remove Logo</button>` : ""}
    </div>`;
}

async function pmsUploadCompanyLogo(companyId) {
  const input = document.getElementById(`company-logo-input-${companyId}`);
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`/masters/companies/${companyId}/logo`, { method: "POST", credentials: "same-origin", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not upload logo.");
    await pmsReloadAndRender("company");
  } catch (err) {
    alert(err.message || "Could not upload logo.");
  }
}

async function pmsRemoveCompanyLogo(companyId) {
  try {
    const res = await fetch(`/masters/companies/${companyId}/logo`, { method: "DELETE", credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not remove logo.");
    await pmsReloadAndRender("company");
  } catch (err) {
    alert(err.message || "Could not remove logo.");
  }
}

async function pmsRenderActiveTab() {
  const cfg = pmsCfg(pmsActiveKey);
  const editable = pmsHasCap(pmsUser.role_codes, "MASTERS_EDIT");
  document.getElementById("pms-header-sub").textContent = editable
    ? `Add, edit and (de)activate ${cfg.label} records.`
    : `View-only — you don't hold edit rights for master data.`;

  const listEl = document.getElementById("pms-list");
  const emptyEl = document.getElementById("pms-empty");
  const errorEl = document.getElementById("pms-error");
  const createBtnWrap = document.getElementById("pms-create-btn-wrap");
  const createFormWrap = document.getElementById("pms-create-form-wrap");
  errorEl.classList.add("pms-hide");

  createBtnWrap.innerHTML = editable
    ? `<button class="pms-btn-primary" onclick="pmsToggleCreate()">${pmsShowCreate ? "Close" : "+ Add New " + cfg.label}</button>`
    : "";
  createFormWrap.innerHTML = (editable && pmsShowCreate)
    ? pmsRenderForm(cfg, cfg.createFields, "create", null, "pmsCreateRecord()", `Create ${cfg.label}`)
    : "";

  try {
    if (!pmsCache[cfg.key]) {
      pmsCache[cfg.key] = await PMS.get(cfg.listPath);
    }
    const rows = pmsCache[cfg.key] || [];
    if (rows.length === 0) {
      listEl.classList.add("pms-hide");
      emptyEl.classList.remove("pms-hide");
      return;
    }
    emptyEl.classList.add("pms-hide");
    listEl.innerHTML = rows.map((r) => pmsRenderItem(cfg, r)).join("");
    listEl.classList.remove("pms-hide");
  } catch (err) {
    listEl.classList.add("pms-hide");
    emptyEl.classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load this master list.";
    errorEl.classList.remove("pms-hide");
  }
}

function pmsRenderTabs() {
  const tabsEl = document.getElementById("pms-tabs");
  tabsEl.innerHTML = MASTERS_CONFIG.map((c) =>
    `<button class="pms-chip ${c.key === pmsActiveKey ? "active" : ""}" onclick="pmsSwitchTab('${c.key}')">${c.label}</button>`
  ).join("");
}

async function pmsSwitchTab(key) {
  pmsActiveKey = key;
  pmsShowCreate = false;
  pmsEditingId = null;
  pmsRenderTabs();
  await pmsRenderActiveTab();
}

async function pmsPreloadCatalogs() {
  // Loaded up front so cross-entity selects (Plant's Company, KPI's KPA,
  // etc.) and lookup labels are ready before any tab is drawn - avoids a
  // waterfall of fetches every time the person switches tabs.
  const refKeys = ["company", "plant", "department", "designation", "kpa", "kpi"];
  await Promise.all(refKeys.map(async (key) => {
    try {
      pmsCache[key] = await PMS.get(pmsCfg(key).listPath);
    } catch (e) {
      pmsCache[key] = [];
    }
  }));
}

async function pmsInitMasters() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "masters");

  if (!pmsHasCap(pmsUser.role_codes, "MASTERS_VIEW")) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-no-access").classList.remove("pms-hide");
    return;
  }

  await pmsPreloadCatalogs();
  document.getElementById("pms-loading").classList.add("pms-hide");
  document.getElementById("pms-body").classList.remove("pms-hide");
  pmsRenderTabs();
  await pmsRenderActiveTab();
}

pmsInitMasters();
