/*
    M18 permission wiring. SCORING_ENGINE.VIEW follows the exact same
    broad grant as ASSIGNMENT.VIEW (M11) - everyone who can see the
    underlying appraisal record can see its final score/rating too, with
    app-layer scoping (self/reports/dept/broad-access, mirroring
    assignments.py's _apply_scope) narrowing it per role. There is no
    SCORING_ENGINE.EDIT - this module never exposes a manual write path
    (see scoring_engine_service.py: the engine runs automatically, once,
    from MD Approval's own /approve action).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SCORING_ENGINE.VIEW', 'SCORING_ENGINE', 'View computed component scores, final score and rating')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SCORING_ENGINE.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SCORING_ENGINE.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
