/*
    M20 permission wiring. No RBAC matrix row exists for this module (see
    model docstring), so DEVELOPMENT_PLAN.VIEW/.EDIT reuse the exact same
    role split as ASSIGNMENT.VIEW/.EDIT (M11): everyone views (Employee
    sees own via app-layer scope, matching the "My Development Plan"
    screen), and Manager/HR/Plant Head/MD/HR Administrator may create/edit
    - HOD is added to the edit set here (unlike M11's ASSIGNMENT.EDIT)
    because HODReview already captures DevelopmentRecommendation/
    TrainingRequirement during HOD's own review stage, making HOD a
    natural author of the resulting development plan too.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('DEVELOPMENT_PLAN.VIEW', 'DEVELOPMENT_PLAN', 'View development plans (scope depends on role)'),
    ('DEVELOPMENT_PLAN.EDIT', 'DEVELOPMENT_PLAN', 'Create/edit development plans (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== DEVELOPMENT_PLAN.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DEVELOPMENT_PLAN.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== DEVELOPMENT_PLAN.EDIT: Manager, HOD, HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DEVELOPMENT_PLAN.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
