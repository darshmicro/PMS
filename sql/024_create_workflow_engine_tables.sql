/*
    M19 DDL: Workflow_History (spec Section 4.5). A dedicated, insert-only
    per-record transition log, distinct from Audit_Log (see the model's
    own docstring for why both exist). Run after 023 (Scoring Engine).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Workflow_History')
BEGIN
    CREATE TABLE Workflow_History (
        WorkflowHistoryID INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        FromStatus      VARCHAR(30) NULL,
        ToStatus        VARCHAR(30) NULL,
        ActionedBy      INT NULL REFERENCES Users(UserID),
        ActionedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        Comments        VARCHAR(500) NULL
    );
END;
GO

-- Workflow_History has no UPDATE/DELETE grants for the application role,
-- matching Audit_Log's own insert-only convention (Sec 32).
GO
