/*
    Standalone, idempotent add-on for an already-running database: adds
    the nullable Performance_Cycles.Year column used by the new report
    "search by year" filter. CycleName is a free-text unique string (e.g.
    'SAMPLE-2026-27') and isn't reliably parseable, so Year is a real
    column instead - sql/006_create_performance_masters.sql and
    sql/000_FULL_DATABASE_SETUP.sql have also been updated to include it
    in the CREATE TABLE, for anyone setting up fresh.

    USE PMS_DB; GO at the top - see sql/040's fix note for why every
    standalone script needs this.
*/
USE PMS_DB;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('Performance_Cycles') AND name = 'Year'
)
BEGIN
    ALTER TABLE Performance_Cycles ADD Year INT NULL;
END;
GO

-- Best-effort backfill for existing rows whose CycleName happens to start
-- with a 4-digit year (e.g. '2026-27', 'SAMPLE-2026-27' does NOT match
-- this and is left NULL - harmless, it's sample/test data per spec
-- Section 46 and won't be relied on for the year filter in a real deployment).
UPDATE Performance_Cycles
SET Year = TRY_CAST(LEFT(CycleName, 4) AS INT)
WHERE Year IS NULL AND LEFT(CycleName, 4) LIKE '[0-9][0-9][0-9][0-9]';
GO
