/*
    M11 permission wiring. ASSIGNMENT.VIEW/EDIT are new permission codes
    (unlike M5-M10, which reused the generic MASTERS.* codes) because
    assignment visibility and edit rights follow the record-scoped
    Manager/HOD/broad-role pattern from the Employee Master (M4), not the
    flat "everyone views, HR+ edits" pattern the org/performance masters use.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ASSIGNMENT.VIEW', 'KPA_KPI_ASSIGNMENT', 'View KPA/KPI assignments (scope depends on role)'),
    ('ASSIGNMENT.EDIT', 'KPA_KPI_ASSIGNMENT', 'Create/edit/submit KPA/KPI assignments (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== ASSIGNMENT.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== ASSIGNMENT.EDIT: Manager, HR, Plant Head, MD, HR Admin =====
-- (spec Section 10: "Manager/HR can assign KPAs and KPIs to employees";
--  Section 4 gives Plant Head/MD full business-level admin rights, and
--  HR Admin administers on HR's behalf. HOD is view-only here - HOD's
--  own authority begins at the review stage, M17.)
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
