/*
    M20 DDL: Development_Plans (spec Section 4.5). Zero or more rows per
    Employee_Performance (no UniqueConstraint - several skill gaps can be
    tracked independently). Run after 025 (Workflow Engine).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Development_Plans')
BEGIN
    CREATE TABLE Development_Plans (
        DevPlanID       INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        DevelopmentArea VARCHAR(200) NULL,
        SkillGap        VARCHAR(500) NULL,
        TrainingRequired VARCHAR(500) NULL,
        ActionPlan      VARCHAR(500) NULL,
        ResponsiblePersonID INT NULL REFERENCES Employees(EmployeeID),
        TargetDate      DATE NULL,
        CompletionStatus VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        ReviewComments  VARCHAR(500) NULL,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT CK_DevelopmentPlan_CompletionStatus CHECK (CompletionStatus IN ('PENDING', 'IN_PROGRESS', 'COMPLETED'))
    );
END;
GO

/*
    Note: CompletionStatus's vocabulary (PENDING/IN_PROGRESS/COMPLETED) is
    inferred, not read off the DDL (which only gives a default value, no
    enum/CHECK) - see the model module's own docstring for the reasoning.
    This table also deliberately has no lock/stage gate in the service
    layer - a development plan's tracked lifetime routinely outlives the
    appraisal cycle that created it.
*/
GO
