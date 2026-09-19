/*
    M13 DDL: Manager Review (spec Section 11). One row per Employee_KPI,
    created lazily on the manager's first edit (no separate "acknowledge"
    step exists for this stage - see the model docstring). Run after 010
    (Self-Assessment).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Manager_Reviews')
BEGIN
    CREATE TABLE Manager_Reviews (
        ManagerReviewID  INT IDENTITY PRIMARY KEY,
        EmployeeKPIID    INT NOT NULL REFERENCES Employee_KPI(EmployeeKPIID) ON DELETE CASCADE,
        ManagerScore     INT NULL,
        ManagerComments  VARCHAR(1000) NULL,
        DevelopmentRequirement VARCHAR(500) NULL,
        Action           VARCHAR(20) NULL,  -- SUBMIT, RETURN
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_ManagerReview_EmployeeKPI UNIQUE (EmployeeKPIID),
        CONSTRAINT CK_ManagerReview_ManagerScore CHECK (ManagerScore IS NULL OR (ManagerScore BETWEEN 1 AND 5)),
        CONSTRAINT CK_ManagerReview_Action CHECK (Action IS NULL OR Action IN ('SUBMIT', 'RETURN'))
    );
    CREATE INDEX IX_ManagerReview_Action ON Manager_Reviews(Action);
END;
GO

/*
    Note: as with Self_Assessments (M12), the cross-row "every KPI scored
    before submission" rule and the "override requires comments" rule need
    to see sibling rows and/or the linked Self_Assessment row, so they stay
    in app/services/manager_review_service.py rather than a CHECK constraint.
*/
GO
