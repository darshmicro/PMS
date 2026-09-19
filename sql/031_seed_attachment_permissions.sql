/*
    M22 permission wiring. No RBAC matrix row exists for this module (see
    router docstring). ATTACHMENT.VIEW/.EDIT reuse the same broad
    review-chain visibility scope as ASSIGNMENT/SELF_ASSESSMENT: Employee
    (own evidence, app-layer scope), Manager/HOD (their reports/
    department, app-layer scope), HR/Plant Head/MD/HR Administrator
    (everyone). Uploading (ATTACHMENT.EDIT) is granted alongside viewing
    to the same full set, since ownership within that scope is checked
    per-request in the route handler (_ensure_can_upload_for) rather than
    narrowed by role at grant time - unlike Self-Assessment, this module
    also has to support HR/Manager-uploaded evidence (e.g. PIP supporting
    documents), not employee-authored evidence alone.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ATTACHMENT.VIEW', 'ATTACHMENT', 'View attachments/evidence (scope depends on role)'),
    ('ATTACHMENT.EDIT', 'ATTACHMENT', 'Upload attachments/evidence (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== ATTACHMENT.VIEW / ATTACHMENT.EDIT: everyone (scope enforced in-app) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('ATTACHMENT.VIEW', 'ATTACHMENT.EDIT')
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
