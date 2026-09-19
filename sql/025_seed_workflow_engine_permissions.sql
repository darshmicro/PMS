/*
    M19 permission wiring. WORKFLOW_ENGINE.VIEW follows the same broad
    grant as ASSIGNMENT.VIEW (M11) and SCORING_ENGINE.VIEW (M18) -
    everyone who can see the underlying appraisal record can see its
    workflow status/history too, narrowed by the identical app-layer
    self/reports/dept/broad-access scoping. No .EDIT code - this module
    is entirely read-only (see workflow_engine_service.py).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('WORKFLOW_ENGINE.VIEW', 'WORKFLOW_ENGINE', 'View workflow status, SLA and transition history')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== WORKFLOW_ENGINE.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'WORKFLOW_ENGINE.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
