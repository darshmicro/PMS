/*
    M28 permission wiring. The last row in the whole RBAC matrix
    (Section 5): System Configuration (SMTP, AD server, storage path) is
    "X" for every role except System Administrator, who gets C,V,E - the
    single narrowest-reach row in the entire matrix, and the only module
    in this codebase granted to System Administrator alone.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SYSTEM_CONFIG.VIEW', 'SYSTEM_CONFIG', 'View app-wide operational configuration'),
    ('SYSTEM_CONFIG.EDIT', 'SYSTEM_CONFIG', 'Create/edit app-wide operational configuration')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SYSTEM_CONFIG.VIEW / .EDIT: System Administrator only =====
-- Note: the route layer itself gates on require_any_role("SYS_ADMIN"),
-- not these permission codes, since no other role holds them - these
-- grants exist for completeness/consistency with every other module's
-- Permissions/Role_Permissions wiring, and for any future UI that wants
-- to check "can this user reach the System Configuration screen at all."
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('SYSTEM_CONFIG.VIEW', 'SYSTEM_CONFIG.EDIT')
WHERE r.RoleCode = 'SYS_ADMIN'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
