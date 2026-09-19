/*
    M26 permission wiring. Audit_Log itself and its write path
    (write_audit()) have existed since M1 - this is only the reader's
    permission, following Section 5's "Audit Log" row exactly:
    X | X | X | V(dept) | V(plant) | V(all) | V(all) | V(all, no edit)
    for Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator/System
    Administrator. There is no AUDIT_LOG.EDIT - nobody edits an audit
    trail, matching the matrix's own "no edit" note for every role that
    can see it at all, and the DB-grant-level insert-only enforcement
    already documented on the Audit_Log table itself (sql/001_...).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('AUDIT_LOG.VIEW', 'AUDIT_LOG', 'View the audit trail (scope depends on role - see matrix row)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== AUDIT_LOG.VIEW: HR (dept), Plant Head (plant), MD/HR Admin/Sys Admin (all) =====
-- Employee/Manager/HOD deliberately excluded - the matrix's "X".
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'AUDIT_LOG.VIEW'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
