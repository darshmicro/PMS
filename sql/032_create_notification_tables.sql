/*
    M23 DDL: Notifications (spec Section 4.5). Run after 031 (Attachments).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Notifications')
BEGIN
    CREATE TABLE Notifications (
        NotificationID  INT IDENTITY PRIMARY KEY,
        EmployeeID      INT NOT NULL REFERENCES Employees(EmployeeID),
        Message         VARCHAR(500) NOT NULL,
        Module          VARCHAR(60) NULL,
        IsRead          BIT NOT NULL DEFAULT 0,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

/*
    Note: rows are created exclusively server-side, by notify_stage_transition()
    firing at the same 11 transition call sites M19's Workflow Engine
    already established across self-assessment/manager review/HOD review/
    HR review/Plant Head/MD Approval - see notification_service.py for the
    full recipient-resolution and retrofit rationale. There is no
    application-level create endpoint.
*/
GO
