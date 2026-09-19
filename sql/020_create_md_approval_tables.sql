/*
    M17 DDL: MD Final Approval (spec Section 11). Structurally identical
    to PlantHead_Approvals (M16) - no score column, MD approves/returns
    the record as a whole. One row per Employee_Performance, reused
    across repeated approve/return cycles. Run after 019 (Plant Head
    Approval).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'MD_Approvals')
BEGIN
    CREATE TABLE MD_Approvals (
        ApprovalID       INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        Decision         VARCHAR(20) NULL,   -- APPROVE, RETURN
        Comments         VARCHAR(1000) NULL,
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_MDApproval_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_MDApproval_Decision CHECK (Decision IS NULL OR Decision IN ('APPROVE', 'RETURN'))
    );
END;
GO

/*
    Note: the "return requires non-empty Comments" rule (mirroring every
    return action since M13) stays in app/services/md_approval_service.py,
    not a CHECK constraint, for the same reason as M16's identical rule -
    a CHECK constraint can't express "required only for this action".

    Also note: Employee_Performance.IsLocked is set to 1 by this module's
    /approve endpoint (app/services/md_approval_service.finalize_and_lock),
    modelling the workflow diagram's actor-less "FINAL_APPROVED -> LOCKED:
    System locks record" arrow as an immediate consequence of approval
    rather than a distinct stage/table of its own.
*/
GO
