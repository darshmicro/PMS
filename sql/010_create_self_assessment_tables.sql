/*
    M12 DDL: Employee Self-Assessment (spec Section 11). One row per
    Employee_KPI, seeded when the employee acknowledges their KPI
    assignment (Employee_Performance.Status: KPI_ASSIGNED ->
    EMPLOYEE_ACKNOWLEDGED). Run after 008 (KPA/KPI Assignment).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Self_Assessments')
BEGIN
    CREATE TABLE Self_Assessments (
        SelfAssessmentID INT IDENTITY PRIMARY KEY,
        EmployeeKPIID    INT NOT NULL REFERENCES Employee_KPI(EmployeeKPIID) ON DELETE CASCADE,
        Achievement      DECIMAL(18,4) NULL,
        AchievementPct   DECIMAL(9,2) NULL,
        SelfScore        INT NULL,
        EmployeeComments VARCHAR(1000) NULL,
        DevelopmentNeed  VARCHAR(500) NULL,
        Status           VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT, SUBMITTED, RETURNED
        SubmittedAt      DATETIME2 NULL,
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_SelfAssessment_EmployeeKPI UNIQUE (EmployeeKPIID),
        CONSTRAINT CK_SelfAssessment_SelfScore CHECK (SelfScore IS NULL OR (SelfScore BETWEEN 1 AND 5))
    );
    CREATE INDEX IX_SelfAssessment_Status ON Self_Assessments(Status);
END;
GO

/*
    Note: as with Employee_KPI's weightage-sums-to-100% rule (M11), the
    "every assigned KPI must be assessed before submission" rule needs to
    see every sibling row for the whole Employee_Performance record and
    cannot be a single-table CHECK constraint - it is enforced in
    app/services/self_assessment_service.py::validate_submission_ready.
*/
GO
