#!/usr/bin/env python3
"""
DEMO-ONLY. Drives ONE employee's performance appraisal through the entire
M5-M21 workflow via real HTTP calls against a running PMS instance, using
the same REST API a browser would use - so every business rule (weightage
checks, scoring rules, RBAC scoping, audit trail) runs exactly as it would
for a real user. This is not a database script; it exercises the app.

Prerequisites:
  1. uvicorn is running locally with AUTH_MODE=demo_local
     (python -m uvicorn app.main:app --host 127.0.0.1 --port 8000)
  2. You've already run, in order:
       - 000_FULL_DATABASE_SETUP.sql (schema + sample org data incl.
         Company 'SAMPLE-CO1' / Plant 'SAMPLE-PLT1' from sql/004)
       - sql/demo_only/041_create_demo_login_table.sql (or the identical
         top-level sql/041_create_demo_login_table.sql - either works)
       - sql/demo_only/042_bootstrap_first_admin_demo_local.sql (demoadmin)
         - or, instead of that hardcoded-password script, run
           `python scripts/bootstrap_admin.py` and choose local mode
       - sql/demo_only/043_seed_demo_multi_role_users.sql (emp.demo,
         manager.demo, hod.demo, planthead.demo, hr.demo, md.demo)
  3. `pip install requests` if you don't already have it in this venv.

Run:
    python scripts/demo_full_workflow.py
    python scripts/demo_full_workflow.py 2   # pass any tag to create ANOTHER
                                              # appraisal instead of re-using
                                              # the first one (see note below)

It prints each stage as it completes. The KPA/KPI/Cycle/Company/Plant
master-data creates are safe to re-run (skipped if a matching record
already exists, matched by unique code/name). The Assignment step is NOT:
the app enforces one Assignment per (employee, cycle), so running this
script twice with no argument will hit a 409 on the *second* run at the
"Creating assignment" step - that's the app correctly refusing a duplicate,
not a bug. Pass any argument (e.g. "2", "3") to seed a fresh cycle name and
therefore a brand-new appraisal without touching the first one.
"""
import sys

import requests

CYCLE_TAG = sys.argv[1] if len(sys.argv) > 1 else "1"

BASE_URL = "http://127.0.0.1:8000"
PASSWORD = "Demo@12345"

USERS = {
    "hr": "hr.demo",
    "manager": "manager.demo",
    "hod": "hod.demo",
    "employee": "emp.demo",
    "planthead": "planthead.demo",
    "md": "md.demo",
}


