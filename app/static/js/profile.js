/* My Profile: self-service page every account can reach (the user's
   request: "add my profile page for all accounts where he or she can
   update his own profile details along with they can add his or her own
   pic"). Backed by GET/PUT /employees/me (contact info only - see
   EmployeeSelfUpdate's docstring in app/schemas/employee.py for why
   structural fields like department/designation/hierarchy are excluded)
   and POST/DELETE /employees/{id}/photo. HR/Plant Head editing someone
   else's full profile already happens on the Employees page - this page
   is deliberately just "me". */

let pmsUser = null;
let pmsProfile = null;

function pmsField(label, value) {
  return `<div><div class="pms-label">${label}</div><div style="font-size:13px;color:var(--pms-text-soft);margin-top:2px;">${value || "—"}</div></div>`;
}

function pmsRenderProfile() {
  const p = pmsProfile;
  const bodyEl = document.getElementById("pms-body");
  bodyEl.innerHTML = `
    <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start;">
      <div style="display:flex;flex-direction:column;align-items:center;gap:10px;">
        ${pmsAvatarHtml(p.photo_url, p.full_name, "pms-avatar-lg")}
        <input type="file" id="pms-photo-input" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none;" onchange="pmsUploadPhoto()">
        <button class="pms-btn-ghost" onclick="document.getElementById('pms-photo-input').click()">${p.photo_url ? "Change Photo" : "Add Photo"}</button>
        ${p.photo_url ? `<button class="pms-btn-ghost" onclick="pmsRemovePhoto()">Remove Photo</button>` : ""}
      </div>

      <div style="flex:1;min-width:280px;">
        <div style="font-size:17px;font-weight:700;">${p.full_name}</div>
        <div style="font-size:12.5px;color:var(--pms-text-faint);margin-top:2px;">${p.employee_code} &middot; ${p.designation_name || "—"}</div>

        <div class="pms-form-grid" style="margin-top:18px;">
          ${pmsField("Department", p.department_name)}
          ${pmsField("Section", p.section_name)}
          ${pmsField("Plant", p.plant_name)}
          ${pmsField("Grade", p.grade_name)}
          ${pmsField("Date of Joining", p.date_of_joining)}
          ${pmsField("Employment Status", p.employment_status)}
          ${pmsField("Manager", p.manager_name)}
          ${pmsField("HOD", p.hod_name)}
          ${pmsField("HR Contact", p.hr_name)}
        </div>

        <div style="margin-top:18px;">
          <label class="pms-label">Email</label>
          <input class="pms-field" type="text" id="pms-email" value="${p.email || ""}" style="max-width:360px;">
        </div>
        <div class="pms-form-actions">
          <button class="pms-btn-primary" onclick="pmsSaveEmail()">Save Email</button>
        </div>
        <div class="pms-inline-note" style="margin-top:10px;">Department, designation, grade and reporting hierarchy are set by HR or your Plant Head — see them on your Employees record, or ask them to update it.</div>
      </div>
    </div>`;
}

async function pmsSaveEmail() {
  const email = document.getElementById("pms-email").value.trim();
  try {
    pmsProfile = await PMS.put("/employees/me", { email: email || null });
    pmsRenderProfile();
  } catch (err) {
    alert(err.message || "Could not save your email.");
  }
}

async function pmsUploadPhoto() {
  const input = document.getElementById("pms-photo-input");
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`/employees/${pmsProfile.employee_id}/photo`, {
      method: "POST", credentials: "same-origin", body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not upload photo.");
    pmsProfile = data;
    pmsRenderProfile();
    // Topbar avatar reflects the change immediately too.
    pmsUser.photo_url = data.photo_url;
    pmsRenderShell(pmsUser, "profile");
  } catch (err) {
    alert(err.message || "Could not upload photo.");
  }
}

async function pmsRemovePhoto() {
  try {
    const res = await fetch(`/employees/${pmsProfile.employee_id}/photo`, { method: "DELETE", credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not remove photo.");
    pmsProfile = data;
    pmsRenderProfile();
    pmsUser.photo_url = data.photo_url;
    pmsRenderShell(pmsUser, "profile");
  } catch (err) {
    alert(err.message || "Could not remove photo.");
  }
}

async function pmsInitProfile() {
  try {
    pmsUser = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(pmsUser, "profile");

  try {
    pmsProfile = await PMS.get("/employees/me");
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-body").classList.remove("pms-hide");
    pmsRenderProfile();
  } catch (err) {
    document.getElementById("pms-loading").classList.add("pms-hide");
    document.getElementById("pms-error").textContent = err.message || "Could not load your profile.";
    document.getElementById("pms-error").classList.remove("pms-hide");
  }
}

pmsInitProfile();
