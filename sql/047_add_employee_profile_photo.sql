USE PMS_DB;
GO

-- Adds the column backing the profile-photo feature: every employee can
-- upload their own picture (self-service, via /employees/me + the new
-- /employees/{id}/photo endpoints), and HR/Plant Head can set anyone's
-- photo the same way they already edit the rest of an employee's record.
-- Nullable/additive, same convention as every other Employees migration
-- in this folder (003, 046, ...).
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('Employees') AND name = 'ProfilePhotoPath'
)
BEGIN
    ALTER TABLE Employees ADD ProfilePhotoPath VARCHAR(255) NULL;
END;
GO
