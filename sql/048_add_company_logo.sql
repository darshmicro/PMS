USE PMS_DB;
GO

-- Adds the column backing the company-logo feature: HR or Plant Head can
-- upload a logo for a Company (Masters -> Company, same MASTERS.EDIT
-- permission they already hold for every other master field) and it
-- shows in the sidebar branding for anyone in that company. Nullable/
-- additive, same convention as every other Employees/Companies migration
-- in this folder (003, 046, 047, ...).
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('Companies') AND name = 'LogoPath'
)
BEGIN
    ALTER TABLE Companies ADD LogoPath VARCHAR(255) NULL;
END;
GO
