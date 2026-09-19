/*
    M18 DDL: Scoring Engine (spec Section 8). Three tables:

    - Employee_Competency: exists in the design doc's ERD/DDL but was
      never created by any prior module (M10 only built Competency_Master,
      the org-wide list of competencies; no module assigns them to a
      specific Employee_Performance). Created here because Section 8.3's
      formula needs it to exist - see the model's own docstring for why
      this module stops short of building a full assignment workflow
      around it.
    - Performance_Scores: audit trail of computed component/final figures.
    - Performance_Ratings: the rating-band lookup result, inserted once
      per record, only at the FINAL_APPROVED transition, and immutable
      thereafter (spec Section 8.5).

    Run after 021 (MD Approval).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_Competency')
BEGIN
    CREATE TABLE Employee_Competency (
        EmployeeCompetencyID INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        CompetencyID    INT NOT NULL REFERENCES Competency_Master(CompetencyID),
        Weightage       DECIMAL(5,2) NOT NULL,
        Score           INT NULL,   -- 1-5, same scale as KPI scores
        Comments        VARCHAR(1000) NULL,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT CK_EmployeeCompetency_Score CHECK (Score IS NULL OR Score BETWEEN 1 AND 5)
    );
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Performance_Scores')
BEGIN
    CREATE TABLE Performance_Scores (
        ScoreID         INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        EmployeeKPIID   INT NULL REFERENCES Employee_KPI(EmployeeKPIID),
        ScoreType       VARCHAR(20) NOT NULL,   -- KPI_WEIGHTED, COMPETENCY_WEIGHTED, FINAL
        ScoreValue      DECIMAL(9,4) NOT NULL,
        CalculatedAt    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_PerformanceScores_ScoreType CHECK (ScoreType IN ('KPI_WEIGHTED', 'COMPETENCY_WEIGHTED', 'FINAL'))
    );
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Performance_Ratings')
BEGIN
    CREATE TABLE Performance_Ratings (
        PerformanceRatingID INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) UNIQUE,
        FinalScorePct   DECIMAL(6,2) NOT NULL,
        RatingID        INT NOT NULL REFERENCES Rating_Master(RatingID),
        FinalizedAt     DATETIME2 NULL
    );
END;
GO

/*
    Note: "no in-place edit of Performance_Ratings, ever - only a new
    audited reopen workflow event" (spec Section 8.5/4/32) is an
    application-level rule the service layer upholds (run_scoring_engine
    refuses to insert a second row for a PerformanceID); a future "reopen"
    module is where an explicit, audited correction path belongs, not a
    relaxed constraint here.
*/
GO
