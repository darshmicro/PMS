/*
    M3/M4 permission wiring. MASTERS.VIEW/EDIT/DEACTIVATE already exist
    from 002_seed_roles_and_permissions.sql but were not yet assigned to
    any role - this file assigns them, and adds the new EMPLOYEE_MASTER.*
    permissions, exactly per the Role-Permission Matrix in the design doc.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('EMPLOYEE_MASTER.VIEW',       'EMPLOYEE_MASTER', 'View employee records (scope depends on role)'),
    ('EMPLOYEE_MASTER.EDIT',       'EMPLOYEE_MASTER', 'Create/edit employee records'),
    ('EMPLOYEE_MASTER.DEACTIVATE', 'EMPLOYEE_MASTER', 'Deactivate employee records')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MASTERS.VIEW: everyone (Employee, Manager, HOD, HR, Plant Head, MD, HR Admin) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MASTERS.EDIT: HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.EDIT'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MASTERS.DEACTIVATE: Plant Head, MD, HR Admin only (per matrix, HR has C,V,E but not Deact) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.DEACTIVATE'
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== EMPLOYEE_MASTER.VIEW: everyone (scope narrowed in the app layer, not here) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'EMPLOYEE_MASTER.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== EMPLOYEE_MASTER.EDIT / DEACTIVATE: HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('EMPLOYEE_MASTER.EDIT', 'EMPLOYEE_MASTER.DEACTIVATE')
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
