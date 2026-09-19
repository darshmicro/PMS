/*
    M14 DDL: HOD Review (spec Section 11). One row per Employee_Performance
    (not per-KPI, unlike Self_Assessments/Manager_Reviews - see the model
    docstring for why). Run after 012 (Manager Review).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'HOD_Reviews')
BEGIN
    CREATE TABLE HOD_Reviews (
        HODReviewID      INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        HODScore         DECIMAL(6,2) NULL,
        HODComments      VARCHAR(1000) NULL,
        DevelopmentRecommendation VARCHAR(500) NULL,
        TrainingRequirement VARCHAR(500) NULL,
        Action           VARCHAR(20) NULL,  -- APPROVE_FORWARD, RETURN_TO_MANAGER, RETURN_TO_EMPLOYEE
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_HODReview_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_HODReview_HODScore CHECK (HODScore IS NULL OR (HODScore BETWEEN 0 AND 100)),
        CONSTRAINT CK_HODReview_Action CHECK (Action IS NULL OR Action IN ('APPROVE_FORWARD', 'RETURN_TO_MANAGER', 'RETURN_TO_EMPLOYEE'))
    );
    CREATE INDEX IX_HODReview_Action ON HOD_Reviews(Action);
END;
GO

/*
    Note: the "HOD score differs from the manager-weighted reference
    without comments" rule needs to compute that reference from every
    sibling Manager_Review row, so - like every cross-row rule before it
    since M8 - it stays in app/services/hod_review_service.py rather than
    a CHECK constraint.
*/
GO
