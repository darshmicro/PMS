/*
    M16 DDL: Plant Head Approval (spec Section 11). Unlike HOD_Reviews
    (M14) and HR_Reviews (M15), this table has no score column at all -
    Plant Head does not re-score the record, they approve or return it
    based on the HR-calibrated score that already exists. One row per
    Employee_Performance, reused across repeated approve/return cycles.
    Run after 017 (HR Review).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PlantHead_Approvals')
BEGIN
    CREATE TABLE PlantHead_Approvals (
        ApprovalID       INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        Decision         VARCHAR(20) NULL,   -- APPROVE, RETURN
        Comments         VARCHAR(1000) NULL,
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_PlantHeadApproval_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_PlantHeadApproval_Decision CHECK (Decision IS NULL OR Decision IN ('APPROVE', 'RETURN'))
    );
END;
GO

/*
    Note: "a RETURN decision requires non-empty Comments" (mirroring the
    mandatory-reason rule for every return action since M13) depends on
    two columns together, so - consistent with every cross-field rule
    since M8 - it stays in app/services/plant_head_approval_service.py
    rather than a CHECK constraint.
*/
GO
