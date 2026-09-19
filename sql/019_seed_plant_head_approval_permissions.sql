/*
    M16 permission wiring. Per the RBAC matrix's "Plant Head Approval:
    C,V,A,R" row, Plant Head alone gets edit rights (approve/return) -
    there is no separate EDIT-vs-Approve/Return distinction, so
    PLANT_HEAD_APPROVAL.EDIT is used to gate both the /approve and
    /return actions, matching HOD_REVIEW.EDIT's role in M14. MD and HR
    Administrator get View only; Employee, Manager, HOD and HR get no
    access at all to this stage.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PLANT_HEAD_APPROVAL.VIEW', 'PLANT_HEAD_APPROVAL', 'View Plant Head Approval records'),
    ('PLANT_HEAD_APPROVAL.EDIT', 'PLANT_HEAD_APPROVAL', 'Approve or return a record at Plant Head Approval (Plant Head only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PLANT_HEAD_APPROVAL.VIEW: Plant Head + broad business-admin roles =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PLANT_HEAD_APPROVAL.VIEW'
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== PLANT_HEAD_APPROVAL.EDIT: Plant Head only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PLANT_HEAD_APPROVAL.EDIT'
WHERE r.RoleCode = 'PLANT_HEAD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
