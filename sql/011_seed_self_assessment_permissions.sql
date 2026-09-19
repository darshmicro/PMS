/*
    M12 permission wiring. SELF_ASSESSMENT.EDIT is granted to EMPLOYEE only
    (per the RBAC matrix's "Own Self-Assessment: C,V,E (until submit)" row -
    Manager/HOD/HR/Plant Head/MD/HR Administrator get View only, never
    Edit, unlike KPA/KPI Assignment's ASSIGNMENT.EDIT in M11). The route
    layer additionally enforces that even an EMPLOYEE-role holder can only
    edit their OWN record (self_assessment_service.ensure_own_record) -
    this permission grant alone does not scope by employee.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SELF_ASSESSMENT.VIEW', 'SELF_ASSESSMENT', 'View self-assessments (scope depends on role)'),
    ('SELF_ASSESSMENT.EDIT', 'SELF_ASSESSMENT', 'Create/edit/submit own self-assessment (employee only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SELF_ASSESSMENT.VIEW: everyone in the review chain =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SELF_ASSESSMENT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== SELF_ASSESSMENT.EDIT: Employee only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SELF_ASSESSMENT.EDIT'
WHERE r.RoleCode = 'EMPLOYEE'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
