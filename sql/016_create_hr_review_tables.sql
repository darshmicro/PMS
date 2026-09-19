/*
    M15 DDL: HR Review & Calibration (spec Section 11). One row per
    Employee_Performance, like HOD_Reviews (M14). Run after 014 (HOD Review).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'HR_Reviews')
BEGIN
    CREATE TABLE HR_Reviews (
        HRReviewID       INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        HRScore          DECIMAL(6,2) NULL,
        CalibrationAdjustment DECIMAL(6,2) NOT NULL DEFAULT 0,
        AdjustmentReason VARCHAR(500) NULL,
        HRComments       VARCHAR(1000) NULL,
        TrainingRecommendation VARCHAR(500) NULL,
        CareerDevelopmentRecommendation VARCHAR(500) NULL,
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_HRReview_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_HRReview_HRScore CHECK (HRScore IS NULL OR (HRScore BETWEEN 0 AND 100))
    );
END;
GO

/*
    Note: "CalibrationAdjustment <> 0 requires non-empty AdjustmentReason"
    (spec Section 8.6) is a single-row rule in principle, but it depends on
    two columns together (not a fixed threshold), and HRScore's own value
    is *derived* from CalibrationAdjustment plus the sibling HOD_Reviews
    row - both stay in app/services/hr_review_service.py rather than a
    CHECK constraint, consistent with every cross-field/cross-row rule
    since M8.
*/
GO
