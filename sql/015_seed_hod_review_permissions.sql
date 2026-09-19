/*
    M14 permission wiring. Notably, unlike every previous review-stage
    module (Assignment, Self-Assessment, Manager Review), the RBAC matrix's
    HOD Review row grants EMPLOYEE and MANAGER no access at all - not even
    View - so neither role appears in either grant below. HOD_REVIEW.EDIT
    is HOD-only; the route layer further restricts it to the employee's
    own HOD (hod_review_service.ensure_is_reviewing_hod).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('HOD_REVIEW.VIEW', 'HOD_REVIEW', 'View HOD reviews (scope depends on role)'),
    ('HOD_REVIEW.EDIT', 'HOD_REVIEW', 'Score/comment, approve & forward, or return an HOD review (own department only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== HOD_REVIEW.VIEW: HOD + broad business-admin roles only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HOD_REVIEW.VIEW'
WHERE r.RoleCode IN ('HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== HOD_REVIEW.EDIT: HOD only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HOD_REVIEW.EDIT'
WHERE r.RoleCode = 'HOD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
