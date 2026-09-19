/*
    Standalone, idempotent add-on for an already-running database: the
    "Process Improvement" sample KPA (SAMPLE-KPA-GEN-001, seeded by
    sql/007) shipped with zero KPIs under it, unlike every other sample
    KPA - so the KPA/KPI Assignment screen's "Add KPI" list was empty for
    it. This script only adds the two missing KPIs; it does not touch
    anything else. (sql/007 and sql/000_FULL_DATABASE_SETUP.sql have also
    been updated with the same two inserts, for anyone setting up fresh.)

    USE PMS_DB; GO at the top - see sql/040's fix note for why every
    standalone script needs this.
*/
USE PMS_DB;
GO

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
