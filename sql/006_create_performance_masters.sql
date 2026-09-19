/*
    M5-M10 DDL: Performance Cycle, KPA, KPI, KPI Scoring Rules, Rating,
    Competency masters. Run after 003 (Org Masters + Employee extension) -
    KPA_Master and KPI_Master reference Departments/Designations.
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Performance_Cycles')
BEGIN
    CREATE TABLE Performance_Cycles (
        CycleID                 INT IDENTITY PRIMARY KEY,
        CycleName                VARCHAR(50) NOT NULL UNIQUE,
        Year                     INT NULL,
        KPISettingStart          DATE NULL, KPISettingEnd DATE NULL,
        SelfAssessmentStart      DATE NULL, SelfAssessmentEnd DATE NULL,
        ManagerReviewStart       DATE NULL, ManagerReviewEnd DATE NULL,
        HODReviewStart           DATE NULL, HODReviewEnd DATE NULL,
        HRReviewStart            DATE NULL, HRReviewEnd DATE NULL,
        PlantHeadApprovalStart   DATE NULL, PlantHeadApprovalEnd DATE NULL,
        MDApprovalStart          DATE NULL, MDApprovalEnd DATE NULL,
        IsActive                 BIT NOT NULL DEFAULT 1,
        CreatedAt                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPA_Master')
BEGIN
    CREATE TABLE KPA_Master (
        KPAID            INT IDENTITY PRIMARY KEY,
        KPACode          VARCHAR(30) NOT NULL UNIQUE,
        KPAName          VARCHAR(150) NOT NULL,
        Description      VARCHAR(500) NULL,
        DepartmentID     INT NULL REFERENCES Departments(DepartmentID),
        DesignationID    INT NULL REFERENCES Designations(DesignationID),
        Category         VARCHAR(60) NULL,
        DefaultWeightage DECIMAL(5,2) NULL,
        EffectiveFrom    DATE NULL,
        EffectiveTo      DATE NULL,
        IsActive         BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_KPA_Weightage CHECK (DefaultWeightage IS NULL OR (DefaultWeightage >= 0 AND DefaultWeightage <= 100))
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_Master')
BEGIN
    CREATE TABLE KPI_Master (
        KPIID            INT IDENTITY PRIMARY KEY,
        KPICode          VARCHAR(30) NOT NULL UNIQUE,
        KPIName          VARCHAR(150) NOT NULL,
        Description      VARCHAR(500) NULL,
        KPAID            INT NOT NULL REFERENCES KPA_Master(KPAID),
        DepartmentID     INT NULL REFERENCES Departments(DepartmentID),
        DesignationID    INT NULL REFERENCES Designations(DesignationID),
        MeasurementType  VARCHAR(30) NOT NULL,
        Unit             VARCHAR(30) NULL,
        TargetType       VARCHAR(20) NULL,
        DefaultTarget    DECIMAL(18,4) NULL,
        MinimumTarget    DECIMAL(18,4) NULL,
        ExpectedTarget   DECIMAL(18,4) NULL,
        StretchTarget    DECIMAL(18,4) NULL,
        Weightage        DECIMAL(5,2) NULL,
        ScoringMethod    VARCHAR(30) NULL,
        IsActive         BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_KPI_Weightage CHECK (Weightage IS NULL OR (Weightage >= 0 AND Weightage <= 100)),
        CONSTRAINT CK_KPI_MeasurementType CHECK (MeasurementType IN (
            'NUMERIC','PERCENTAGE','RATIO','YESNO','DATE','MILESTONE','QTY','COST','REDUCTION','QUALITATIVE'
        ))
    );
    CREATE INDEX IX_KPI_KPA ON KPI_Master(KPAID);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_Scoring_Rules')
BEGIN
    CREATE TABLE KPI_Scoring_Rules (
        RuleID          INT IDENTITY PRIMARY KEY,
        KPIID           INT NULL REFERENCES KPI_Master(KPIID),  -- NULL = global default rule set
        MinAchievement  DECIMAL(9,2) NOT NULL,
        MaxAchievement  DECIMAL(9,2) NOT NULL,
        Score           INT NOT NULL,
        IsActive        BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_ScoringRule_Range CHECK (MinAchievement <= MaxAchievement),
        CONSTRAINT CK_ScoringRule_Score CHECK (Score BETWEEN 1 AND 5)
    );
    CREATE INDEX IX_ScoringRule_KPI ON KPI_Scoring_Rules(KPIID);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Rating_Master')
BEGIN
    CREATE TABLE Rating_Master (
        RatingID    INT IDENTITY PRIMARY KEY,
        RatingLabel VARCHAR(60) NOT NULL,
        MinPercent  DECIMAL(5,2) NOT NULL,
        MaxPercent  DECIMAL(5,2) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_Rating_Range CHECK (MinPercent <= MaxPercent)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Competency_Master')
BEGIN
    CREATE TABLE Competency_Master (
        CompetencyID   INT IDENTITY PRIMARY KEY,
        CompetencyCode VARCHAR(30) NOT NULL UNIQUE,
        CompetencyName VARCHAR(150) NOT NULL,
        Category       VARCHAR(60) NULL,
        Weightage      DECIMAL(5,2) NULL,
        IsActive       BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_Competency_Weightage CHECK (Weightage IS NULL OR (Weightage >= 0 AND Weightage <= 100))
    );
END;
GO

/*
    Note on band non-overlap (KPI_Scoring_Rules, Rating_Master): SQL Server
    CHECK constraints cannot reference other rows, so "no two active bands
    overlap" is enforced at the application layer (app/services/band_validation.py),
    not here. This mirrors the KPI weightage-sums-to-100% rule (Employee_KPA,
    built in M11), which is also cross-row and therefore also enforced in
    the service layer rather than in SQL.
*/
GO
