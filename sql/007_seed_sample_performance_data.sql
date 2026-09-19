/*
    SAMPLE / TEST DATA - remove before go-live (spec Section 46), tagged
    'SAMPLE-' throughout. Also seeds the DEFAULT scoring bands and rating
    scale straight from the spec's own worked examples (Sections 12/21) -
    these are real defaults a fresh install needs, not just test filler,
    so they are NOT tagged SAMPLE- and are meant to stay (HR/Plant Head/MD
    can reconfigure them any time through the Scoring Rules / Rating Master
    screens, per spec Section 12 "do not hard-code these rules").
*/

-- ===== Performance Cycle (spec Section 9's own worked example) =====
INSERT INTO Performance_Cycles (
    CycleName, Year, KPISettingStart, KPISettingEnd, SelfAssessmentStart, SelfAssessmentEnd,
    ManagerReviewStart, ManagerReviewEnd, HODReviewStart, HODReviewEnd,
    HRReviewStart, HRReviewEnd, PlantHeadApprovalStart, PlantHeadApprovalEnd,
    MDApprovalStart, MDApprovalEnd, IsActive
)
SELECT 'SAMPLE-2026-27', 2026,
    '2026-04-01', '2026-04-30', '2027-04-01', '2027-04-10',
    '2027-04-11', '2027-04-20', '2027-04-21', '2027-04-25',
    '2027-04-26', '2027-04-30', '2027-05-01', '2027-05-05',
    '2027-05-06', '2027-05-10', 1
WHERE NOT EXISTS (SELECT 1 FROM Performance_Cycles WHERE CycleName = 'SAMPLE-2026-27');
GO

-- ===== Default Rating Scale (spec Section 21's own worked example) =====
INSERT INTO Rating_Master (RatingLabel, MinPercent, MaxPercent, IsActive)
SELECT v.Label, v.MinPct, v.MaxPct, 1
FROM (VALUES
    ('Exceptional',                       90.00, 100.00),
    ('Exceeds Expectations',              80.00, 89.99),
    ('Meets Expectations',                70.00, 79.99),
    ('Partially Meets Expectations',      60.00, 69.99),
    ('Does Not Meet Expectations',         0.00, 59.99)
) AS v(Label, MinPct, MaxPct)
WHERE NOT EXISTS (SELECT 1 FROM Rating_Master WHERE RatingLabel = v.Label);
GO

-- ===== Global Default KPI Scoring Rule set (spec Section 12's own worked example) =====
-- KPIID = NULL -> applies to any KPI without its own KPI-specific rule set.
INSERT INTO KPI_Scoring_Rules (KPIID, MinAchievement, MaxAchievement, Score, IsActive)
SELECT NULL, v.MinAch, v.MaxAch, v.Score, 1
FROM (VALUES
    (110.00, 999.00, 5),
    (105.00, 109.99, 4),
    (100.00, 104.99, 3),
    (90.00,   99.99, 2),
    (0.00,    89.99, 1)
) AS v(MinAch, MaxAch, Score)
WHERE NOT EXISTS (
    SELECT 1 FROM KPI_Scoring_Rules WHERE KPIID IS NULL AND MinAchievement = v.MinAch AND MaxAchievement = v.MaxAch
);
GO

-- ===== Sample KPAs (one per sample department from 004_seed_sample_master_data.sql) =====
INSERT INTO KPA_Master (KPACode, KPAName, Description, DepartmentID, Category, DefaultWeightage, IsActive)
SELECT 'SAMPLE-KPA-PROD-001', 'Production Performance', 'Overall production output and efficiency',
       d.DepartmentID, 'Operational', 20.00, 1
FROM Departments d WHERE d.DeptCode = 'SAMPLE-DPT-PROD'
AND NOT EXISTS (SELECT 1 FROM KPA_Master WHERE KPACode = 'SAMPLE-KPA-PROD-001');

INSERT INTO KPA_Master (KPACode, KPAName, Description, DepartmentID, Category, DefaultWeightage, IsActive)
SELECT 'SAMPLE-KPA-QA-001', 'Quality Assurance Compliance', 'Adherence to GMP and quality standards',
       d.DepartmentID, 'Compliance', 25.00, 1
FROM Departments d WHERE d.DeptCode = 'SAMPLE-DPT-QA'
AND NOT EXISTS (SELECT 1 FROM KPA_Master WHERE KPACode = 'SAMPLE-KPA-QA-001');

INSERT INTO KPA_Master (KPACode, KPAName, Description, DepartmentID, Category, DefaultWeightage, IsActive)
SELECT 'SAMPLE-KPA-GEN-001', 'Process Improvement', 'Contribution to continuous improvement initiatives',
       NULL, 'Cross-functional', 15.00, 1
WHERE NOT EXISTS (SELECT 1 FROM KPA_Master WHERE KPACode = 'SAMPLE-KPA-GEN-001');
GO

-- ===== Sample KPIs under the sample KPAs =====
INSERT INTO KPI_Master (
    KPICode, KPIName, Description, KPAID, DepartmentID, MeasurementType, Unit,
    TargetType, DefaultTarget, MinimumTarget, ExpectedTarget, StretchTarget, Weightage, IsActive
)
SELECT 'SAMPLE-KPI-PROD-001', 'Monthly Production Output', 'Units produced against monthly plan',
       k.KPAID, k.DepartmentID, 'PERCENTAGE', '%', 'HIGHER_IS_BETTER',
       100.00, 90.00, 100.00, 115.00, 60.00, 1
FROM KPA_Master k WHERE k.KPACode = 'SAMPLE-KPA-PROD-001'
AND NOT EXISTS (SELECT 1 FROM KPI_Master WHERE KPICode = 'SAMPLE-KPI-PROD-001');

INSERT INTO KPI_Master (
    KPICode, KPIName, Description, KPAID, DepartmentID, MeasurementType, Unit,
    TargetType, DefaultTarget, MinimumTarget, ExpectedTarget, StretchTarget, Weightage, IsActive
)
SELECT 'SAMPLE-KPI-PROD-002', 'Batch Rejection Rate', 'Percentage of batches rejected in QC',
       k.KPAID, k.DepartmentID, 'REDUCTION', '%', 'LOWER_IS_BETTER',
       2.00, 3.00, 2.00, 1.00, 40.00, 1
FROM KPA_Master k WHERE k.KPACode = 'SAMPLE-KPA-PROD-001'
AND NOT EXISTS (SELECT 1 FROM KPI_Master WHERE KPICode = 'SAMPLE-KPI-PROD-002');

INSERT INTO KPI_Master (
    KPICode, KPIName, Description, KPAID, DepartmentID, MeasurementType, Unit,
    TargetType, DefaultTarget, Weightage, IsActive
)
SELECT 'SAMPLE-KPI-QA-001', 'CAPA Closure On Time', 'Percentage of CAPAs closed within due date',
       k.KPAID, k.DepartmentID, 'PERCENTAGE', '%', 'HIGHER_IS_BETTER', 95.00, 100.00, 1
FROM KPA_Master k WHERE k.KPACode = 'SAMPLE-KPA-QA-001'
AND NOT EXISTS (SELECT 1 FROM KPI_Master WHERE KPICode = 'SAMPLE-KPI-QA-001');

-- SAMPLE-KPA-GEN-001 ("Process Improvement") originally shipped with no
-- KPIs under it at all - every other sample KPA got 1-2 KPIs above, this
-- one got none, so anyone assigning it in the KPA/KPI Assignment screen
-- hit an empty "Add KPI" list with nothing to pick. These two give it the
-- same kind of coverage the other sample KPAs already have.
INSERT INTO KPI_Master (
    KPICode, KPIName, Description, KPAID, DepartmentID, MeasurementType, Unit,
    TargetType, DefaultTarget, Weightage, IsActive
)
SELECT 'SAMPLE-KPI-GEN-001', 'Improvement Ideas Implemented',
       'Number of process improvement ideas raised and implemented during the cycle',
       k.KPAID, k.DepartmentID, 'QTY', 'ideas', 'HIGHER_IS_BETTER', 4.00, 60.00, 1
FROM KPA_Master k WHERE k.KPACode = 'SAMPLE-KPA-GEN-001'
AND NOT EXISTS (SELECT 1 FROM KPI_Master WHERE KPICode = 'SAMPLE-KPI-GEN-001');

INSERT INTO KPI_Master (
    KPICode, KPIName, Description, KPAID, DepartmentID, MeasurementType, Unit,
    TargetType, DefaultTarget, Weightage, IsActive
)
SELECT 'SAMPLE-KPI-GEN-002', 'Cycle Time Reduction',
       'Percentage reduction in process cycle time versus the prior-year baseline',
       k.KPAID, k.DepartmentID, 'REDUCTION', '%', 'LOWER_IS_BETTER', 10.00, 40.00, 1
FROM KPA_Master k WHERE k.KPACode = 'SAMPLE-KPA-GEN-001'
AND NOT EXISTS (SELECT 1 FROM KPI_Master WHERE KPICode = 'SAMPLE-KPI-GEN-002');
GO

-- ===== Sample Competencies (spec Section 14's own list) =====
INSERT INTO Competency_Master (CompetencyCode, CompetencyName, Category, Weightage, IsActive)
SELECT v.Code, v.Name, v.Category, v.Weightage, 1
FROM (VALUES
    ('SAMPLE-COMP-LEAD', 'Leadership', 'Behavioral', 15.00),
    ('SAMPLE-COMP-TEAM', 'Teamwork', 'Behavioral', 10.00),
    ('SAMPLE-COMP-COMM', 'Communication', 'Behavioral', 10.00),
    ('SAMPLE-COMP-DECN', 'Decision Making', 'Behavioral', 10.00),
    ('SAMPLE-COMP-PROB', 'Problem Solving', 'Behavioral', 10.00),
    ('SAMPLE-COMP-OWN',  'Ownership', 'Behavioral', 10.00),
    ('SAMPLE-COMP-INNOV','Innovation', 'Behavioral', 5.00),
    ('SAMPLE-COMP-CUST', 'Customer Focus', 'Behavioral', 5.00),
    ('SAMPLE-COMP-GMP',  'GMP Compliance', 'Technical', 15.00),
    ('SAMPLE-COMP-TECH', 'Technical Knowledge', 'Technical', 10.00)
) AS v(Code, Name, Category, Weightage)
WHERE NOT EXISTS (SELECT 1 FROM Competency_Master WHERE CompetencyCode = v.Code);
GO
