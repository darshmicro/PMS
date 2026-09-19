/*
    M25 permission wiring. Like Dashboards (M24), this module has an
    explicit RBAC matrix row - Section 5's "Reports/Exports" row:
    Own | Team-scoped | Dept-scoped | Org-scoped | Plant-scoped |
    Org-scoped | Org-scoped | X, for Employee/Manager/HOD/HR/Plant
    Head/MD/HR Administrator/System Administrator respectively. There is
    no dedicated table for this module either (the catalog is a static
    list in code; the one new report aggregates Employee_Performance
    live, exactly like Dashboards), so this is the only SQL file M25
    needs.

    REPORT.VIEW gates both the catalog (GET /reports/catalog, filtered to
    whichever OTHER permissions the caller already holds - see
    report_service.list_available_reports) and the new consolidated
    Appraisal Status report. It is granted to every role except System
    Administrator, matching the matrix's "X" for that column exactly -
    unlike Dashboards (M24), where Sys Admin gets a genuine, if
    different, dashboard, here it gets nothing at all.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('REPORT.VIEW', 'REPORT', 'View the Reports & Export Center catalog and the consolidated Appraisal Status report')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== REPORT.VIEW: every role except System Administrator (matrix: X) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'REPORT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
