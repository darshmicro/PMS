/* Client-side mirror of the role -> permission grants seeded in sql/
   (005, 009, 011, 013, 015, 017, 019, 021, 035, 044). The server is the
   real enforcement point (every route still depends on require_permission/
   require_any_permission - see app/core/dependencies.py) - this map only
   decides which buttons/nav items/forms this page bothers to show, exactly
   like dependencies.py's own docstring describes ("the UI also hides
   buttons the user can't use"). If it drifts from the SQL grants, the
   worst case is a button that 403s when clicked, not a security hole. */

const PMS_ROLE_CAPS = {
  ASSIGNMENT_VIEW: ["EMPLOYEE", "MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  ASSIGNMENT_EDIT: ["MANAGER", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  ASSIGNMENT_PROPOSE: ["EMPLOYEE"],

  SELF_ASSESSMENT_VIEW: ["EMPLOYEE", "MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  SELF_ASSESSMENT_EDIT: ["EMPLOYEE"],

  MANAGER_REVIEW_VIEW: ["MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  MANAGER_REVIEW_EDIT: ["MANAGER"],

  HOD_REVIEW_VIEW: ["HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  HOD_REVIEW_EDIT: ["HOD"],

  HR_REVIEW_VIEW: ["HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  HR_REVIEW_EDIT: ["HR"],

  PLANT_HEAD_APPROVAL_VIEW: ["PLANT_HEAD", "MD", "HR_ADMIN"],
  PLANT_HEAD_APPROVAL_EDIT: ["PLANT_HEAD"],

  MD_APPROVAL_VIEW: ["MD", "HR_ADMIN"],
  MD_APPROVAL_EDIT: ["MD"],

  REPORT_VIEW: ["EMPLOYEE", "MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],

  // MASTERS.VIEW/EDIT/DEACTIVATE (sql/005_seed_m3_m4_permissions.sql) cover
  // every master data type - org masters, KPA, KPI, Scoring Rules, Ratings,
  // Competency, Performance Cycles - under the same three permission codes.
  MASTERS_VIEW: ["EMPLOYEE", "MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  MASTERS_EDIT: ["HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  MASTERS_DEACTIVATE: ["PLANT_HEAD", "MD", "HR_ADMIN"],

  // EMPLOYEE_MASTER.VIEW/EDIT/DEACTIVATE (sql/005) - everyone can view (the
  // app layer narrows scope per-role, e.g. a Manager only sees their own
  // reports), but only HR/Plant Head/MD/HR Admin can create, edit or
  // deactivate an employee record.
  EMPLOYEE_MASTER_VIEW: ["EMPLOYEE", "MANAGER", "HOD", "HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  EMPLOYEE_MASTER_EDIT: ["HR", "PLANT_HEAD", "MD", "HR_ADMIN"],
  EMPLOYEE_MASTER_DEACTIVATE: ["HR", "PLANT_HEAD", "MD", "HR_ADMIN"],

  // Mirrors ADMIN_ROLES in app/api/routes/users.py and the role list on
  // POST /auth/demo/set-password/{user_id} - widened from HR
  // Administrator/System Administrator alone so HR and Plant Head can also
  // create logins, assign roles (including promoting to PLANT_HEAD/MD) and
  // reset a first-login password.
  USER_MANAGEMENT_VIEW: ["HR_ADMIN", "SYS_ADMIN", "HR", "PLANT_HEAD"],
  USER_MANAGEMENT_EDIT: ["HR_ADMIN", "SYS_ADMIN", "HR", "PLANT_HEAD"],
};

function pmsHasCap(roleCodes, capKey) {
  const allowed = PMS_ROLE_CAPS[capKey] || [];
  return (roleCodes || []).some((r) => allowed.includes(r));
}

function pmsHasAnyCap(roleCodes, capKeys) {
  return capKeys.some((k) => pmsHasCap(roleCodes, k));
}
