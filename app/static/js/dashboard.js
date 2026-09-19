/* Dashboard: role-adaptive. SYS_ADMIN gets system health; everyone else
   gets /dashboard/summary, which itself scopes the numbers (org-wide vs
   personal) based on the caller's role and permissions - this page just
   renders whatever comes back and never re-derives scope client-side. */

const PMS_RATING_COLORS = {
  0: "#35d68f", 1: "#6fa8f5", 2: "#8577f5", 3: "#eab155", 4: "#f0596b",
};

function pmsBarColorForIndex(i) {
  const palette = ["#35d68f", "#6fa8f5", "#8577f5", "#eab155", "#f0596b"];
  return palette[i % palette.length];
}

function pmsStatCard(label, value, sub) {
  return `
    <div class="pms-card">
      <div class="pms-stat-label">${label}</div>
      <div class="pms-stat-value">${value}</div>
      ${sub ? `<div style="font-size:12px;color:var(--pms-text-muted);margin-top:6px;">${sub}</div>` : ""}
    </div>`;
}

function pmsRenderBreakdown(container, dict, colorFn) {
  const entries = Object.entries(dict || {});
  if (entries.length === 0) {
    container.innerHTML = `<div class="pms-empty">No data yet for this scope.</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v), 1);
  container.innerHTML = entries.map(([key, value], i) => `
    <div style="margin-bottom:13px;">
      <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:6px;">
        <span style="color:var(--pms-text-soft);">${key.replace(/_/g, " ")}</span>
        <span style="color:var(--pms-text-faint);">${value}</span>
      </div>
      <div class="pms-bar-track"><div class="pms-bar-fill" style="width:${(value / max) * 100}%;background:${colorFn(i)};"></div></div>
    </div>`).join("");
}

async function pmsInitDashboard() {
  const loadingEl = document.getElementById("pms-loading");
  const errorEl = document.getElementById("pms-error");
  const bodyEl = document.getElementById("pms-body");

  let user;
  try {
    user = await PMS.me();
  } catch (e) {
    return; // api.js already redirected to login.html on 401
  }
  pmsRenderShell(user, "dashboard");

  const isSysAdmin = user.role_codes.includes("SYS_ADMIN") && !user.role_codes.some((r) => r !== "SYS_ADMIN");

  try {
    if (isSysAdmin) {
      const health = await PMS.get("/dashboard/system-health");
      document.getElementById("pms-header-title").textContent = "System Health";
      document.getElementById("pms-header-sub").textContent =
        `${health.active_users} active users · ${health.active_employees} active employees`;

      document.getElementById("pms-stat-grid").innerHTML =
        pmsStatCard("ACTIVE EMPLOYEES", health.active_employees) +
        pmsStatCard("ACTIVE USERS", health.active_users) +
        pmsStatCard("AUDIT LOG ENTRIES", health.total_audit_log_entries,
          health.most_recent_audit_at ? `Last entry ${new Date(health.most_recent_audit_at).toLocaleString()}` : "No entries yet") +
        pmsStatCard("NOTIFICATIONS SENT", health.total_notifications_sent);

      pmsRenderBreakdown(document.getElementById("pms-status-list"), health.appraisals_by_status, pmsBarColorForIndex);
      document.getElementById("pms-rating-section").classList.add("pms-hide");
    } else {
      const summary = await PMS.get("/dashboard/summary");
      const scopeLabel = summary.scope === "organization" || summary.scope === "org" ? "Organization-wide" : "Your scope";
      document.getElementById("pms-header-title").textContent = "Overview";
      document.getElementById("pms-header-sub").textContent = `${scopeLabel} · ${summary.total_appraisals} appraisal(s) in view`;

      document.getElementById("pms-stat-grid").innerHTML =
        pmsStatCard("TOTAL APPRAISALS", summary.total_appraisals) +
        pmsStatCard("PENDING MY ACTION", summary.pending_my_action_count,
          summary.pending_my_action_count > 0 ? "Needs your review" : "Nothing waiting on you") +
        pmsStatCard("AVERAGE FINAL SCORE", summary.average_final_score_pct != null ? summary.average_final_score_pct.toFixed(1) + "%" : "—") +
        pmsStatCard("OVERDUE", summary.overdue_count, summary.overdue_count > 0 ? "Past due date" : "None overdue");

      pmsRenderBreakdown(document.getElementById("pms-status-list"), summary.status_breakdown, pmsBarColorForIndex);
      pmsRenderBreakdown(document.getElementById("pms-rating-list"), summary.rating_distribution, (i) => PMS_RATING_COLORS[i] || "#8577f5");

      if (["EMPLOYEE", "MANAGER", "HOD"].some((r) => user.role_codes.includes(r)) &&
          !["HR", "HR_ADMIN", "PLANT_HEAD", "MD"].some((r) => user.role_codes.includes(r))) {
        document.getElementById("pms-header-sub").innerHTML +=
          ` &middot; See your own appraisal detail under <a href="my-performance.html">My Performance</a>.`;
      }
    }

    // Recent audit activity - visible to roles with AUDIT_LOG.VIEW; hidden
    // gracefully (not an error) for anyone who gets a 403 here.
    try {
      const entries = await PMS.get("/audit-log");
      const list = Array.isArray(entries) ? entries.slice(0, 8) : [];
      if (list.length > 0) {
        document.getElementById("pms-audit-section").classList.remove("pms-hide");
        document.getElementById("pms-audit-list").innerHTML = list.map((e) => `
          <div class="pms-status-row">
            <span style="color:var(--pms-text-soft);">${e.action} &middot; ${e.module}</span>
            <span style="color:var(--pms-text-faint);">${new Date(e.actioned_at).toLocaleString()}</span>
          </div>`).join("");
      }
    } catch (auditErr) {
      // 403 or any other failure here just means this widget stays hidden.
    }

    loadingEl.classList.add("pms-hide");
    bodyEl.classList.remove("pms-hide");
  } catch (err) {
    loadingEl.classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load the dashboard.";
    errorEl.classList.remove("pms-hide");
  }
}

pmsInitDashboard();
