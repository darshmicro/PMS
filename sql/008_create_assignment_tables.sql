/*
    M11 DDL: KPA/KPI Assignment (spec Section 10). Employee_Performance is
    the appraisal "envelope" for one (employee, cycle) pair that every
    later module (M12 Self-Assessment onward) attaches to via PerformanceID.
    Run after 006 (Performance Masters) and 003 (Employees).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_Performance')
BEGIN
    CREATE TABLE Employee_Performance (
        PerformanceID   INT IDENTITY PRIMARY KEY,
        EmployeeID      INT NOT NULL REFERENCES Employees(EmployeeID),
        CycleID         INT NOT NULL REFERENCES Performance_Cycles(CycleID),
        Status          VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
        TotalWeightage  DECIMAL(5,2) NOT NULL DEFAULT 0,
        FinalScorePct   DECIMAL(6,2) NULL,
        FinalRatingID   INT NULL REFERENCES Rating_Master(RatingID),
        IsLocked        BIT NOT NULL DEFAULT 0,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT UQ_EmployeePerformance_Employee_Cycle UNIQUE (EmployeeID, CycleID)
    );
    CREATE INDEX IX_EmployeePerformance_Employee ON Employee_Performance(EmployeeID);
    CREATE INDEX IX_EmployeePerformance_Cycle ON Employee_Performance(CycleID);
    CREATE INDEX IX_EmployeePerformance_Status ON Employee_Performance(Status);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_KPA')
BEGIN
    CREATE TABLE Employee_KPA (
        EmployeeKPAID   INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        KPAID           INT NOT NULL REFERENCES KPA_Master(KPAID),
        -- Read-only rollup (sum of this KPA's own Employee_KPI rows),
        -- recomputed by the application after every KPI add/edit/remove -
        -- see app/services/assignment_service.py::recompute_rollups.
        Weightage       DECIMAL(5,2) NOT NULL DEFAULT 0,
        CONSTRAINT UQ_EmployeeKPA_Performance_KPA UNIQUE (PerformanceID, KPAID)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_KPI')
BEGIN
    CREATE TABLE Employee_KPI (
        EmployeeKPIID    INT IDENTITY PRIMARY KEY,
        EmployeeKPAID    INT NOT NULL REFERENCES Employee_KPA(EmployeeKPAID) ON DELETE CASCADE,
        KPIID            INT NOT NULL REFERENCES KPI_Master(KPIID),
        Description      VARCHAR(500) NULL,
        Target           DECIMAL(18,4) NULL,
        Unit             VARCHAR(30) NULL,
        -- Snapshot of KPI_Master.MeasurementType at assignment time - see
        -- the model docstring for why this is copied rather than read live.
        MeasurementType  VARCHAR(30) NOT NULL,
        Weightage        DECIMAL(5,2) NOT NULL,
        DueDate          DATE NULL,
        EvidenceRequired BIT NOT NULL DEFAULT 0,
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_EmployeeKPI_EmployeeKPA_KPI UNIQUE (EmployeeKPAID, KPIID),
        CONSTRAINT CK_EmployeeKPI_Weightage CHECK (Weightage > 0 AND Weightage <= 100)
    );
    CREATE INDEX IX_EmployeeKPI_KPI ON Employee_KPI(KPIID);
END;
GO

/*
    Note: SQL Server CHECK constraints can enforce a single row's weightage
    bounds (0 < Weightage <= 100, above) but cannot enforce the cross-row
    "duplicate KPI across the whole appraisal" or "total weightage = 100%
    before submission" rules - those need to see every sibling row and are
    enforced in app/services/assignment_service.py, exactly as the
    KPI-Scoring-Rule / Rating-Master band-overlap rules are in M8/M9.
*/
GO
