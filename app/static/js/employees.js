/* Employees admin page: create/edit employee records (HR & Plant Head
   per the user's request - EMPLOYEE_MASTER.EDIT already grants this to
   HR/Plant Head/MD/HR Admin), map each employee's hierarchy (Manager,
   HOD, HR contact - Plant Head/MD are not per-employee columns; access
   for those roles is role + plant/org-wide, not a mapped field), and set
   up first-login credentials for a newly created employee by chaining
   POST /admin/users (create the AD-username<->employee<->role mapping)
   then POST /auth/demo/set-password/{user_id} (set the initial
   password) - both endpoints are gated the same way as this page
   (USER_MANAGEMENT_EDIT - see roles.js), so anyone who can reach this
   "Set up login" action already holds the rights the two calls need. */

const PMS_ALL_ROLES = [
  { code: "EMPLOYEE", label: "Employee" },
  { code: "MANAGER", label: "Reporting Manager" },
  { code: "HOD", label: "Head of Department" },
  { code: "HR", label: "HR" },
  { code: "PLANT_HEAD", label: "Plant Head" },
  { code: "MD", label: "Managing Director" },
  { code: "HR_ADMIN", label: "HR Administrator" },
  { code: "SYS_ADMIN", label: "System Administrator" },
];

let pmsUser = null;
let pmsEmployees = [];
let pmsCatalogs = { plant: [], department: [], section: [], designation: [], grade: [], employee_category: [] };
let pmsShowCreate = false;
let pmsEditingId = null;
let pmsLoginSetupId = null;
let pmsFilters = { search: "", plant_id: "", department_id: "", active_only: "true" };

function pmsOpt(rows, idKey, labelKey, current) {
  return rows.map((r) => `<option value="${r[idKey]}" ${current === r[idKey] ? "selected" : ""}>${r[labelKey]}</option>`).join("");
}

function pmsEmployeeOptions(current, excludeId) {
  const rows = pmsEmployees.filter((e) => e.is_active !== false && e.employee_id !== excludeId);
  let options = `<option value="">— None —</option>`;
  options += rows.map((e) => `<option value="${e.employee_id}" ${current === e.employee_id ? "selected" : ""}>${e.full_name} (${e.employee_code})</option>`).join("");
  return options;
}

function pmsEmployeeForm(record, idPrefix) {
  const r = record || {};
  return `
    <div class="pms-form-grid">
      <div><label class="pms-label">Employee Code</label><input class="pms-field" type="text" id="${idPrefix}-code" value="${r.employee_code || ""}" ${record ? "disabled" : ""}></div>
      <div><label class="pms-label">AD / Login Username</label><input class="pms-field" type="text" id="${idPrefix}-ad" value="${r.ad_username || ""}" placeholder="COMPANY\\jdoe" ${record ? "disabled" : ""}></div>
      <div><label class="pms-label">Full Name</label><input class="pms-field" type="text" id="${idPrefix}-name" value="${r.full_name || ""}"></div>
      <div><label class="pms-label">Email</label><input class="pms-field" type="text" id="${idPrefix}-email" value="${r.email || ""}"></div>
      <div><label class="pms-label">Plant</label><select class="pms-field" id="${idPrefix}-plant" onchange="pmsRenderHierarchySelects('${idPrefix}')"><option value="">— None —</option>${pmsOpt(pmsCatalogs.plant, "plant_id", "plant_name", r.plant_id)}</select></div>
      <div><label class="pms-label">Department</label><select class="pms-field" id="${idPrefix}-dept"><option value="">— None —</option>${pmsOpt(pmsCatalogs.department, "department_id", "dept_name", r.department_id)}</select></div>
      <div><label class="pms-label">Section</label><select class="pms-field" id="${idPrefix}-section"><option value="">— None —</option>${pmsOpt(pmsCatalogs.section, "section_id", "section_name", r.section_id)}</select></div>
      <div><label class="pms-label">Designation</label><select class="pms-field" id="${idPrefix}-designation"><option value="">— None —</option>${pmsOpt(pmsCatalogs.designation, "designation_id", "designation_name", r.designation_id)}</select></div>
      <div><label class="pms-label">Grade</label><select class="pms-field" id="${idPrefix}-grade"><option value="">— None —</option>${pmsOpt(pmsCatalogs.grade, "grade_id", "grade_name", r.grade_id)}</select></div>
      <div><label class="pms-label">Employee Category</label><select class="pms-field" id="${idPrefix}-category"><option value="">— None —</option>${pmsOpt(pmsCatalogs.employee_category, "employee_category_id", "category_name", r.employee_category_id)}</select></div>
      <div><label class="pms-label">Date of Joining</label><input class="pms-field" type="date" id="${idPrefix}-doj" value="${r.date_of_joining || ""}"></div>
      <div><label class="pms-label">Employment Status</label><select class="pms-field" id="${idPrefix}-empstatus">
        ${["ACTIVE", "ON_LEAVE", "INACTIVE"].map((s) => `<option value="${s}" ${r.employment_status === s ? "selected" : ""}>${s}</option>`).join("")}
      </select></div>
      <div id="${idPrefix}-hierarchy-wrap" style="grid-column:1/-1;display:contents;"></div>
      ${record ? `<div style="grid-column:1/-1;"><label class="pms-label">Reason for change (required)</label><textarea class="pms-field" id="${idPrefix}-reason"></textarea></div>` : ""}
    </div>`;
}

