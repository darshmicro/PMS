/*
    M22 DDL: Attachments (spec Section 4.5). Run after 029 (PIP).
    EmployeeKPIID and RelatedEmployeeID are both nullable in the DDL -
    "exactly one of the two" is enforced at both layers (defense in
    depth, the same pattern as Development Plan's CompletionStatus and
    PIP's Outcome): the service layer's ensure_exactly_one_target() is
    the primary gate the API always goes through, and the CHECK
    constraint below is the last-resort DB-level backstop against any
    write that bypasses the application (a direct INSERT, a future
    integration, etc).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Attachments')
BEGIN
    CREATE TABLE Attachments (
        AttachmentID    INT IDENTITY PRIMARY KEY,
        EmployeeKPIID   INT NULL REFERENCES Employee_KPI(EmployeeKPIID),
        FileName        VARCHAR(255) NOT NULL,
        StoredPath      VARCHAR(500) NOT NULL,
        UploadedBy      INT NOT NULL REFERENCES Users(UserID),
        UploadedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        RelatedEmployeeID INT NULL REFERENCES Employees(EmployeeID),
        FileVersion     INT NOT NULL DEFAULT 1,
        CONSTRAINT CK_Attachments_ExactlyOneTarget CHECK (
            (CASE WHEN EmployeeKPIID IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN RelatedEmployeeID IS NOT NULL THEN 1 ELSE 0 END) = 1
        )
    );
END;
GO

/*
    Note: unlike every other stage table since M13, there is no
    UniqueConstraint here - a KPI/employee can carry many attachment rows,
    one per (FileName, FileVersion). Re-uploading a file with the same
    FileName against the same target creates a new row with FileVersion+1
    rather than overwriting StoredPath - see the model module's own
    docstring for the full versioning rationale.
*/
GO
