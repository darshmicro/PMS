/*
    M21 DDL: PIP (spec Section 4.5). EmployeeID-scoped, not tied to one
    Employee_Performance record - a PIP can be opened independent of where
    the employee sits in a given cycle's workflow. Run after 027
    (Development Plan).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PIP')
BEGIN
    CREATE TABLE PIP (
        PIPID               INT IDENTITY PRIMARY KEY,
        EmployeeID          INT NOT NULL REFERENCES Employees(EmployeeID),
        PerformanceGap      VARCHAR(500) NULL,
        ExpectedPerformance VARCHAR(500) NULL,
        ImprovementTarget   VARCHAR(500) NULL,
        ActionPlan          VARCHAR(1000) NULL,
        Training            VARCHAR(500) NULL,
        ManagerID           INT NULL REFERENCES Employees(EmployeeID),
        ReviewDate          DATE NULL,
        PIPStartDate        DATE NULL,
        PIPEndDate          DATE NULL,
        Outcome             VARCHAR(30) NULL,
        Comments            VARCHAR(1000) NULL,
        CreatedAt           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt           DATETIME2 NULL,
        CONSTRAINT CK_PIP_Outcome CHECK (Outcome IS NULL OR Outcome IN ('SUCCESSFUL', 'UNSUCCESSFUL', 'EXTENDED'))
    );
END;
GO

/*
    Note: Outcome is nullable and stays NULL while a PIP is open - only a
    dedicated /close action sets it, one-way (see model/service docstrings).
    ManagerID here is the PIP's own assigned-manager field, not read from
    Employee.ManagerID's org-chart line - see model module docstring for why.
*/
GO
