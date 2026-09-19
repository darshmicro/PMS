/*
    Employee self-service KPA/KPI proposal. Adds ASSIGNMENT.PROPOSE, a
    narrower sibling of M11's ASSIGNMENT.EDIT (sql/009) granted to the
    EMPLOYEE role only - see app/api/routes/assignments.py's module
    docstring ("DESIGN NOTE on ASSIGNMENT.PROPOSE") for the full design:
    it lets an employee create/edit their own DRAFT appraisal record's
    KPAs/KPIs (never anyone else's - the existing role-scope check in
    assignments.py restricts a plain EMPLOYEE-role caller to their own
    EmployeeID regardless of which permission let them in), while
    submission (POST /assignments/{id}/submit, moving the record out of
    DRAFT) stays ASSIGNMENT.EDIT-only - i.e. Manager/HR/Plant Head/MD/HR
    Admin - so a Manager reviewing and submitting an employee-proposed
    draft is what "approves" it. No new status field, no schema change.

    USE PMS_DB; GO at the top - see sql/040's fix note for why every
    standalone script needs this (a query window can default to `master`
    or whatever DB it was last pointed at otherwise).
*/
USE PMS_DB;
GO

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ASSIGNMENT.PROPOSE', 'KPA_KPI_ASSIGNMENT', 'Employee: create/edit own DRAFT KPA/KPI assignment (subject to Manager/HR submitting it before it takes effect)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== ASSIGNMENT.PROPOSE: EMPLOYEE only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.PROPOSE'
WHERE r.RoleCode = 'EMPLOYEE'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO
