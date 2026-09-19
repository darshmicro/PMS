/*
    M21 permission wiring. No RBAC matrix row exists for this module (see
    model docstring) - Section 7's screen list places PIP management under
    HR, and the table's own ManagerID column names a specifically assigned
    manager per PIP. PIP.VIEW is granted broadly (Employee sees own PIP via
    app-layer scope, Manager sees PIPs assigned to them, HR/Plant Head/MD/
    HR Administrator see all); PIP.EDIT is granted to the same broad-access
    roles plus Manager (scoped in-app to PIPs where PIP.ManagerID matches
    the caller - enforced in pip_service.ensure_can_act, not by this table
    alone). Creating a brand-new PIP is further restricted, in the route
    handler itself, to the broad-access roles only - a Manager holding
    PIP.EDIT may work PIPs already assigned to them but may not open one.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PIP.VIEW', 'PIP', 'View PIPs (scope depends on role)'),
    ('PIP.EDIT', 'PIP', 'Create/edit/close PIPs (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PIP.VIEW: Employee (own), Manager (assigned), HR/Plant Head/MD/HR Admin (all) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PIP.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== PIP.EDIT: Manager (scoped to assigned PIPs, in-app), HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PIP.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
