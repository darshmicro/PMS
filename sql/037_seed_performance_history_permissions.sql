/*
    M27 permission wiring. Performance History has no matrix row of its
    own (the same kind of gap M18/M20/M21/M22/M23 already hit) - Section
    7's Employee screen #8, "My Performance History," is the only textual
    anchor. No new table: this module aggregates Employee_Performance,
    Performance_Scores and Workflow_History, all of which already exist.

    Granted to all 7 business roles - every role can at minimum see their
    own history via GET /performance-history/me, and the broader roles
    (Manager/HOD/HR/Plant Head/MD/HR Administrator) can additionally see
    in-scope employees via GET /performance-history/{employee_id}, gated
    at the service layer by can_view_employee_history(), not by this
    permission grant.

    System Administrator is deliberately excluded - performance history is
    business content (scores, ratings), and this codebase's running
    principle since M2 is that System Administrator "has no business
    approval rights." This mirrors M25's Reports & Exports decision, not
    M24's Dashboards system-health carve-out (Performance History has no
    technical-only equivalent for Sys Admin to view instead).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PERFORMANCE_HISTORY.VIEW', 'PERFORMANCE_HISTORY', 'View own or in-scope employees'' historical appraisal records')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PERFORMANCE_HISTORY.VIEW: all 7 business roles, System Administrator excluded =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PERFORMANCE_HISTORY.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
