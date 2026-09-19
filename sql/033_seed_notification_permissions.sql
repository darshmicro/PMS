/*
    M23 permission wiring. No RBAC matrix row exists for this module (see
    service module docstring) - Section 7's "Notifications panel" is a
    Common screen for every role, so NOTIFICATION.VIEW is granted to all
    eight roles including System Administrator (a technical account may
    have no linked Employee row at all - handled in-app as "no possible
    notifications" rather than an error). There is no NOTIFICATION.EDIT -
    marking a notification read is bundled into NOTIFICATION.VIEW as part
    of using your own inbox, not a separately grantable capability.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('NOTIFICATION.VIEW', 'NOTIFICATION', 'View and mark read your own notifications')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== NOTIFICATION.VIEW: every role (always self-scoped, enforced in-app) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'NOTIFICATION.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
