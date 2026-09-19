/* Users & Roles admin: the "AD Username <-> Employee <-> Role" screen
   (spec Section 5), backed by /admin/users (app/api/routes/users.py).
   Originally HR Administrator/System Administrator only; widened at the
   user's request so HR and Plant Head can also manage this - including
   reassigning someone to PLANT_HEAD or MD - which is why USER_MANAGEMENT_
   VIEW/EDIT in roles.js now includes HR/PLANT_HEAD too (must mirror
   ADMIN_ROLES in users.py exactly, or a button would show here that 403s
   on the server). */

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
let pmsUsers = [];
let pmsEmployees = [];
let pmsShowCreate = false;
let pmsEditingId = null;
let pmsResettingId = null;

function pmsRoleCheckboxes(idPrefix, currentCodes) {
  const codes = currentCodes || [];
  return PMS_ALL_ROLES.map((r) => `
    <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:500;">
      <input type="checkbox" id="${idPrefix}-role-${r.code}" ${codes.includes(r.code) ? "checked" : ""}> ${r.label}
    </label>`).join("");
}

function pmsReadRoleCodes(idPrefix) {
  return PMS_ALL_ROLES.filter((r) => document.getElementById(`${idPrefix}-role-${r.code}`).checked).map((r) => r.code);
}

function pmsEmployeeSelectOptions(current) {
  let options = `<option value="">— No linked employee —</option>`;
  options += pmsEmployees.map((e) =>
    `<option value="${e.employee_id}" ${current === e.employee_id ? "selected" : ""}>${e.full_name} (${e.employee_code})</option>`
  ).join("");
  return options;
}

function pmsCreateForm() {
  return `
    <div class="pms-form-grid">
      <div><label class="pms-label">AD / Login Username</label><input class="pms-field" type="text" id="create-ad" placeholder="COMPANY\\jdoe"></div>
      <div><label class="pms-label">Linked Employee</label><select class="pms-field" id="create-employee">${pmsEmployeeSelectOptions(null)}</select></div>
      <div style="grid-column:1/-1;"><label class="pms-label">Roles</label><div style="display:flex;flex-wrap:wrap;gap:14px;">${pmsRoleCheckboxes("create", ["EMPLOYEE"])}</div></div>
      <div><label class="pms-label">Initial Password</label><input class="pms-field" type="text" id="create-password" placeholder="Shared with the user to log in the first time"></div>
    </div>
    <div class="pms-form-actions">
      <button class="pms-btn-primary" onclick="pmsCreateUser()">Create User</button>
      <button class="pms-btn-ghost" onclick="pmsToggleCreate()">Cancel</button>
    </div>`;
}

async function pmsCreateUser() {
  const ad = document.getElementById("create-ad").value.trim();
  const employeeId = document.getElementById("create-employee").value;
  const roleCodes = pmsReadRoleCodes("create");
  const password = document.getElementById("create-password").value;
  if (!ad) { alert("AD/Login Username is required."); return; }
  if (roleCodes.length === 0) { alert("Pick at least one role."); return; }
  try {
    const user = await PMS.post("/admin/users", {
      ad_username: ad, employee_id: employeeId ? parseInt(employeeId, 10) : null, role_codes: roleCodes, is_active: true,
    });
    if (password && password.trim()) {
      await PMS.post(`/auth/demo/set-password/${user.user_id}`, { new_password: password.trim() });
    }
    pmsShowCreate = false;
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not create this user.");
  }
}

function pmsEditForm(user) {
  const idPrefix = `edit-${user.user_id}`;
  return `
    <div class="pms-form-grid" style="margin-top:10px;">
      <div><label class="pms-label">Linked Employee</label><select class="pms-field" id="${idPrefix}-employee">${pmsEmployeeSelectOptions(user.employee_id)}</select></div>
      <div><label class="pms-label">Active</label><select class="pms-field" id="${idPrefix}-active">
        <option value="true" ${user.is_active ? "selected" : ""}>Active</option>
        <option value="false" ${!user.is_active ? "selected" : ""}>Inactive</option>
      </select></div>
      <div style="grid-column:1/-1;"><label class="pms-label">Roles</label><div style="display:flex;flex-wrap:wrap;gap:14px;">${pmsRoleCheckboxes(idPrefix, user.role_codes)}</div></div>
      <div style="grid-column:1/-1;"><label class="pms-label">Reason for change (required)</label><textarea class="pms-field" id="${idPrefix}-reason"></textarea></div>
    </div>
    <div class="pms-form-actions">
      <button class="pms-btn-primary" onclick="pmsSaveUser(${user.user_id})">Save Changes</button>
      <button class="pms-btn-ghost" onclick="pmsToggleEdit(${user.user_id})">Cancel</button>
    </div>`;
}

async function pmsSaveUser(userId) {
  const idPrefix = `edit-${userId}`;
  const employeeVal = document.getElementById(`${idPrefix}-employee`).value;
  const active = document.getElementById(`${idPrefix}-active`).value === "true";
  const roleCodes = pmsReadRoleCodes(idPrefix);
  const reason = document.getElementById(`${idPrefix}-reason`).value.trim();
  if (roleCodes.length === 0) { alert("Pick at least one role."); return; }
  if (!reason) { alert("A reason for this change is required."); return; }
  try {
    await PMS.put(`/admin/users/${userId}`, {
      employee_id: employeeVal ? parseInt(employeeVal, 10) : null,
      role_codes: roleCodes,
      is_active: active,
      reason,
    });
    pmsEditingId = null;
    await pmsReload();
  } catch (err) {
    alert(err.message || "Could not save changes.");
  }
}

