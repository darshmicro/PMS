/*
    M17 permission wiring. The RBAC matrix's "MD Approval: C,V,A,R" row is
    the narrowest yet - MD alone gets create/view/approve/return rights,
    and only HR Administrator gets View alongside them. Notably, Plant
    Head (the immediately preceding stage) gets NO access at all here,
    unlike every other stage where the immediately preceding role at
    least kept View. Employee, Manager, HOD and HR get no access either.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('MD_APPROVAL.VIEW', 'MD_APPROVAL', 'View MD Approval records'),
    ('MD_APPROVAL.EDIT', 'MD_APPROVAL', 'Approve or return a record at MD Approval (MD only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MD_APPROVAL.VIEW: MD + HR Administrator only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MD_APPROVAL.VIEW'
WHERE r.RoleCode IN ('MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MD_APPROVAL.EDIT: MD only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MD_APPROVAL.EDIT'
WHERE r.RoleCode = 'MD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