def die(msg: str) -> None:
    print(f"\nFAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def login(username: str) -> requests.Session:
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/auth/login", json={"username": username, "password": PASSWORD})
    if resp.status_code != 200:
        die(f"login as {username} failed ({resp.status_code}): {resp.text}\n"
            f"  Have you run sql/demo_only/043_seed_demo_multi_role_users.sql yet?")
    return s


def call(session: requests.Session, method: str, path: str, as_user: str, **kwargs) -> dict:
    resp = session.request(method, f"{BASE_URL}{path}", **kwargs)
    if resp.status_code >= 400:
        die(f"{method} {path} as {as_user} -> {resp.status_code}: {resp.text}")
    return resp.json() if resp.text else {}


def get_or_create(session: requests.Session, as_user: str, list_path: str, create_path: str,
                   match_field: str, match_value: str, create_body: dict) -> dict:
    """List first (idempotent re-run support), create only if not found."""
    existing = call(session, "GET", list_path, as_user)
    for row in existing:
        if row.get(match_field) == match_value:
            return row
    return call(session, "POST", create_path, as_user, json=create_body)


def main() -> None:
    print("Logging in as each demo user...")
    sessions = {key: login(username) for key, username in USERS.items()}
    print("  OK - all 6 demo users authenticated.\n")

    hr, manager, hod, employee, planthead, md = (
        sessions["hr"], sessions["manager"], sessions["hod"],
        sessions["employee"], sessions["planthead"], sessions["md"],
    )

    # ---- Employee IDs for each demo user (from their own /auth/me) ----
    ids = {}
    for key, session in sessions.items():
        me = call(session, "GET", "/auth/me", key)
        ids[key] = me["employee_id"]
    emp_employee_id = ids["employee"]
    manager_employee_id = ids["manager"]
    planthead_employee_id = ids["planthead"]

    # ---- 0. Make sure the employee and the plant head share a Plant ----
    # (Plant Head Approval is scoped by matching Employee.PlantID -
    # sql/demo_only/043 doesn't set one, so this demo script does.)
    print("Linking employee + plant head to a shared Plant...")
    company = get_or_create(
        hr, "hr", "/masters/companies", "/masters/companies",
        "company_code", "SAMPLE-CO1",
        {"company_code": "SAMPLE-CO1", "company_name": "Sample Biologics Ltd"},
    )
    plant = get_or_create(
        hr, "hr", "/masters/plants", "/masters/plants",
        "plant_code", "SAMPLE-PLT1",
        {"company_id": company["company_id"], "plant_code": "SAMPLE-PLT1", "plant_name": "Sample Plant - Unit 1"},
    )
    plant_id = plant["plant_id"]
    for target_employee_id, label in ((emp_employee_id, "emp.demo"), (planthead_employee_id, "planthead.demo")):
        call(hr, "PUT", f"/employees/{target_employee_id}", "hr",
             json={"plant_id": plant_id, "reason": "Demo setup: link to shared plant for Plant Head Approval scoping"})
    print(f"  OK - both linked to PlantID={plant_id} ({plant['plant_name']}).\n")

    # ---- 1. KPA Master ----
    print("Creating KPA Master...")
    kpa = get_or_create(
        hr, "hr", "/masters/kpa", "/masters/kpa",
        "kpa_code", "DEMO-KPA-01",
        {"kpa_code": "DEMO-KPA-01", "kpa_name": "Process Excellence", "description": "Demo KPA for workflow walkthrough"},
    )
    kpa_id = kpa["kpa_id"]
    print(f"  OK - KPAID={kpa_id}\n")

    # ---- 2a. KPI Master ----
    print("Creating KPI Master...")
    kpi = get_or_create(
        hr, "hr", "/masters/kpi", "/masters/kpi",
        "kpi_code", "DEMO-KPI-01",
        {
            "kpi_code": "DEMO-KPI-01", "kpi_name": "Batch Right-First-Time %",
            "kpa_id": kpa_id, "measurement_type": "NUMERIC",
            "minimum_target": 80.0, "expected_target": 95.0, "stretch_target": 100.0,
            "weightage": 100.0,
        },
    )
    kpi_id = kpi["kpi_id"]
    print(f"  OK - KPIID={kpi_id}\n")

    # ---- 2b. Scoring rule + rating bands (needed by the Scoring Engine at MD approval) ----
    print("Ensuring a KPI scoring rule and rating bands exist...")
    existing_rules = call(hr, "GET", "/masters/scoring-rules", "hr")
    if not any(r.get("kpi_id") == kpi_id for r in existing_rules):
        call(hr, "POST", "/masters/scoring-rules", "hr",
             json={"kpi_id": kpi_id, "min_achievement": 0, "max_achievement": 200, "score": 5})
    existing_ratings = call(hr, "GET", "/masters/ratings", "hr")
    if not existing_ratings:
        call(hr, "POST", "/masters/ratings", "hr",
             json={"rating_label": "Exceeds Expectations", "min_percent": 0, "max_percent": 200})
    print("  OK.\n")

    # ---- 3. Performance Cycle ----
    print("Creating Performance Cycle...")
    cycle_name = f"DEMO-2026-27-{CYCLE_TAG}"
    cycles = call(hr, "GET", "/masters/performance-cycles", "hr")
    cycle = next((c for c in cycles if c.get("cycle_name") == cycle_name), None)
    if cycle is None:
        cycle = call(hr, "POST", "/masters/performance-cycles", "hr", json={"cycle_name": cycle_name})
    cycle_id = cycle["cycle_id"]
    print(f"  OK - CycleID={cycle_id} ({cycle_name})\n")

    # ---- 4. Assignment (manager creates the appraisal shell) ----
    print("Creating assignment + attaching KPA/KPI (as manager.demo)...")
    existing_assignments = call(manager, "GET", "/assignments", "manager")
    existing = next(
        (a for a in existing_assignments if a["employee_id"] == emp_employee_id and a["cycle_id"] == cycle_id),
        None,
    )
    if existing is not None:
        die(
            f"An assignment already exists for this employee+cycle (PerformanceID={existing['performance_id']}, "
            f"status={existing['status']}). Re-running this script for the SAME cycle isn't supported once an "
            f"assignment exists - pass a different tag to create another appraisal, e.g.:\n"
            f"    python scripts/demo_full_workflow.py {int(CYCLE_TAG) + 1 if CYCLE_TAG.isdigit() else 2}"
        )
    assignment = call(manager, "POST", "/assignments", "manager",
                       json={"employee_id": emp_employee_id, "cycle_id": cycle_id})
    performance_id = assignment["performance_id"]

    employee_kpa = call(manager, "POST", f"/assignments/{performance_id}/kpas", "manager", json={"kpa_id": kpa_id})
    employee_kpa_id = employee_kpa["employee_kpa_id"]

    employee_kpi = call(
        manager, "POST", f"/assignments/{performance_id}/kpas/{employee_kpa_id}/kpis", "manager",
        json={"kpi_id": kpi_id, "weightage": 100.0, "target": 95.0, "unit": "%"},
    )
    employee_kpi_id = employee_kpi["employee_kpi_id"]

    call(manager, "POST", f"/assignments/{performance_id}/submit", "manager")
    print(f"  OK - PerformanceID={performance_id}, status now KPI_ASSIGNED.\n")

    # ---- 5. Self-Assessment (employee) ----
    print("Employee self-assessment (as emp.demo)...")
    call(employee, "POST", f"/self-assessments/{performance_id}/acknowledge", "employee")
    call(employee, "PUT", f"/self-assessments/{performance_id}/kpis/{employee_kpi_id}", "employee",
         json={"achievement": 97.0, "employee_comments": "Consistently exceeded RFT target this cycle."})
    call(employee, "POST", f"/self-assessments/{performance_id}/submit", "employee")
    print("  OK - status now MANAGER_REVIEW.\n")

    # ---- 6. Manager Review ----
    print("Manager review (as manager.demo)...")
    call(manager, "PUT", f"/manager-reviews/{performance_id}/kpis/{employee_kpi_id}", "manager",
         json={"manager_score": 5, "manager_comments": "Agree with self-assessment - excellent RFT performance."})
    call(manager, "POST", f"/manager-reviews/{performance_id}/submit", "manager")
    print("  OK - status now HOD_REVIEW.\n")

    # ---- 7. HOD Review ----
    print("HOD review (as hod.demo)...")
    call(hod, "PUT", f"/hod-reviews/{performance_id}", "hod",
         json={"hod_score": 95.0, "hod_comments": "Consistent with manager's assessment."})
    call(hod, "POST", f"/hod-reviews/{performance_id}/approve", "hod")
    print("  OK - status now HR_REVIEW.\n")

    # ---- 8. HR Review ----
    print("HR review / calibration (as hr.demo)...")
    call(hr, "PUT", f"/hr-reviews/{performance_id}", "hr", json={"hr_comments": "Calibration reviewed, no adjustment needed."})
    call(hr, "POST", f"/hr-reviews/{performance_id}/complete", "hr")
    print("  OK - status now PLANT_HEAD_APPROVAL.\n")

    # ---- 9. Plant Head Approval ----
    print("Plant Head approval (as planthead.demo)...")
    call(planthead, "POST", f"/plant-head-approvals/{performance_id}/approve", "planthead",
         json={"comments": "Approved."})
    print("  OK - status now MD_APPROVAL.\n")

    # ---- 10. MD Approval (triggers the Scoring Engine) ----
    print("MD final approval (as md.demo) - this also runs the Scoring Engine...")
    call(md, "POST", f"/md-approvals/{performance_id}/approve", "md", json={"comments": "Final approval granted."})
    print("  OK - status now FINAL_APPROVED, record locked.\n")

    # ---- 11. Read back the final score ----
    result = call(hr, "GET", f"/scoring-engine/{performance_id}", "hr")
    print("=" * 60)
    print(f"DONE. PerformanceID {performance_id} for Rohan Iyer (emp.demo):")
    print(f"  Final score:  {result.get('final_score_pct')}%")
    print(f"  Rating:       {result.get('rating_label')}")
    print("=" * 60)
    print("\nLog in as emp.demo to see it on My Performance, or as any")
    print("other demo role to see it reflected on their Dashboard.")


if __name__ == "__main__":
    main()
