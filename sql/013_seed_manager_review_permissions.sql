/*
    M13 permission wiring. MANAGER_REVIEW.EDIT is granted to MANAGER only -
    per the RBAC matrix's "Manager Review: C,V,E,R" row, HOD/HR/Plant
    Head/MD/HR Administrator get View only here, despite Plant Head/MD's
    broader business-admin rights elsewhere (their own edit rights begin at
    HOD Review onward, M14+). The route layer additionally enforces that
    even a MANAGER-role holder can only edit reviews for their OWN direct
    reports (manager_review_service.ensure_is_reviewing_manager).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('MANAGER_REVIEW.VIEW', 'MANAGER_REVIEW', 'View manager reviews (scope depends on role)'),
    ('MANAGER_REVIEW.EDIT', 'MANAGER_REVIEW', 'Score/comment, submit, or return a manager review (own reports only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MANAGER_REVIEW.VIEW: everyone in the review chain =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MANAGER_REVIEW.VIEW'
WHERE r.RoleCode IN ('MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MANAGER_REVIEW.EDIT: Manager only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MANAGER_REVIEW.EDIT'
WHERE r.RoleCode = 'MANAGER'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
