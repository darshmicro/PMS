/*
    M1/M2 scope: Auth + RBAC + minimal Employee + Audit_Log.
    Run against an already-created PMS_DB database.

    NOTE ON EMPLOYEES: only the columns needed for AD-mapping/RBAC are
    created here. Section 4.2's full column set (DepartmentID, SectionID,
    DesignationID, GradeID, PlantID) is added by an ALTER TABLE migration
    in M3/M4 once those master tables exist - see 003_add_org_fk_to_employees.sql
    (to be delivered with M3).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employees')
BEGIN
    CREATE TABLE Employees (
        EmployeeID       INT IDENTITY PRIMARY KEY,
        EmployeeCode     VARCHAR(20) NOT NULL UNIQUE,
        ADUsername       VARCHAR(100) NOT NULL UNIQUE,
        FullName         VARCHAR(150) NOT NULL,
        Email            VARCHAR(150) NULL,
        ManagerID        INT NULL REFERENCES Employees(EmployeeID),
        HODID            INT NULL REFERENCES Employees(EmployeeID),
        EmploymentStatus VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        IsActive         BIT NOT NULL DEFAULT 1,
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL
    );
    CREATE INDEX IX_Employees_Manager ON Employees(ManagerID);
    CREATE INDEX IX_Employees_HOD ON Employees(HODID);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Roles')
BEGIN
    CREATE TABLE Roles (
        RoleID          INT IDENTITY PRIMARY KEY,
        RoleCode        VARCHAR(30)  NOT NULL UNIQUE,
        RoleName        VARCHAR(100) NOT NULL,
        IsBusinessRole  BIT NOT NULL DEFAULT 1,
        IsActive        BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Permissions')
BEGIN
    CREATE TABLE Permissions (
        PermissionID    INT IDENTITY PRIMARY KEY,
        PermissionCode  VARCHAR(60) NOT NULL UNIQUE,
        Module          VARCHAR(60) NOT NULL,
        Description     VARCHAR(255) NULL
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Role_Permissions')
BEGIN
    CREATE TABLE Role_Permissions (
        RoleID          INT NOT NULL REFERENCES Roles(RoleID),
        PermissionID    INT NOT NULL REFERENCES Permissions(PermissionID),
        PRIMARY KEY (RoleID, PermissionID)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
BEGIN
    CREATE TABLE Users (
        UserID          INT IDENTITY PRIMARY KEY,
        ADUsername      VARCHAR(100) NOT NULL UNIQUE,
        EmployeeID      INT NULL REFERENCES Employees(EmployeeID),
        IsActive        BIT NOT NULL DEFAULT 1,
        LastLoginAt     DATETIME2 NULL,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'User_Roles')
BEGIN
    CREATE TABLE User_Roles (
        UserID   INT NOT NULL REFERENCES Users(UserID),
        RoleID   INT NOT NULL REFERENCES Roles(RoleID),
        PRIMARY KEY (UserID, RoleID)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Audit_Log')
BEGIN
    CREATE TABLE Audit_Log (
        AuditID         BIGINT IDENTITY PRIMARY KEY,
        UserID          INT NULL REFERENCES Users(UserID),
        ADUsername      VARCHAR(100) NULL,
        EmployeeID      INT NULL REFERENCES Employees(EmployeeID),
        Action          VARCHAR(30) NOT NULL,
        Module          VARCHAR(60) NOT NULL,
        RecordID        VARCHAR(50) NULL,
        OldValue        NVARCHAR(MAX) NULL,
        NewValue        NVARCHAR(MAX) NULL,
        Reason          VARCHAR(500) NULL,
        ActionedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        IPAddress       VARCHAR(45) NULL
    );
    CREATE INDEX IX_AuditLog_ActionedAt ON Audit_Log(ActionedAt);
    CREATE INDEX IX_AuditLog_Module ON Audit_Log(Module);
END;
GO

/* -----------------------------------------------------------------------
   Least-privilege application login (spec Section 33/34).
   Run the CREATE LOGIN/USER block once per environment; adjust password.
   ----------------------------------------------------------------------- */
-- CREATE LOGIN svc_pms_app WITH PASSWORD = '<set via secure process, not in source control>';
-- CREATE USER svc_pms_app FOR LOGIN svc_pms_app;

-- Normal tables: read/write, no schema changes
-- EXEC sp_addrolemember 'db_datareader', 'svc_pms_app';
-- EXEC sp_addrolemember 'db_datawriter', 'svc_pms_app';

-- Audit_Log: INSERT + SELECT only - explicitly deny UPDATE/DELETE even
-- though db_datawriter would otherwise grant them, so no code path,
-- bug, or compromised session can alter history.
-- GRANT SELECT, INSERT ON Audit_Log TO svc_pms_app;
-- DENY UPDATE, DELETE ON Audit_Log TO svc_pms_app;
GO
