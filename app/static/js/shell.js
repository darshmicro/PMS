/* Renders the shared sidebar + topbar shell. Nav items and their target
   pages mirror the app's real routers - nothing here is decorative; a
   role that lacks a permission simply gets a 403 handled by that page,
   the same way the API itself enforces it. */

const PMS_ICONS = {
  grid: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="3" width="8" height="8" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="8" height="8" rx="2" stroke="currentColor" stroke-width="1.8"/></svg>',
  trend: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 19c4-8 6-12 8-12s4 4 8 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  clipboard: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  bell: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 17H5l1.4-1.4A2 2 0 0 0 7 14.2V11a5 5 0 0 1 10 0v3.2c0 .5.2 1 .6 1.4L19 17h-4Z" stroke="currentColor" stroke-width="1.7"/></svg>',
  shield: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 3 5 6v6c0 4.4 3 8 7 9 4-1 7-4.6 7-9V6l-7-3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  gear: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M19.4 13.5a1.9 1.9 0 0 0 2.1-1.9v-1.2a1.9 1.9 0 0 0-1.9-1.9M4.6 10.5a1.9 1.9 0 0 0-2.1 1.9v1.2a1.9 1.9 0 0 0 1.9 1.9" stroke="currentColor" stroke-width="1.3"/></svg>',
  database: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="6" rx="7" ry="3" stroke="currentColor" stroke-width="1.8"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" stroke="currentColor" stroke-width="1.8"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" stroke="currentColor" stroke-width="1.8"/></svg>',
};

function pmsInitials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
}

// Shared "picture before the name" helper - every screen that shows a
// person's name (topbar, Employees, Users & Roles, Reviews & Approvals
// record cards) renders its avatar through this one function, so a photo
// uploaded via /employees/{id}/photo (see profile.js/employees.js) shows
// up everywhere consistently, falling back to initials when there's no
// photo yet. sizeClass is "" (32px, the default list/topbar size) or
// "pms-avatar-lg" (88px, used on the Profile page).
function pmsAvatarHtml(photoUrl, name, sizeClass) {
  const cls = sizeClass || "";
  if (photoUrl) {
    return `<img class="pms-avatar-img ${cls}" src="${photoUrl}" alt="${name || "Profile photo"}">`;
  }
  return `<div class="pms-avatar ${cls}">${pmsInitials(name)}</div>`;
}

function pmsRoleLabel(roleCodes) {
  const labels = {
    SYS_ADMIN: "System Administrator", HR_ADMIN: "HR Administrator", HR: "HR",
    MD: "Managing Director", PLANT_HEAD: "Plant Head", HOD: "Head of Department",
    MANAGER: "Reporting Manager", EMPLOYEE: "Employee",
  };
  const priority = ["MD", "PLANT_HEAD", "HR_ADMIN", "HR", "HOD", "MANAGER", "EMPLOYEE", "SYS_ADMIN"];
  for (const r of priority) if (roleCodes.includes(r)) return labels[r];
  return roleCodes[0] || "User";
}

