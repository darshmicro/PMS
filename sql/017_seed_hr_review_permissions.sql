/*
    M15 permission wiring. HR_REVIEW.EDIT is HR-only - per the RBAC
    matrix's "HR Review/Calibration: C,V,E" row, even HR Administrator,
    Plant Head and MD get View only here, matching HOD Review's pattern of
    Edit belonging to exactly one role at each stage. Employee, Manager and
    HOD get no access at all, same as HOD Review.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('HR_REVIEW.VIEW', 'HR_REVIEW', 'View HR reviews/calibration'),
    ('HR_REVIEW.EDIT', 'HR_REVIEW', 'Record calibration adjustment and complete HR Review (HR only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== HR_REVIEW.VIEW: HR + broad business-admin roles =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HR_REVIEW.VIEW'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== HR_REVIEW.EDIT: HR only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HR_REVIEW.EDIT'
WHERE r.RoleCode = 'HR'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
