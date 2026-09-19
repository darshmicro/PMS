"""
Shared helper for profile-photo URLs, used everywhere an Employee (or a
row that carries one, like a review/approval record) is rendered so the
photo shows "before the name" consistently across the app - the Employees
list, Users & Roles, the review/approval chain, and the topbar/sidebar
(see auth_service.py/auth.py). Keeping this in one place means every
caller derives the same URL shape (GET /employees/{id}/photo, served by
app/api/routes/employees.py) from the same underlying column
(Employee.ProfilePhotoPath) without duplicating the null-check.
"""


def employee_photo_url(employee) -> str | None:
    if employee is None or not getattr(employee, "ProfilePhotoPath", None):
        return None
    return f"/employees/{employee.EmployeeID}/photo"


def company_logo_url(company) -> str | None:
    if company is None or not getattr(company, "LogoPath", None):
        return None
    return f"/masters/companies/{company.CompanyID}/logo"