// Hierarchy selects (Manager / HOD / HR) are rendered separately and
// re-rendered whenever the Plant select changes, so the three dropdowns
// default to showing people in the same plant first - a plant can (and
// per the user's clarified requirement, does) have several different
// people holding Manager/HOD, so this is a convenience filter, not a
// hard constraint: switching plant never wipes an already-picked value.
function pmsRenderHierarchySelects(idPrefix, record) {
  const wrap = document.getElementById(`${idPrefix}-hierarchy-wrap`);
  if (!wrap) return;
  const r = record || {};
  const plantSel = document.getElementById(`${idPrefix}-plant`);
  const plantId = plantSel ? (plantSel.value ? parseInt(plantSel.value, 10) : null) : r.plant_id;
  const inPlant = (e) => plantId == null || e.plant_id === plantId;
  const pool = pmsEmployees.filter((e) => e.is_active !== false && e.employee_id !== r.employee_id);
  const scoped = pool.filter(inPlant);
  const rows = scoped.length > 0 ? scoped : pool;

  const buildSelect = (fieldId, label, currentId) => `
    <div>
      <label class="pms-label">${label}</label>
      <select class="pms-field" id="${fieldId}">
        <option value="">— None —</option>
        ${rows.map((e) => `<option value="${e.employee_id}" ${currentId === e.employee_id ? "selected" : ""}>${e.full_name} (${e.employee_code})</option>`).join("")}
        ${currentId != null && !rows.some((e) => e.employee_id === currentId) ? (() => {
          const cur = pmsEmployees.find((e) => e.employee_id === currentId);
          return cur ? `<option value="${cur.employee_id}" selected>${cur.full_name} (${cur.employee_code})</option>` : "";
        })() : ""}
      </select>
    </div>`;

  wrap.innerHTML =
    buildSelect(`${idPrefix}-manager`, "Manager", r.manager_id) +
    buildSelect(`${idPrefix}-hod`, "HOD", r.hod_id) +
    buildSelect(`${idPrefix}-hr`, "HR Contact", r.hr_id);
}

function pmsReadEmployeeForm(idPrefix) {
  const val = (id) => document.getElementById(id).value;
  const intOrNull = (id) => (val(id) ? parseInt(val(id), 10) : null);
  return {
    full_name: val(`${idPrefix}-name`),
    email: val(`${idPrefix}-email`) || null,
    plant_id: intOrNull(`${idPrefix}-plant`),
    department_id: intOrNull(`${idPrefix}-dept`),
    section_id: intOrNull(`${idPrefix}-section`),
    designation_id: intOrNull(`${idPrefix}-designation`),
    grade_id: intOrNull(`${idPrefix}-grade`),
    employee_category_id: intOrNull(`${idPrefix}-category`),
    date_of_joining: val(`${idPrefix}-doj`) || null,
    employment_status: val(`${idPrefix}-empstatus`),
    manager_id: intOrNull(`${idPrefix}-manager`),
    hod_id: intOrNull(`${idPrefix}-hod`),
    hr_id: intOrNull(`${idPrefix}-hr`),
  };
}

