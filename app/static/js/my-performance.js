/* My Performance: renders exactly what GET /performance-history/me
   returns - a list of records, each with a score breakdown and a
   transitions timeline. No fields are invented beyond that response. */

function pmsRatingPillClass(label) {
  if (!label) return "pms-pill-neutral";
  const l = label.toLowerCase();
  if (l.includes("exceed") || l.includes("outstanding")) return "pms-pill-mint";
  if (l.includes("meet") || l.includes("good")) return "pms-pill-blue";
  if (l.includes("improve") || l.includes("below")) return "pms-pill-amber";
  if (l.includes("pip") || l.includes("unsatisfactory") || l.includes("poor")) return "pms-pill-red";
  return "pms-pill-purple";
}

function pmsStatusPillClass(status) {
  if (!status) return "pms-pill-neutral";
  const s = status.toUpperCase();
  if (s.includes("APPROVED") || s.includes("COMPLETE")) return "pms-pill-mint";
  if (s.includes("REJECT") || s.includes("PIP")) return "pms-pill-red";
  if (s.includes("DRAFT")) return "pms-pill-neutral";
  return "pms-pill-amber";
}

function pmsRecordCard(record) {
  const scoreBoxes = (record.score_breakdown || []).map((s) => `
    <div class="pms-score-box">
      <div class="pms-score-box-label">${s.score_type.replace(/_/g, " ").toUpperCase()}</div>
      <div class="pms-score-box-value">${s.score_value}</div>
    </div>`).join("");

  const transitions = (record.transitions || []).map((t, i, arr) => `
    <div class="pms-transition-item">
      <div class="pms-transition-dotcol">
        <div class="pms-timeline-dot" style="background:${i === 0 ? "#35d68f" : "#3a4258"};"></div>
        ${i < arr.length - 1 ? '<div class="pms-timeline-line"></div>' : ""}
      </div>
      <div style="padding-bottom:2px;">
        <div style="font-size:12.5px;color:var(--pms-text-soft);font-weight:600;">
          ${t.from_status ? t.from_status.replace(/_/g, " ") + " &rarr; " : ""}${(t.to_status || "").replace(/_/g, " ")}
        </div>
        <div style="font-size:11.5px;color:var(--pms-text-faint);margin-top:2px;">${new Date(t.actioned_at).toLocaleString()}</div>
        ${t.comments ? `<div style="font-size:12px;color:var(--pms-text-muted);margin-top:4px;">${t.comments}</div>` : ""}
      </div>
    </div>`).join("") || `<div class="pms-empty">No transitions recorded yet.</div>`;

  return `
    <div class="pms-card pms-record-card">
      <div class="pms-record-head">
        <div>
          <div class="pms-record-title">${record.cycle_name}</div>
          <div style="font-size:11.5px;color:var(--pms-text-faint);margin-top:3px;">Performance ID #${record.performance_id}${record.is_locked ? " &middot; Locked" : ""}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span class="pms-pill ${pmsStatusPillClass(record.status)}">${record.status.replace(/_/g, " ")}</span>
          ${record.final_rating_label ? `<span class="pms-pill ${pmsRatingPillClass(record.final_rating_label)}">${record.final_rating_label}</span>` : ""}
        </div>
      </div>

      ${record.final_score_pct != null ? `
        <div style="font-size:12px;color:var(--pms-text-muted);margin-bottom:6px;">Final score</div>
        <div style="font-family:'Manrope',sans-serif;font-size:26px;font-weight:700;margin-bottom:10px;">${record.final_score_pct.toFixed(1)}%</div>
      ` : ""}

      ${scoreBoxes ? `<div class="pms-score-row">${scoreBoxes}</div>` : ""}

      <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--pms-border-soft);">
        <div style="font-size:12px;font-weight:700;color:var(--pms-text-label);letter-spacing:.03em;margin-bottom:12px;">WORKFLOW HISTORY</div>
        ${transitions}
      </div>
    </div>`;
}

async function pmsInitMyPerformance() {
  const loadingEl = document.getElementById("pms-loading");
  const errorEl = document.getElementById("pms-error");
  const emptyEl = document.getElementById("pms-empty");
  const recordsEl = document.getElementById("pms-records");

  let user;
  try {
    user = await PMS.me();
  } catch (e) {
    return;
  }
  pmsRenderShell(user, "my-performance");

  try {
    const history = await PMS.get("/performance-history/me");
    loadingEl.classList.add("pms-hide");
    const records = history.records || [];
    if (records.length === 0) {
      emptyEl.classList.remove("pms-hide");
      return;
    }
    recordsEl.innerHTML = records.map(pmsRecordCard).join("");
    recordsEl.classList.remove("pms-hide");
  } catch (err) {
    loadingEl.classList.add("pms-hide");
    errorEl.textContent = err.message || "Could not load your performance history.";
    errorEl.classList.remove("pms-hide");
  }
}

pmsInitMyPerformance();
