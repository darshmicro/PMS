/*
    M24 permission wiring. Unlike every module since M18, this one HAS an
    explicit RBAC matrix row to work from - Section 5's "Dashboards" row:
    Own | Team | Dept | Org | Plant | Org | Org | System health only, for
    Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator/System
    Administrator respectively. There is no dedicated table for this
    module (it aggregates Employee_Performance/Audit_Log/Notifications
    live), so this is the only SQL file M24 needs.

    A single DASHBOARD.VIEW permission is granted to all eight roles -
    which of the two dashboard shapes (business summary vs. system
    health) a given caller gets is decided in the route handler by role,
    not by a second permission code (see dashboard.py's own docstring).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('DASHBOARD.VIEW', 'DASHBOARD', 'View your role-scoped dashboard (business summary or system health)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== DASHBOARD.VIEW: every role (scope/shape enforced in-app per the matrix row) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DASHBOARD.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