async function pmsCreateEmployee() {
  const idPrefix = "create";
  const code = document.getElementById(`${idPrefix}-code`).value.trim();
  const ad = document.getElementById(`${idPrefix}-ad`).value.trim();
  if (!code || !ad) { alert("Employee Code and AD/Login Username are required."); return; }
  const payload = { employee_code: code, ad_username: ad, ...pmsReadEmployeeForm(idPrefix) };
  if (!payload.full_name) { alert("Full Name is required."); return; }
  try {
    const created = await PMS.post("/employees", payload);
    pmsShowCreate = false;
    await pmsReload();
    pmsLoginSetupId = created.employee_id;
    await pmsRenderList();
    alert(`Employee "${created.full_name}" created. Use "Set up login" below to create their username/password.`);
  } catch (err) {
    alert(err.message || "Could not create this employee.");
  }
}

async function pmsUpdateEmployee(id) {
  const idPrefix = `edit-${id}`;
  const reason = document.getElementById(`${idPrefix}-reason`).value.trim();
  if (!reason) { alert("A reason for this change is required."); return; }
  const payload = { ...pmsReadEmployeeForm(idPrefix), reason };
  try {
    await PMS.put(`/employees/${id}`, payload);
    pmsEditingId = null;
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not save changes.");
  }
}

async function pmsUploadEmployeePhoto(employeeId) {
  const input = document.getElementById(`edit-${employeeId}-photo-input`);
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`/employees/${employeeId}/photo`, { method: "POST", credentials: "same-origin", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not upload photo.");
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not upload photo.");
  }
}