function pmsRenderShell(user, activeKey) {
  const navItems = [
    { key: "dashboard", label: "Dashboard", href: "dashboard.html", icon: "grid" },
    { key: "my-performance", label: "My Performance", href: "my-performance.html", icon: "trend" },
    { key: "profile", label: "My Profile", href: "profile.html", icon: "shield" },
  ];

  // Each remaining item mirrors a real permission grant (roles.js) - a
  // role with no reach into that module never sees the nav item at all,
  // matching dependencies.py's "the UI also hides buttons the user can't
  // use" principle. typeof-guarded so a page that hasn't loaded roles.js
  // yet (there should be none, but this keeps the shell from crashing) just
  // shows the two items above instead of throwing.
  if (typeof pmsHasCap === "function" && Array.isArray(user.role_codes)) {
    if (pmsHasAnyCap(user.role_codes, ["ASSIGNMENT_EDIT", "ASSIGNMENT_PROPOSE"])) {
      navItems.push({ key: "assignments", label: "KPA / KPI Assignment", href: "assignments.html", icon: "clipboard" });
    }
    if (pmsHasCap(user.role_codes, "SELF_ASSESSMENT_EDIT")) {
      navItems.push({ key: "self-assessment", label: "Self-Assessment", href: "self-assessment.html", icon: "clipboard" });
    }
    if (pmsHasAnyCap(user.role_codes, [
      "MANAGER_REVIEW_VIEW", "HOD_REVIEW_VIEW", "HR_REVIEW_VIEW", "PLANT_HEAD_APPROVAL_VIEW", "MD_APPROVAL_VIEW",
    ])) {
      navItems.push({ key: "reviews", label: "Reviews & Approvals", href: "reviews.html", icon: "shield" });
    }
    if (pmsHasCap(user.role_codes, "REPORT_VIEW")) {
      navItems.push({ key: "reports", label: "Reports & Exports", href: "reports.html", icon: "gear" });
    }
    if (pmsHasCap(user.role_codes, "EMPLOYEE_MASTER_EDIT")) {
      navItems.push({ key: "employees", label: "Employees", href: "employees.html", icon: "clipboard" });
    }
    if (pmsHasCap(user.role_codes, "USER_MANAGEMENT_VIEW")) {
      navItems.push({ key: "users", label: "Users & Roles", href: "users.html", icon: "shield" });
    }
    if (pmsHasCap(user.role_codes, "MASTERS_EDIT")) {
      navItems.push({ key: "masters", label: "Masters", href: "masters.html", icon: "database" });
    }
  }

  const navHtml = navItems.map((item) => {
    const cls = "pms-navitem" + (item.key === activeKey ? " active" : "");
    return `<a class="${cls}" href="${item.href}">${PMS_ICONS[item.icon]}<span>${item.label}</span></a>`;
  }).join("");

  document.querySelectorAll("[data-pms-sidebar]").forEach((el) => {
    el.innerHTML = `
      <div>
        <div class="pms-brand">
          <div class="pms-brand-mark" ${user.company_logo_url ? 'style="background:#fff;padding:3px;"' : ""}>
            ${user.company_logo_url
              ? `<img src="${user.company_logo_url}" alt="Company logo" style="width:100%;height:100%;object-fit:contain;">`
              : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 19V5a1 1 0 0 1 1-1h8l7 7v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z" stroke="#0a0e15" stroke-width="1.8" stroke-linejoin="round"/></svg>'}
          </div>
          <div>
            <div class="pms-brand-name">Performance MS</div>
            <div class="pms-brand-role">${pmsRoleLabel(user.role_codes).toUpperCase()}</div>
          </div>
        </div>
        <div class="pms-nav-heading">WORKSPACE</div>
        <div style="display:flex;flex-direction:column;gap:2px;">${navHtml}</div>
      </div>
      <div class="pms-sidebar-footer">
        <div style="font-size:11.5px;font-weight:700;color:var(--pms-text-soft);margin-bottom:6px;">Signed in as</div>
        <div style="font-size:12.5px;color:var(--pms-text-muted);margin-bottom:10px;">${user.ad_username}</div>
        <button class="pms-btn-ghost" style="width:100%;justify-content:center;" onclick="PMS.logout().then(()=>location.href='login.html')">Log out</button>
      </div>`;
  });

  document.querySelectorAll("[data-pms-topbar-user]").forEach((el) => {
    el.innerHTML = `
      <a href="profile.html" style="display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit;">
        ${pmsAvatarHtml(user.photo_url, user.employee_name || user.ad_username)}
        <div>
          <div style="font-size:12.5px;font-weight:600;color:var(--pms-text);">${user.employee_name || user.ad_username}</div>
          <div style="font-size:11px;color:var(--pms-text-faint);">${pmsRoleLabel(user.role_codes)}</div>
        </div>
      </a>`;
  });
}
