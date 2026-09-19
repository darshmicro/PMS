import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    assignments,
    attachments,
    audit_log,
    auth,
    competency,
    dashboard,
    demo_auth,
    development_plans,
    employees,
    hod_reviews,
    hr_reviews,
    kpa,
    kpi,
    manager_reviews,
    masters,
    md_approvals,
    notifications,
    performance_cycles,
    performance_history,
    pip,
    plant_head_approvals,
    reports,
    roles,
    scoring,
    scoring_engine,
    self_assessments,
    system_config,
    users,
    workflow_engine,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.APP_NAME)

# Intranet-only app served behind IIS on the same origin in production;
# CORS is permissive here only to ease local dev against a separate frontend port.
if settings.ENVIRONMENT == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(demo_auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(masters.router)
app.include_router(employees.router)
app.include_router(performance_cycles.router)
app.include_router(kpa.router)
app.include_router(kpi.router)
app.include_router(scoring.router)
app.include_router(competency.router)
app.include_router(assignments.router)
app.include_router(self_assessments.router)
app.include_router(manager_reviews.router)
app.include_router(hod_reviews.router)
app.include_router(hr_reviews.router)
app.include_router(plant_head_approvals.router)
app.include_router(md_approvals.router)
app.include_router(scoring_engine.router)
app.include_router(workflow_engine.router)
app.include_router(development_plans.router)
app.include_router(pip.router)
app.include_router(attachments.router)
app.include_router(notifications.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(audit_log.router)
app.include_router(performance_history.router)
app.include_router(system_config.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# Static frontend (plain HTML/CSS/JS, no build step). Mounted under /app so
# it can never collide with an API path at root (e.g. /auth/login). Served
# same-origin so the existing signed session cookie works without CORS.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/app", StaticFiles(directory=_STATIC_DIR, html=True), name="static")


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/app/login.html")