async function pmsRemoveEmployeePhoto(employeeId) {
  try {
    const res = await fetch(`/employees/${employeeId}/photo`, { method: "DELETE", credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not remove photo.");
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not remove photo.");
  }
}

async function pmsDeactivateEmployee(id) {
  const reason = window.prompt("Reason for deactivating this employee:");
  if (reason === null) return;
  if (!reason.trim()) { alert("A reason is required."); return; }
  try {
    await PMS.post(`/employees/${id}/deactivate`, { reason: reason.trim() });
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not deactivate this employee.");
  }
}

/* ---------- First-login setup (HR / Plant Head only, USER_MANAGEMENT_EDIT) ---------- */

function pmsLoginSetupForm(employee) {
  const idPrefix = `login-${employee.employee_id}`;
  const roleBoxes = PMS_ALL_ROLES.map((r) => `
    <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:500;">
      <input type="checkbox" id="${idPrefix}-role-${r.code}" ${r.code === "EMPLOYEE" ? "checked" : ""}> ${r.label}
    </label>`).join("");
  return `
    <div class="pms-form-grid" style="margin-top:10px;">
      <div style="grid-column:1/-1;font-size:12.5px;color:var(--pms-text-muted);">
        Sets up ${employee.full_name}'s username/password login (username defaults to their AD/Login Username, ${employee.ad_username}). Pick every role they should hold - e.g. tick Plant Head or Managing Director here to promote them.
      </div>
      <div style="grid-column:1/-1;display:flex;flex-wrap:wrap;gap:14px;">${roleBoxes}</div>
      <div><label class="pms-label">Initial Password</label><input class="pms-field" type="text" id="${idPrefix}-password" placeholder="Shared with the employee to log in the first time"></div>
    </div>
    <div class="pms-form-actions">
      <button class="pms-btn-primary" onclick="pmsSubmitLoginSetup(${employee.employee_id})">Create Login</button>
      <button class="pms-btn-ghost" onclick="pmsCancelLoginSetup()">Cancel</button>
    </div>`;
}

async function pmsSubmitLoginSetup(employeeId) {
  const employee = pmsEmployees.find((e) => e.employee_id === employeeId);
  const idPrefix = `login-${employeeId}`;
  const roleCodes = PMS_ALL_ROLES.filter((r) => document.getElementById(`${idPrefix}-role-${r.code}`).checked).map((r) => r.code);
  const password = document.getElementById(`${idPrefix}-password`).value;
  if (roleCodes.length === 0) { alert("Pick at least one role."); return; }
  if (!password || password.length < 4) { alert("Enter an initial password (at least 4 characters)."); return; }
  try {
    const user = await PMS.post("/admin/users", {
      ad_username: employee.ad_username, employee_id: employeeId, role_codes: roleCodes, is_active: true,
    });
    await PMS.post(`/auth/demo/set-password/${user.user_id}`, { new_password: password });
    pmsLoginSetupId = null;
    await pmsRenderList();
    alert(`Login created for ${employee.full_name}. Share the username (${employee.ad_username}) and initial password with them.`);
  } catch (err) {
    alert(err.message || "Could not set up this login. If a login already exists for this AD username, use the Users & Roles page to reset the password instead.");
  }
}

function pmsCancelLoginSetup() {
  pmsLoginSetupId = null;
  pmsRenderList();
}

function pmsToggleLoginSetup(id) {
  pmsLoginSetupId = pmsLoginSetupId === id ? null : id;
  pmsEditingId = null;
  pmsRenderList();
}

/* ---------- list rendering ---------- */

function pmsToggleCreate() {
  pmsShowCreate = !pmsShowCreate;
  pmsEditingId = null;
  pmsRenderList();
  if (pmsShowCreate) setTimeout(() => pmsRenderHierarchySelects("create"), 0);
}

function pmsToggleEdit(id) {
  pmsEditingId = pmsEditingId === id ? null : id;
  pmsShowCreate = false;
  pmsLoginSetupId = null;
  pmsRenderList();
  if (pmsEditingId === id) {
    const record = pmsEmployees.find((e) => e.employee_id === id);
    setTimeout(() => pmsRenderHierarchySelects(`edit-${id}`, record), 0);
  }
}

function pmsRenderEmployeeCard(e) {
  const editable = pmsHasCap(pmsUser.role_codes, "EMPLOYEE_MASTER_EDIT");
  const canDeactivate = pmsHasCap(pmsUser.role_codes, "EMPLOYEE_MASTER_DEACTIVATE");
  const canManageLogin = pmsHasCap(pmsUser.role_codes, "USER_MANAGEMENT_EDIT");
  const editing = pmsEditingId === e.employee_id;
  const settingUpLogin = pmsLoginSetupId === e.employee_id;
  const isActive = e.is_active !== false;

  const subtitleParts = [
    e.employee_code, e.designation_name, e.department_name, e.plant_name,
  ].filter(Boolean).join(" · ");
  const hierarchyParts = [
    e.manager_name ? `Manager: ${e.manager_name}` : null,
    e.hod_name ? `HOD: ${e.hod_name}` : null,
    e.hr_name ? `HR: ${e.hr_name}` : null,
  ].filter(Boolean).join(" &middot; ");

  return `
    <div class="pms-list-item" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:12px;">
          ${pmsAvatarHtml(e.photo_url, e.full_name)}
          <div>
            <div style="font-weight:600;font-size:13.5px;">${e.full_name}</div>
            <div style="font-size:12px;color:var(--pms-text-faint);margin-top:3px;">${subtitleParts}</div>
            ${hierarchyParts ? `<div style="font-size:11.5px;color:var(--pms-text-faint);margin-top:2px;">${hierarchyParts}</div>` : ""}
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="pms-pill ${isActive ? "pms-pill-mint" : "pms-pill-neutral"}">${isActive ? "Active" : "Inactive"}</span>
          ${canManageLogin ? `<button class="pms-btn-ghost" onclick="pmsToggleLoginSetup(${e.employee_id})">${settingUpLogin ? "Close" : "Set up login"}</button>` : ""}
          ${editable ? `<button class="pms-btn-ghost" onclick="pmsToggleEdit(${e.employee_id})">${editing ? "Close" : "Edit"}</button>` : ""}
          ${canDeactivate && isActive ? `<button class="pms-btn-ghost" onclick="pmsDeactivateEmployee(${e.employee_id})">Deactivate</button>` : ""}
        </div>
      </div>
      ${editing ? `<div>
        <div style="display:flex;align-items:center;gap:12px;margin:10px 0;">
          ${pmsAvatarHtml(e.photo_url, e.full_name)}
          <input type="file" id="edit-${e.employee_id}-photo-input" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none;" onchange="pmsUploadEmployeePhoto(${e.employee_id})">
          <button class="pms-btn-ghost" onclick="document.getElementById('edit-${e.employee_id}-photo-input').click()">${e.photo_url ? "Change Photo" : "Add Photo"}</button>
          ${e.photo_url ? `<button class="pms-btn-ghost" onclick="pmsRemoveEmployeePhoto(${e.employee_id})">Remove Photo</button>` : ""}
        </div>
        ${pmsEmployeeForm(e, `edit-${e.employee_id}`)}<div class="pms-form-actions"><button class="pms-btn-primary" onclick="pmsUpdateEmployee(${e.employee_id})">Save Changes</button><button class="pms-btn-ghost" onclick="pmsToggleEdit(${e.employee_id})">Cancel</button></div></div>` : ""}
      ${settingUpLogin ? pmsLoginSetupForm(e) : ""}
    </div>`;
}

async function pmsRenderList() {
  const listEl = document.getElementById("pms-list");
  const emptyEl = document.getElementById("pms-empty");
  const editable = pmsHasCap(pmsUser.role_codes, "EMPLOYEE_MASTER_EDIT");

  document.getElementById("pms-create-btn-wrap").innerHTML = editable
    ? `<button class="pms-btn-primary" onclick="pmsToggleCreate()">${pmsShowCreate ? "Close" : "+ Add New Employee"}</button>`
    : "";
  document.getElementById("pms-create-form-wrap").innerHTML = (editable && pmsShowCreate)
    ? `${pmsEmployeeForm(null, "create")}<div class="pms-form-actions"><button class="pms-btn-primary" onclick="pmsCreateEmployee()">Create Employee</button><button class="pms-btn-ghost" onclick="pmsToggleCreate()">Cancel</button></div>`
    : "";

  if (pmsEmployees.length === 0) {
    listEl.classList.add("pms-hide");
    emptyEl.classList.remove("pms-hide");
    return;
  }
  emptyEl.classList.add("pms-hide");
  listEl.innerHTML = pmsEmployees.map(pmsRenderEmployeeCard).join("");
  listEl.classList.remove("pms-hide");
}

function pmsApplyFilters() {
  pmsFilters.search = document.getElementById("pms-f-search").value.trim();
  pmsFilters.plant_id = document.getElementById("pms-f-plant").value;
  pmsFilters.department_id = document.getElementById("pms-f-department").value;
  pmsFilters.active_only = document.getElementById("pms-f-active").value;
  pmsReload();
}

function pmsClearFilters() {
  document.getElementById("pms-f-search").value = "";
  document.getElementById("pms-f-plant").value = "";
  document.getElementById("pms-f-department").value = "";
  document.getElementById("pms-f-active").value = "true";
  pmsFilters = { search: "", plant_id: "", department_id: "", active_only: "true" };
  pmsReload();
}

function pmsBuildQuery() {
  const params = new URLSearchParams();
  if (pmsFilters.search) params.set("search", pmsFilters.search);
  if (pmsFilters.plant_id) params.set("plant_id", pmsFilters.plant_id);
  if (pmsFilters.department_id) params.set("department_id", pmsFilters.department_id);
  if (pmsFilters.active_only) params.set("active_only", pmsFilters.active_only);
  const qs = params.toString();
  return qs ? `/employees?${qs}` : "/employees";
}

async function pmsReload() {
  const errorEl = document.getElementById("pms-error");
  errorEl.classList.add("pms-hide");
  try {
    pmsEmployees = await PMS.get(pmsBuildQuery());
    await pmsRenderList();
  } catch (err) {
    document.getElementById("pms-list").classList.add("pms-hide");
    document.getElementById("pms-empty").classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load employees.";
    errorEl.classList.remove("pms-hide");
  }
}

async function pmsPreloadCatalogs() {
  const [plants, departments, sections, designations, grades, categories] = await Promise.all([
    PMS.get("/masters/plants").catch(() => []),
    PMS.get("/masters/departments").catch(() => []),
    PMS.get("/masters/sections").catch(() => []),
    PMS.get("/masters/designations").catch(() => []),
    PMS.get("/masters/grades").catch(() => []),
    PMS.get("/masters/employee-categories").catch(() => []),
  ]);
  pmsCatalogs = { plant: plants, department: departments, section: sections, designation: designations, grade: grades, employee_category: categories };

  const plantSel = document.getElementById("pms-f-plant");
  plantSel.innerHTML += pmsOpt(plants, "plant_id", "plant_name");
  const deptSel = document.getElementById("pms-f-department");
  deptSel.innerHTML += pmsOpt(departments, "department_id", "dept_name");
}

async function pmsInitEmployees() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "employees");

  if (!pmsHasCap(pmsUser.role_codes, "EMPLOYEE_MASTER_VIEW")) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-no-access").classList.remove("pms-hide");
    return;
  }

  await pmsPreloadCatalogs();
  await pmsReload();
  document.getElementById("pms-loading").classList.add("pms-hide");
  document.getElementById("pms-body").classList.remove("pms-hide");
}

pmsInitEmployees();
