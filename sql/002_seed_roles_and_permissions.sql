/*
    Seed data for M1/M2. Idempotent (MERGE-style guards) so it can be
    re-run safely. Extend Permissions as later modules (M11 onward) are built -
    this file seeds only what M1/M2's own admin screens need to function,
    plus placeholders for the module-level permissions referenced by the
    design doc's RBAC matrix so role assignment can start immediately.
*/

-- ===== Roles (spec Section 3) =====
INSERT INTO Roles (RoleCode, RoleName, IsBusinessRole, IsActive)
SELECT v.RoleCode, v.RoleName, v.IsBusinessRole, 1
FROM (VALUES
    ('EMPLOYEE',    'Employee',                 1),
    ('MANAGER',     'Reporting Manager',        1),
    ('HOD',         'Head of Department',       1),
    ('HR',          'HR',                       1),
    ('PLANT_HEAD',  'Plant Head',               1),
    ('MD',          'Managing Director',        1),
    ('HR_ADMIN',    'HR Administrator',         1),
    ('SYS_ADMIN',   'System Administrator',     0)   -- technical only, no business approval rights
) AS v(RoleCode, RoleName, IsBusinessRole)
WHERE NOT EXISTS (SELECT 1 FROM Roles r WHERE r.RoleCode = v.RoleCode);

-- ===== Permissions =====
-- Naming convention: MODULE.ACTION  (ACTION in {VIEW, CREATE, EDIT, APPROVE, RETURN, DEACTIVATE, EXPORT})
INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    -- User/Role administration (M2 itself)
    ('USER_MANAGEMENT.VIEW',   'USER_MANAGEMENT', 'View AD-to-employee-role mappings'),
    ('USER_MANAGEMENT.EDIT',   'USER_MANAGEMENT', 'Create/edit AD-to-employee-role mappings'),
    ('ROLE_PERMISSIONS.VIEW',  'ROLE_PERMISSIONS','View role-permission assignments'),
    ('ROLE_PERMISSIONS.EDIT',  'ROLE_PERMISSIONS','Edit role-permission assignments'),

    -- Self-assessment / review chain (placeholders wired up fully in M12-M17)
    ('SELF_ASSESSMENT.EDIT',       'SELF_ASSESSMENT',   'Employee can edit own self-assessment'),
    ('MANAGER_REVIEW.EDIT',        'MANAGER_REVIEW',    'Manager can score/comment/return'),
    ('HOD_REVIEW.APPROVE',         'HOD_REVIEW',        'HOD can approve/return'),
    ('HR_REVIEW.EDIT',             'HR_REVIEW',         'HR can calibrate/adjust'),
    ('PLANTHEAD_APPROVAL.APPROVE', 'PLANTHEAD_APPROVAL','Plant Head can approve/return'),
    ('MD_APPROVAL.APPROVE',        'MD_APPROVAL',       'MD can approve/return'),

    -- Masters (placeholders wired up fully in M3-M10)
    ('MASTERS.VIEW',   'MASTERS', 'View master data'),
    ('MASTERS.EDIT',   'MASTERS', 'Create/edit master data'),
    ('MASTERS.DEACTIVATE', 'MASTERS', 'Deactivate master records'),

    -- Audit / export (placeholders for M25/M26)
    ('AUDIT_LOG.VIEW', 'AUDIT_LOG', 'View audit trail, scope depends on role'),
    ('EXPORT.ANY',      'EXPORT',   'Export data at any workflow stage, scope depends on role')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);

-- ===== Role -> Permission wiring for M1/M2's own screens =====
-- HR_ADMIN and SYS_ADMIN administer users/roles; SYS_ADMIN's rights stop at
-- the technical layer (no business approval permissions granted here).
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN (
    'USER_MANAGEMENT.VIEW', 'USER_MANAGEMENT.EDIT',
    'ROLE_PERMISSIONS.VIEW', 'ROLE_PERMISSIONS.EDIT'
)
WHERE r.RoleCode IN ('HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (
      SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID
  );

-- Plant Head and MD get full business-level view rights on user/role admin
-- (view only here; they are not the ones maintaining the mapping day-to-day - Sec 4).
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('USER_MANAGEMENT.VIEW', 'ROLE_PERMISSIONS.VIEW')
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD')
  AND NOT EXISTS (
      SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID
  );
GO