function pmsResetForm(user) {
  const idPrefix = `reset-${user.user_id}`;
  return `
    <div class="pms-form-grid" style="margin-top:10px;">
      <div><label class="pms-label">New Password</label><input class="pms-field" type="text" id="${idPrefix}-password" placeholder="Share this with ${user.ad_username}"></div>
    </div>
    <div class="pms-form-actions">
      <button class="pms-btn-primary" onclick="pmsSubmitReset(${user.user_id})">Set Password</button>
      <button class="pms-btn-ghost" onclick="pmsToggleReset(${user.user_id})">Cancel</button>
    </div>`;
}

async function pmsSubmitReset(userId) {
  const idPrefix = `reset-${userId}`;
  const password = document.getElementById(`${idPrefix}-password`).value;
  if (!password || password.length < 4) { alert("Enter a password (at least 4 characters)."); return; }
  try {
    await PMS.post(`/auth/demo/set-password/${userId}`, { new_password: password });
    pmsResettingId = null;
    await pmsRenderList();
    alert("Password updated.");
  } catch (err) {
    alert(err.message || "Could not reset this password.");
  }
}

function pmsToggleCreate() {
  pmsShowCreate = !pmsShowCreate;
  pmsEditingId = null;
  pmsResettingId = null;
  pmsRenderList();
}

function pmsToggleEdit(id) {
  pmsEditingId = pmsEditingId === id ? null : id;
  pmsShowCreate = false;
  pmsResettingId = null;
  pmsRenderList();
}

function pmsToggleReset(id) {
  pmsResettingId = pmsResettingId === id ? null : id;
  pmsShowCreate = false;
  pmsEditingId = null;
  pmsRenderList();
}

function pmsRolePillClass(code) {
  if (code === "MD" || code === "PLANT_HEAD") return "pms-pill-amber";
  if (code === "SYS_ADMIN" || code === "HR_ADMIN") return "pms-pill-mint";
  return "pms-pill-neutral";
}

function pmsRenderUserCard(u) {
  const editable = pmsHasCap(pmsUser.role_codes, "USER_MANAGEMENT_EDIT");
  const editing = pmsEditingId === u.user_id;
  const resetting = pmsResettingId === u.user_id;
  const roleBadges = (u.role_codes || []).map((c) => `<span class="pms-pill ${pmsRolePillClass(c)}">${c.replace(/_/g, " ")}</span>`).join(" ");

  return `
    <div class="pms-list-item" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:12px;">
          ${pmsAvatarHtml(u.employee_photo_url, u.employee_name || u.ad_username)}
          <div>
            <div style="font-weight:600;font-size:13.5px;">${u.ad_username}</div>
            <div style="font-size:12px;color:var(--pms-text-faint);margin-top:3px;">${u.employee_name || "No linked employee"}</div>
            <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;">${roleBadges}</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="pms-pill ${u.is_active ? "pms-pill-mint" : "pms-pill-neutral"}">${u.is_active ? "Active" : "Inactive"}</span>
          ${editable ? `<button class="pms-btn-ghost" onclick="pmsToggleReset(${u.user_id})">${resetting ? "Close" : "Reset Password"}</button>` : ""}
          ${editable ? `<button class="pms-btn-ghost" onclick="pmsToggleEdit(${u.user_id})">${editing ? "Close" : "Edit Roles"}</button>` : ""}
        </div>
      </div>
      ${editing ? pmsEditForm(u) : ""}
      ${resetting ? pmsResetForm(u) : ""}
    </div>`;
}

async function pmsRenderList() {
  const listEl = document.getElementById("pms-list");
  const emptyEl = document.getElementById("pms-empty");
  const editable = pmsHasCap(pmsUser.role_codes, "USER_MANAGEMENT_EDIT");

  document.getElementById("pms-create-btn-wrap").innerHTML = editable
    ? `<button class="pms-btn-primary" onclick="pmsToggleCreate()">${pmsShowCreate ? "Close" : "+ Add New User"}</button>`
    : "";
  document.getElementById("pms-create-form-wrap").innerHTML = (editable && pmsShowCreate) ? pmsCreateForm() : "";

  if (pmsUsers.length === 0) {
    listEl.classList.add("pms-hide");
    emptyEl.classList.remove("pms-hide");
    return;
  }
  emptyEl.classList.add("pms-hide");
  listEl.innerHTML = pmsUsers.map(pmsRenderUserCard).join("");
  listEl.classList.remove("pms-hide");
}

async function pmsReload() {
  const errorEl = document.getElementById("pms-error");
  errorEl.classList.add("pms-hide");
  try {
    pmsUsers = await PMS.get("/admin/users");
    await pmsRenderList();
  } catch (err) {
    document.getElementById("pms-list").classList.add("pms-hide");
    document.getElementById("pms-empty").classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load users.";
    errorEl.classList.remove("pms-hide");
  }
}

async function pmsInitUsers() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "users");

  if (!pmsHasCap(pmsUser.role_codes, "USER_MANAGEMENT_VIEW")) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-no-access").classList.remove("pms-hide");
    return;
  }

  try {
    pmsEmployees = await PMS.get("/employees");
  } catch (e) {
    pmsEmployees = [];
  }
  await pmsReload();
  document.getElementById("pms-loading").classList.add("pms-hide");
  document.getElementById("pms-body").classList.remove("pms-hide");
}

pmsInitUsers();
