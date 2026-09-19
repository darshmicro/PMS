/* =============================================================================
   PMS — FULL DATABASE SETUP (all modules M1–M28)
   -----------------------------------------------------------------------------
   Run this ONE script in SSMS (connected to your SQL Server instance, not yet
   inside a specific database) to create the PMS_DB database and every table,
   role, permission, and default master-data row every module (M1–M28) needs.

   This script is a straight concatenation of sql/001 through sql/039, in
   their original numbered order, wrapped with CREATE DATABASE + USE. Every
   CREATE TABLE / INSERT in it is already idempotent (IF NOT EXISTS / WHERE
   NOT EXISTS guards), so re-running the whole script on an existing database
   is safe and simply does nothing to tables/rows that already exist.

   WHAT'S INCLUDED:
     - 001–003   Auth/RBAC + Org Masters + Employee extension (M1–M4)
     - 004       Sample org master data (Company/Plant/Departments) — tagged
                 'SAMPLE-', safe to leave for a demo/UAT install; DELETE before
                 a real production go-live (see DEPLOYMENT.md §11).
     - 005       M3/M4 permissions
     - 006       Performance Cycle / KPA / KPI / Scoring Rules / Rating /
                 Competency masters (M5–M10 schema)
     - 007       Sample performance cycle + employee data (tagged 'SAMPLE-')
                 AND the real default Scoring Bands / Rating Master rows the
                 app needs to function (NOT sample data — meant to stay, and
                 reconfigurable later via the Scoring Rules/Rating Master
                 screens).
     - 008–039   Every remaining module's tables + seeded permissions, in
                 build order: Assignments, Self-Assessment, Manager/HOD/HR
                 Review, Plant Head Approval, MD Approval, Scoring Engine,
                 Workflow Engine, Development Plans, PIP, Attachments,
                 Notifications, Dashboard, Reports, Audit Log, Performance
                 History, System Configuration (M28).

   WHAT'S DELIBERATELY NOT INCLUDED (run separately, after this script):
     - 040_bootstrap_first_admin.sql — creates your first SYS_ADMIN login.
       Requires editing one line (the real AD username) before running, so
       it is not safe to blindly include here. See DEPLOYMENT.md §6/§11.
     - sql/demo_only/041 + 042 — ONLY for the Windows 11 Home / no-AD local
       demo (AUTH_MODE=demo_local). Do not run these against a real AD-backed
       production database. See DEPLOY_WINDOWS11_HOME_DEMO.md.

   If this is a real production go-live rather than a demo/UAT install,
   remove the two SAMPLE- tagged blocks (004 in full, and the SAMPLE- rows in
   007) after running this script — DEPLOYMENT.md §11 covers exactly what to
   delete.
   ============================================================================= */

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'PMS_DB')
BEGIN
    CREATE DATABASE PMS_DB;
END;
GO

USE PMS_DB;
GO


-- =============================================================================
-- source: sql/001_create_auth_rbac_tables.sql
-- =============================================================================
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

-- Local (non-AD) password table - backs AUTH_MODE=demo_local and
-- AUTH_MODE=hybrid (AD + local users side by side, see sql/041's own
-- header comment and app/services/demo_auth_service.py). Harmless to
-- create even for a pure AD-only deployment; it simply stays empty.
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Demo_Login')
BEGIN
    CREATE TABLE Demo_Login (
        DemoCredentialID INT IDENTITY PRIMARY KEY,
        UserID           INT NOT NULL UNIQUE REFERENCES Users(UserID),
        PasswordHash     VARCHAR(255) NOT NULL,
        UpdatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
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


-- =============================================================================
-- source: sql/002_seed_roles_and_permissions.sql
-- =============================================================================
/*
    Seed data for M1/M2. Idempotent (MERGE-style guards) so it can be
    re-run safely. Extend Permissions as later modules (M11 onward) are built -
    this file seeds only what M1/M2's own admin screens need to function,
    plus placeholders for the module-level permissions referenced by the
    design doc's RBAC matrix so role assignment can start immediately.
*/

-- ===== Roles (spec Section 3) =====
INSERT INTO Roles (RoleCode, RoleName, IsBusinessRole, IsActive)
SELECT v.RoleCode, v.RoleName, v.IsBusinessRole, 1
FROM (VALUES
    ('EMPLOYEE',    'Employee',                 1),
    ('MANAGER',     'Reporting Manager',        1),
    ('HOD',         'Head of Department',       1),
    ('HR',          'HR',                       1),
    ('PLANT_HEAD',  'Plant Head',               1),
    ('MD',          'Managing Director',        1),
    ('HR_ADMIN',    'HR Administrator',         1),
    ('SYS_ADMIN',   'System Administrator',     0)   -- technical only, no business approval rights
) AS v(RoleCode, RoleName, IsBusinessRole)
WHERE NOT EXISTS (SELECT 1 FROM Roles r WHERE r.RoleCode = v.RoleCode);

-- ===== Permissions =====
-- Naming convention: MODULE.ACTION  (ACTION in {VIEW, CREATE, EDIT, APPROVE, RETURN, DEACTIVATE, EXPORT})
INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    -- User/Role administration (M2 itself)
    ('USER_MANAGEMENT.VIEW',   'USER_MANAGEMENT', 'View AD-to-employee-role mappings'),
    ('USER_MANAGEMENT.EDIT',   'USER_MANAGEMENT', 'Create/edit AD-to-employee-role mappings'),
    ('ROLE_PERMISSIONS.VIEW',  'ROLE_PERMISSIONS','View role-permission assignments'),
    ('ROLE_PERMISSIONS.EDIT',  'ROLE_PERMISSIONS','Edit role-permission assignments'),

    -- Self-assessment / review chain (placeholders wired up fully in M12-M17)
    ('SELF_ASSESSMENT.EDIT',       'SELF_ASSESSMENT',   'Employee can edit own self-assessment'),
    ('MANAGER_REVIEW.EDIT',        'MANAGER_REVIEW',    'Manager can score/comment/return'),
    ('HOD_REVIEW.APPROVE',         'HOD_REVIEW',        'HOD can approve/return'),
    ('HR_REVIEW.EDIT',             'HR_REVIEW',         'HR can calibrate/adjust'),
    ('PLANTHEAD_APPROVAL.APPROVE', 'PLANTHEAD_APPROVAL','Plant Head can approve/return'),
    ('MD_APPROVAL.APPROVE',        'MD_APPROVAL',       'MD can approve/return'),

    -- Masters (placeholders wired up fully in M3-M10)
    ('MASTERS.VIEW',   'MASTERS', 'View master data'),
    ('MASTERS.EDIT',   'MASTERS', 'Create/edit master data'),
    ('MASTERS.DEACTIVATE', 'MASTERS', 'Deactivate master records'),

    -- Audit / export (placeholders for M25/M26)
    ('AUDIT_LOG.VIEW', 'AUDIT_LOG', 'View audit trail, scope depends on role'),
    ('EXPORT.ANY',      'EXPORT',   'Export data at any workflow stage, scope depends on role')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);

-- ===== Role -> Permission wiring for M1/M2's own screens =====
-- HR_ADMIN and SYS_ADMIN administer users/roles; SYS_ADMIN's rights stop at
-- the technical layer (no business approval permissions granted here).
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN (
    'USER_MANAGEMENT.VIEW', 'USER_MANAGEMENT.EDIT',
    'ROLE_PERMISSIONS.VIEW', 'ROLE_PERMISSIONS.EDIT'
)
WHERE r.RoleCode IN ('HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (
      SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID
  );

-- Plant Head and MD get full business-level view rights on user/role admin
-- (view only here; they are not the ones maintaining the mapping day-to-day - Sec 4).
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('USER_MANAGEMENT.VIEW', 'ROLE_PERMISSIONS.VIEW')
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD')
  AND NOT EXISTS (
      SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID
  );
GO


-- =============================================================================
-- source: sql/003_create_org_masters_and_extend_employees.sql
-- =============================================================================
/*
    M3 (Org Masters) + M4 (Employee Master) DDL.
    Run after 001_create_auth_rbac_tables.sql (Employees must already exist).
    All ALTER TABLE statements on Employees are additive/nullable - no
    existing column is renamed or dropped, so M1/M2 data and code keep
    working unchanged (see README_M1_M2.md's forward note).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Companies')
BEGIN
    CREATE TABLE Companies (
        CompanyID   INT IDENTITY PRIMARY KEY,
        CompanyCode VARCHAR(20) NOT NULL UNIQUE,
        CompanyName VARCHAR(150) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1,
        LogoPath    VARCHAR(255) NULL
    );
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Companies') AND name = 'LogoPath')
BEGIN
    ALTER TABLE Companies ADD LogoPath VARCHAR(255) NULL;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Plants')
BEGIN
    CREATE TABLE Plants (
        PlantID     INT IDENTITY PRIMARY KEY,
        CompanyID   INT NOT NULL REFERENCES Companies(CompanyID),
        PlantCode   VARCHAR(20) NOT NULL UNIQUE,
        PlantName   VARCHAR(150) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Departments')
BEGIN
    CREATE TABLE Departments (
        DepartmentID INT IDENTITY PRIMARY KEY,
        PlantID      INT NOT NULL REFERENCES Plants(PlantID),
        DeptCode     VARCHAR(20) NOT NULL UNIQUE,
        DeptName     VARCHAR(150) NOT NULL,
        IsActive     BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Sections')
BEGIN
    CREATE TABLE Sections (
        SectionID    INT IDENTITY PRIMARY KEY,
        DepartmentID INT NOT NULL REFERENCES Departments(DepartmentID),
        SectionCode  VARCHAR(20) NOT NULL UNIQUE,
        SectionName  VARCHAR(150) NOT NULL,
        IsActive     BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Designations')
BEGIN
    CREATE TABLE Designations (
        DesignationID   INT IDENTITY PRIMARY KEY,
        DesignationCode VARCHAR(20) NOT NULL UNIQUE,
        DesignationName VARCHAR(150) NOT NULL,
        IsActive        BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Grades')
BEGIN
    CREATE TABLE Grades (
        GradeID   INT IDENTITY PRIMARY KEY,
        GradeCode VARCHAR(20) NOT NULL UNIQUE,
        GradeName VARCHAR(100) NOT NULL,
        IsActive  BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_Categories')
BEGIN
    CREATE TABLE Employee_Categories (
        EmployeeCategoryID INT IDENTITY PRIMARY KEY,
        CategoryCode       VARCHAR(20) NOT NULL UNIQUE,
        CategoryName       VARCHAR(100) NOT NULL,
        IsActive           BIT NOT NULL DEFAULT 1
    );
END;
GO

/* -----------------------------------------------------------------------
   M4: extend Employees additively now that the master tables above exist.
   ----------------------------------------------------------------------- */
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DepartmentID')
BEGIN
    ALTER TABLE Employees ADD DepartmentID INT NULL REFERENCES Departments(DepartmentID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'SectionID')
BEGIN
    ALTER TABLE Employees ADD SectionID INT NULL REFERENCES Sections(SectionID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DesignationID')
BEGIN
    ALTER TABLE Employees ADD DesignationID INT NULL REFERENCES Designations(DesignationID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'GradeID')
BEGIN
    ALTER TABLE Employees ADD GradeID INT NULL REFERENCES Grades(GradeID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'PlantID')
BEGIN
    ALTER TABLE Employees ADD PlantID INT NULL REFERENCES Plants(PlantID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'EmployeeCategoryID')
BEGIN
    ALTER TABLE Employees ADD EmployeeCategoryID INT NULL REFERENCES Employee_Categories(EmployeeCategoryID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DateOfJoining')
BEGIN
    ALTER TABLE Employees ADD DateOfJoining DATE NULL;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'HRID')
BEGIN
    ALTER TABLE Employees ADD HRID INT NULL REFERENCES Employees(EmployeeID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'ProfilePhotoPath')
BEGIN
    ALTER TABLE Employees ADD ProfilePhotoPath VARCHAR(255) NULL;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Employees_Department')
BEGIN
    CREATE INDEX IX_Employees_Department ON Employees(DepartmentID);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Employees_Plant')
BEGIN
    CREATE INDEX IX_Employees_Plant ON Employees(PlantID);
END;
GO


-- =============================================================================
-- source: sql/004_seed_sample_master_data.sql
-- =============================================================================
/*
    SAMPLE / TEST DATA - remove before go-live (spec Section 46).
    Every row below is tagged with code prefix 'SAMPLE-' or drawn from the
    department list the spec names, so it's easy to identify and purge.
*/

INSERT INTO Companies (CompanyCode, CompanyName, IsActive)
SELECT 'SAMPLE-CO1', 'Sample Biologics Ltd', 1
WHERE NOT EXISTS (SELECT 1 FROM Companies WHERE CompanyCode = 'SAMPLE-CO1');

INSERT INTO Plants (CompanyID, PlantCode, PlantName, IsActive)
SELECT c.CompanyID, 'SAMPLE-PLT1', 'Sample Plant - Unit 1', 1
FROM Companies c WHERE c.CompanyCode = 'SAMPLE-CO1'
AND NOT EXISTS (SELECT 1 FROM Plants WHERE PlantCode = 'SAMPLE-PLT1');

INSERT INTO Departments (PlantID, DeptCode, DeptName, IsActive)
SELECT p.PlantID, v.DeptCode, v.DeptName, 1
FROM Plants p
CROSS JOIN (VALUES
    ('SAMPLE-DPT-PROD', 'Production'),
    ('SAMPLE-DPT-QA',   'Quality Assurance'),
    ('SAMPLE-DPT-QC',   'Quality Control'),
    ('SAMPLE-DPT-ENG',  'Engineering'),
    ('SAMPLE-DPT-WH',   'Warehouse'),
    ('SAMPLE-DPT-RND',  'R&D'),
    ('SAMPLE-DPT-RA',   'Regulatory Affairs'),
    ('SAMPLE-DPT-MICRO','Microbiology'),
    ('SAMPLE-DPT-HR',   'HR'),
    ('SAMPLE-DPT-FIN',  'Finance'),
    ('SAMPLE-DPT-COMM', 'Commercial'),
    ('SAMPLE-DPT-IT',   'IT')
) AS v(DeptCode, DeptName)
WHERE p.PlantCode = 'SAMPLE-PLT1'
AND NOT EXISTS (SELECT 1 FROM Departments WHERE DeptCode = v.DeptCode);

INSERT INTO Designations (DesignationCode, DesignationName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES
    ('SAMPLE-DSG-EXEC', 'Executive'),
    ('SAMPLE-DSG-SR',   'Senior Executive'),
    ('SAMPLE-DSG-MGR',  'Manager'),
    ('SAMPLE-DSG-SRMGR','Senior Manager'),
    ('SAMPLE-DSG-HOD',  'Head of Department'),
    ('SAMPLE-DSG-PH',   'Plant Head'),
    ('SAMPLE-DSG-MD',   'Managing Director')
) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Designations WHERE DesignationCode = v.Code);

INSERT INTO Grades (GradeCode, GradeName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES ('SAMPLE-G1','Grade 1'), ('SAMPLE-G2','Grade 2'), ('SAMPLE-G3','Grade 3'), ('SAMPLE-G4','Grade 4')) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Grades WHERE GradeCode = v.Code);

INSERT INTO Employee_Categories (CategoryCode, CategoryName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES ('SAMPLE-PERM','Permanent'), ('SAMPLE-CONT','Contract'), ('SAMPLE-PROB','Probation')) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Employee_Categories WHERE CategoryCode = v.Code);
GO


-- =============================================================================
-- source: sql/005_seed_m3_m4_permissions.sql
-- =============================================================================
/*
    M3/M4 permission wiring. MASTERS.VIEW/EDIT/DEACTIVATE already exist
    from 002_seed_roles_and_permissions.sql but were not yet assigned to
    any role - this file assigns them, and adds the new EMPLOYEE_MASTER.*
    permissions, exactly per the Role-Permission Matrix in the design doc.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('EMPLOYEE_MASTER.VIEW',       'EMPLOYEE_MASTER', 'View employee records (scope depends on role)'),
    ('EMPLOYEE_MASTER.EDIT',       'EMPLOYEE_MASTER', 'Create/edit employee records'),
    ('EMPLOYEE_MASTER.DEACTIVATE', 'EMPLOYEE_MASTER', 'Deactivate employee records')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MASTERS.VIEW: everyone (Employee, Manager, HOD, HR, Plant Head, MD, HR Admin) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MASTERS.EDIT: HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.EDIT'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MASTERS.DEACTIVATE: Plant Head, MD, HR Admin only (per matrix, HR has C,V,E but not Deact) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MASTERS.DEACTIVATE'
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== EMPLOYEE_MASTER.VIEW: everyone (scope narrowed in the app layer, not here) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'EMPLOYEE_MASTER.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== EMPLOYEE_MASTER.EDIT / DEACTIVATE: HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('EMPLOYEE_MASTER.EDIT', 'EMPLOYEE_MASTER.DEACTIVATE')
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/006_create_performance_masters.sql
-- =============================================================================
/*
    M5-M10 DDL: Performance Cycle, KPA, KPI, KPI Scoring Rules, Rating,
    Competency masters. Run after 003 (Org Masters + Employee extension) -
    KPA_Master and KPI_Master reference Departments/Designations.
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Performance_Cycles')
BEGIN
    CREATE TABLE Performance_Cycles (
        CycleID                 INT IDENTITY PRIMARY KEY,
        CycleName                VARCHAR(50) NOT NULL UNIQUE,
        Year                     INT NULL,
        KPISettingStart          DATE NULL, KPISettingEnd DATE NULL,
        SelfAssessmentStart      DATE NULL, SelfAssessmentEnd DATE NULL,
        ManagerReviewStart       DATE NULL, ManagerReviewEnd DATE NULL,
        HODReviewStart           DATE NULL, HODReviewEnd DATE NULL,
        HRReviewStart            DATE NULL, HRReviewEnd DATE NULL,
        PlantHeadApprovalStart   DATE NULL, PlantHeadApprovalEnd DATE NULL,
        MDApprovalStart          DATE NULL, MDApprovalEnd DATE NULL,
        IsActive                 BIT NOT NULL DEFAULT 1,
        CreatedAt                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPA_Master')
BEGIN
    CREATE TABLE KPA_Master (
        KPAID            INT IDENTITY PRIMARY KEY,
        KPACode          VARCHAR(30) NOT NULL UNIQUE,
        KPAName          VARCHAR(150) NOT NULL,
        Description      VARCHAR(500) NULL,
        DepartmentID     INT NULL REFERENCES Departments(DepartmentID),
        DesignationID    INT NULL REFERENCES Designations(DesignationID),
        Category         VARCHAR(60) NULL,
        DefaultWeightage DECIMAL(5,2) NULL,
        EffectiveFrom    DATE NULL,
        EffectiveTo      DATE NULL,
        IsActive         BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_KPA_Weightage CHECK (DefaultWeightage IS NULL OR (DefaultWeightage >= 0 AND DefaultWeightage <= 100))
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_Master')
BEGIN
    CREATE TABLE KPI_Master (
        KPIID            INT IDENTITY PRIMARY KEY,
        KPICode          VARCHAR(30) NOT NULL UNIQUE,
        KPIName          VARCHAR(150) NOT NULL,
        Description      VARCHAR(500) NULL,
        KPAID            INT NOT NULL REFERENCES KPA_Master(KPAID),
        DepartmentID     INT NULL REFERENCES Departments(DepartmentID),
        DesignationID    INT NULL REFERENCES Designations(DesignationID),
        MeasurementType  VARCHAR(30) NOT NULL,
        Unit             VARCHAR(30) NULL,
        TargetType       VARCHAR(20) NULL,
        DefaultTarget    DECIMAL(18,4) NULL,
        MinimumTarget    DECIMAL(18,4) NULL,
        ExpectedTarget   DECIMAL(18,4) NULL,
        StretchTarget    DECIMAL(18,4) NULL,
        Weightage        DECIMAL(5,2) NULL,
        ScoringMethod    VARCHAR(30) NULL,
        IsActive         BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_KPI_Weightage CHECK (Weightage IS NULL OR (Weightage >= 0 AND Weightage <= 100)),
        CONSTRAINT CK_KPI_MeasurementType CHECK (MeasurementType IN (
            'NUMERIC','PERCENTAGE','RATIO','YESNO','DATE','MILESTONE','QTY','COST','REDUCTION','QUALITATIVE'
        ))
    );
    CREATE INDEX IX_KPI_KPA ON KPI_Master(KPAID);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_Scoring_Rules')
BEGIN
    CREATE TABLE KPI_Scoring_Rules (
        RuleID          INT IDENTITY PRIMARY KEY,
        KPIID           INT NULL REFERENCES KPI_Master(KPIID),  -- NULL = global default rule set
        MinAchievement  DECIMAL(9,2) NOT NULL,
        MaxAchievement  DECIMAL(9,2) NOT NULL,
        Score           INT NOT NULL,
        IsActive        BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_ScoringRule_Range CHECK (MinAchievement <= MaxAchievement),
        CONSTRAINT CK_ScoringRule_Score CHECK (Score BETWEEN 1 AND 5)
    );
    CREATE INDEX IX_ScoringRule_KPI ON KPI_Scoring_Rules(KPIID);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Rating_Master')
BEGIN
    CREATE TABLE Rating_Master (
        RatingID    INT IDENTITY PRIMARY KEY,
        RatingLabel VARCHAR(60) NOT NULL,
        MinPercent  DECIMAL(5,2) NOT NULL,
        MaxPercent  DECIMAL(5,2) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_Rating_Range CHECK (MinPercent <= MaxPercent)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Competency_Master')
BEGIN
    CREATE TABLE Competency_Master (
        CompetencyID   INT IDENTITY PRIMARY KEY,
        CompetencyCode VARCHAR(30) NOT NULL UNIQUE,
        CompetencyName VARCHAR(150) NOT NULL,
        Category       VARCHAR(60) NULL,
        Weightage      DECIMAL(5,2) NULL,
        IsActive       BIT NOT NULL DEFAULT 1,
        CONSTRAINT CK_Competency_Weightage CHECK (Weightage IS NULL OR (Weightage >= 0 AND Weightage <= 100))
    );
END;
GO

/*
    Note on band non-overlap (KPI_Scoring_Rules, Rating_Master): SQL Server
    CHECK constraints cannot reference other rows, so "no two active bands
    overlap" is enforced at the application layer (app/services/band_validation.py),
    not here. This mirrors the KPI weightage-sums-to-100% rule (Employee_KPA,
    built in M11), which is also cross-row and therefore also enforced in
    the service layer rather than in SQL.
*/
GO


-- =============================================================================
-- source: sql/007_seed_sample_performance_data.sql
-- =============================================================================
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


-- =============================================================================
-- source: sql/008_create_assignment_tables.sql
-- =============================================================================
/*
    M11 DDL: KPA/KPI Assignment (spec Section 10). Employee_Performance is
    the appraisal "envelope" for one (employee, cycle) pair that every
    later module (M12 Self-Assessment onward) attaches to via PerformanceID.
    Run after 006 (Performance Masters) and 003 (Employees).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_Performance')
BEGIN
    CREATE TABLE Employee_Performance (
        PerformanceID   INT IDENTITY PRIMARY KEY,
        EmployeeID      INT NOT NULL REFERENCES Employees(EmployeeID),
        CycleID         INT NOT NULL REFERENCES Performance_Cycles(CycleID),
        Status          VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
        TotalWeightage  DECIMAL(5,2) NOT NULL DEFAULT 0,
        FinalScorePct   DECIMAL(6,2) NULL,
        FinalRatingID   INT NULL REFERENCES Rating_Master(RatingID),
        IsLocked        BIT NOT NULL DEFAULT 0,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT UQ_EmployeePerformance_Employee_Cycle UNIQUE (EmployeeID, CycleID)
    );
    CREATE INDEX IX_EmployeePerformance_Employee ON Employee_Performance(EmployeeID);
    CREATE INDEX IX_EmployeePerformance_Cycle ON Employee_Performance(CycleID);
    CREATE INDEX IX_EmployeePerformance_Status ON Employee_Performance(Status);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_KPA')
BEGIN
    CREATE TABLE Employee_KPA (
        EmployeeKPAID   INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        KPAID           INT NOT NULL REFERENCES KPA_Master(KPAID),
        -- Read-only rollup (sum of this KPA's own Employee_KPI rows),
        -- recomputed by the application after every KPI add/edit/remove -
        -- see app/services/assignment_service.py::recompute_rollups.
        Weightage       DECIMAL(5,2) NOT NULL DEFAULT 0,
        CONSTRAINT UQ_EmployeeKPA_Performance_KPA UNIQUE (PerformanceID, KPAID)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_KPI')
BEGIN
    CREATE TABLE Employee_KPI (
        EmployeeKPIID    INT IDENTITY PRIMARY KEY,
        EmployeeKPAID    INT NOT NULL REFERENCES Employee_KPA(EmployeeKPAID) ON DELETE CASCADE,
        KPIID            INT NOT NULL REFERENCES KPI_Master(KPIID),
        Description      VARCHAR(500) NULL,
        Target           DECIMAL(18,4) NULL,
        Unit             VARCHAR(30) NULL,
        -- Snapshot of KPI_Master.MeasurementType at assignment time - see
        -- the model docstring for why this is copied rather than read live.
        MeasurementType  VARCHAR(30) NOT NULL,
        Weightage        DECIMAL(5,2) NOT NULL,
        DueDate          DATE NULL,
        EvidenceRequired BIT NOT NULL DEFAULT 0,
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_EmployeeKPI_EmployeeKPA_KPI UNIQUE (EmployeeKPAID, KPIID),
        CONSTRAINT CK_EmployeeKPI_Weightage CHECK (Weightage > 0 AND Weightage <= 100)
    );
    CREATE INDEX IX_EmployeeKPI_KPI ON Employee_KPI(KPIID);
END;
GO

/*
    Note: SQL Server CHECK constraints can enforce a single row's weightage
    bounds (0 < Weightage <= 100, above) but cannot enforce the cross-row
    "duplicate KPI across the whole appraisal" or "total weightage = 100%
    before submission" rules - those need to see every sibling row and are
    enforced in app/services/assignment_service.py, exactly as the
    KPI-Scoring-Rule / Rating-Master band-overlap rules are in M8/M9.
*/
GO


-- =============================================================================
-- source: sql/009_seed_assignment_permissions.sql
-- =============================================================================
/*
    M11 permission wiring. ASSIGNMENT.VIEW/EDIT are new permission codes
    (unlike M5-M10, which reused the generic MASTERS.* codes) because
    assignment visibility and edit rights follow the record-scoped
    Manager/HOD/broad-role pattern from the Employee Master (M4), not the
    flat "everyone views, HR+ edits" pattern the org/performance masters use.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ASSIGNMENT.VIEW', 'KPA_KPI_ASSIGNMENT', 'View KPA/KPI assignments (scope depends on role)'),
    ('ASSIGNMENT.EDIT', 'KPA_KPI_ASSIGNMENT', 'Create/edit/submit KPA/KPI assignments (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== ASSIGNMENT.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== ASSIGNMENT.EDIT: Manager, HR, Plant Head, MD, HR Admin =====
-- (spec Section 10: "Manager/HR can assign KPAs and KPIs to employees";
--  Section 4 gives Plant Head/MD full business-level admin rights, and
--  HR Admin administers on HR's behalf. HOD is view-only here - HOD's
--  own authority begins at the review stage, M17.)
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/010_create_self_assessment_tables.sql
-- =============================================================================
/*
    M12 DDL: Employee Self-Assessment (spec Section 11). One row per
    Employee_KPI, seeded when the employee acknowledges their KPI
    assignment (Employee_Performance.Status: KPI_ASSIGNED ->
    EMPLOYEE_ACKNOWLEDGED). Run after 008 (KPA/KPI Assignment).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Self_Assessments')
BEGIN
    CREATE TABLE Self_Assessments (
        SelfAssessmentID INT IDENTITY PRIMARY KEY,
        EmployeeKPIID    INT NOT NULL REFERENCES Employee_KPI(EmployeeKPIID) ON DELETE CASCADE,
        Achievement      DECIMAL(18,4) NULL,
        AchievementPct   DECIMAL(9,2) NULL,
        SelfScore        INT NULL,
        EmployeeComments VARCHAR(1000) NULL,
        DevelopmentNeed  VARCHAR(500) NULL,
        Status           VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT, SUBMITTED, RETURNED
        SubmittedAt      DATETIME2 NULL,
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_SelfAssessment_EmployeeKPI UNIQUE (EmployeeKPIID),
        CONSTRAINT CK_SelfAssessment_SelfScore CHECK (SelfScore IS NULL OR (SelfScore BETWEEN 1 AND 5))
    );
    CREATE INDEX IX_SelfAssessment_Status ON Self_Assessments(Status);
END;
GO

/*
    Note: as with Employee_KPI's weightage-sums-to-100% rule (M11), the
    "every assigned KPI must be assessed before submission" rule needs to
    see every sibling row for the whole Employee_Performance record and
    cannot be a single-table CHECK constraint - it is enforced in
    app/services/self_assessment_service.py::validate_submission_ready.
*/
GO


-- =============================================================================
-- source: sql/011_seed_self_assessment_permissions.sql
-- =============================================================================
/*
    M12 permission wiring. SELF_ASSESSMENT.EDIT is granted to EMPLOYEE only
    (per the RBAC matrix's "Own Self-Assessment: C,V,E (until submit)" row -
    Manager/HOD/HR/Plant Head/MD/HR Administrator get View only, never
    Edit, unlike KPA/KPI Assignment's ASSIGNMENT.EDIT in M11). The route
    layer additionally enforces that even an EMPLOYEE-role holder can only
    edit their OWN record (self_assessment_service.ensure_own_record) -
    this permission grant alone does not scope by employee.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SELF_ASSESSMENT.VIEW', 'SELF_ASSESSMENT', 'View self-assessments (scope depends on role)'),
    ('SELF_ASSESSMENT.EDIT', 'SELF_ASSESSMENT', 'Create/edit/submit own self-assessment (employee only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SELF_ASSESSMENT.VIEW: everyone in the review chain =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SELF_ASSESSMENT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== SELF_ASSESSMENT.EDIT: Employee only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SELF_ASSESSMENT.EDIT'
WHERE r.RoleCode = 'EMPLOYEE'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/012_create_manager_review_tables.sql
-- =============================================================================
/*
    M13 DDL: Manager Review (spec Section 11). One row per Employee_KPI,
    created lazily on the manager's first edit (no separate "acknowledge"
    step exists for this stage - see the model docstring). Run after 010
    (Self-Assessment).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Manager_Reviews')
BEGIN
    CREATE TABLE Manager_Reviews (
        ManagerReviewID  INT IDENTITY PRIMARY KEY,
        EmployeeKPIID    INT NOT NULL REFERENCES Employee_KPI(EmployeeKPIID) ON DELETE CASCADE,
        ManagerScore     INT NULL,
        ManagerComments  VARCHAR(1000) NULL,
        DevelopmentRequirement VARCHAR(500) NULL,
        Action           VARCHAR(20) NULL,  -- SUBMIT, RETURN
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_ManagerReview_EmployeeKPI UNIQUE (EmployeeKPIID),
        CONSTRAINT CK_ManagerReview_ManagerScore CHECK (ManagerScore IS NULL OR (ManagerScore BETWEEN 1 AND 5)),
        CONSTRAINT CK_ManagerReview_Action CHECK (Action IS NULL OR Action IN ('SUBMIT', 'RETURN'))
    );
    CREATE INDEX IX_ManagerReview_Action ON Manager_Reviews(Action);
END;
GO

/*
    Note: as with Self_Assessments (M12), the cross-row "every KPI scored
    before submission" rule and the "override requires comments" rule need
    to see sibling rows and/or the linked Self_Assessment row, so they stay
    in app/services/manager_review_service.py rather than a CHECK constraint.
*/
GO


-- =============================================================================
-- source: sql/013_seed_manager_review_permissions.sql
-- =============================================================================
/*
    M13 permission wiring. MANAGER_REVIEW.EDIT is granted to MANAGER only -
    per the RBAC matrix's "Manager Review: C,V,E,R" row, HOD/HR/Plant
    Head/MD/HR Administrator get View only here, despite Plant Head/MD's
    broader business-admin rights elsewhere (their own edit rights begin at
    HOD Review onward, M14+). The route layer additionally enforces that
    even a MANAGER-role holder can only edit reviews for their OWN direct
    reports (manager_review_service.ensure_is_reviewing_manager).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('MANAGER_REVIEW.VIEW', 'MANAGER_REVIEW', 'View manager reviews (scope depends on role)'),
    ('MANAGER_REVIEW.EDIT', 'MANAGER_REVIEW', 'Score/comment, submit, or return a manager review (own reports only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MANAGER_REVIEW.VIEW: everyone in the review chain =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MANAGER_REVIEW.VIEW'
WHERE r.RoleCode IN ('MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MANAGER_REVIEW.EDIT: Manager only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MANAGER_REVIEW.EDIT'
WHERE r.RoleCode = 'MANAGER'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/014_create_hod_review_tables.sql
-- =============================================================================
/*
    M14 DDL: HOD Review (spec Section 11). One row per Employee_Performance
    (not per-KPI, unlike Self_Assessments/Manager_Reviews - see the model
    docstring for why). Run after 012 (Manager Review).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'HOD_Reviews')
BEGIN
    CREATE TABLE HOD_Reviews (
        HODReviewID      INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        HODScore         DECIMAL(6,2) NULL,
        HODComments      VARCHAR(1000) NULL,
        DevelopmentRecommendation VARCHAR(500) NULL,
        TrainingRequirement VARCHAR(500) NULL,
        Action           VARCHAR(20) NULL,  -- APPROVE_FORWARD, RETURN_TO_MANAGER, RETURN_TO_EMPLOYEE
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_HODReview_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_HODReview_HODScore CHECK (HODScore IS NULL OR (HODScore BETWEEN 0 AND 100)),
        CONSTRAINT CK_HODReview_Action CHECK (Action IS NULL OR Action IN ('APPROVE_FORWARD', 'RETURN_TO_MANAGER', 'RETURN_TO_EMPLOYEE'))
    );
    CREATE INDEX IX_HODReview_Action ON HOD_Reviews(Action);
END;
GO

/*
    Note: the "HOD score differs from the manager-weighted reference
    without comments" rule needs to compute that reference from every
    sibling Manager_Review row, so - like every cross-row rule before it
    since M8 - it stays in app/services/hod_review_service.py rather than
    a CHECK constraint.
*/
GO


-- =============================================================================
-- source: sql/015_seed_hod_review_permissions.sql
-- =============================================================================
/*
    M14 permission wiring. Notably, unlike every previous review-stage
    module (Assignment, Self-Assessment, Manager Review), the RBAC matrix's
    HOD Review row grants EMPLOYEE and MANAGER no access at all - not even
    View - so neither role appears in either grant below. HOD_REVIEW.EDIT
    is HOD-only; the route layer further restricts it to the employee's
    own HOD (hod_review_service.ensure_is_reviewing_hod).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('HOD_REVIEW.VIEW', 'HOD_REVIEW', 'View HOD reviews (scope depends on role)'),
    ('HOD_REVIEW.EDIT', 'HOD_REVIEW', 'Score/comment, approve & forward, or return an HOD review (own department only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== HOD_REVIEW.VIEW: HOD + broad business-admin roles only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HOD_REVIEW.VIEW'
WHERE r.RoleCode IN ('HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== HOD_REVIEW.EDIT: HOD only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HOD_REVIEW.EDIT'
WHERE r.RoleCode = 'HOD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/016_create_hr_review_tables.sql
-- =============================================================================
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


-- =============================================================================
-- source: sql/017_seed_hr_review_permissions.sql
-- =============================================================================
/*
    M15 permission wiring. HR_REVIEW.EDIT is HR-only - per the RBAC
    matrix's "HR Review/Calibration: C,V,E" row, even HR Administrator,
    Plant Head and MD get View only here, matching HOD Review's pattern of
    Edit belonging to exactly one role at each stage. Employee, Manager and
    HOD get no access at all, same as HOD Review.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('HR_REVIEW.VIEW', 'HR_REVIEW', 'View HR reviews/calibration'),
    ('HR_REVIEW.EDIT', 'HR_REVIEW', 'Record calibration adjustment and complete HR Review (HR only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== HR_REVIEW.VIEW: HR + broad business-admin roles =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HR_REVIEW.VIEW'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== HR_REVIEW.EDIT: HR only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'HR_REVIEW.EDIT'
WHERE r.RoleCode = 'HR'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/018_create_plant_head_approval_tables.sql
-- =============================================================================
/*
    M16 DDL: Plant Head Approval (spec Section 11). Unlike HOD_Reviews
    (M14) and HR_Reviews (M15), this table has no score column at all -
    Plant Head does not re-score the record, they approve or return it
    based on the HR-calibrated score that already exists. One row per
    Employee_Performance, reused across repeated approve/return cycles.
    Run after 017 (HR Review).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PlantHead_Approvals')
BEGIN
    CREATE TABLE PlantHead_Approvals (
        ApprovalID       INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        Decision         VARCHAR(20) NULL,   -- APPROVE, RETURN
        Comments         VARCHAR(1000) NULL,
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_PlantHeadApproval_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_PlantHeadApproval_Decision CHECK (Decision IS NULL OR Decision IN ('APPROVE', 'RETURN'))
    );
END;
GO

/*
    Note: "a RETURN decision requires non-empty Comments" (mirroring the
    mandatory-reason rule for every return action since M13) depends on
    two columns together, so - consistent with every cross-field rule
    since M8 - it stays in app/services/plant_head_approval_service.py
    rather than a CHECK constraint.
*/
GO


-- =============================================================================
-- source: sql/019_seed_plant_head_approval_permissions.sql
-- =============================================================================
/*
    M16 permission wiring. Per the RBAC matrix's "Plant Head Approval:
    C,V,A,R" row, Plant Head alone gets edit rights (approve/return) -
    there is no separate EDIT-vs-Approve/Return distinction, so
    PLANT_HEAD_APPROVAL.EDIT is used to gate both the /approve and
    /return actions, matching HOD_REVIEW.EDIT's role in M14. MD and HR
    Administrator get View only; Employee, Manager, HOD and HR get no
    access at all to this stage.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PLANT_HEAD_APPROVAL.VIEW', 'PLANT_HEAD_APPROVAL', 'View Plant Head Approval records'),
    ('PLANT_HEAD_APPROVAL.EDIT', 'PLANT_HEAD_APPROVAL', 'Approve or return a record at Plant Head Approval (Plant Head only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PLANT_HEAD_APPROVAL.VIEW: Plant Head + broad business-admin roles =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PLANT_HEAD_APPROVAL.VIEW'
WHERE r.RoleCode IN ('PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== PLANT_HEAD_APPROVAL.EDIT: Plant Head only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PLANT_HEAD_APPROVAL.EDIT'
WHERE r.RoleCode = 'PLANT_HEAD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/020_create_md_approval_tables.sql
-- =============================================================================
/*
    M17 DDL: MD Final Approval (spec Section 11). Structurally identical
    to PlantHead_Approvals (M16) - no score column, MD approves/returns
    the record as a whole. One row per Employee_Performance, reused
    across repeated approve/return cycles. Run after 019 (Plant Head
    Approval).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'MD_Approvals')
BEGIN
    CREATE TABLE MD_Approvals (
        ApprovalID       INT IDENTITY PRIMARY KEY,
        PerformanceID    INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        Decision         VARCHAR(20) NULL,   -- APPROVE, RETURN
        Comments         VARCHAR(1000) NULL,
        ActionedAt       DATETIME2 NULL,
        ActionedBy       INT NULL REFERENCES Users(UserID),
        CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt        DATETIME2 NULL,
        CONSTRAINT UQ_MDApproval_Performance UNIQUE (PerformanceID),
        CONSTRAINT CK_MDApproval_Decision CHECK (Decision IS NULL OR Decision IN ('APPROVE', 'RETURN'))
    );
END;
GO

/*
    Note: the "return requires non-empty Comments" rule (mirroring every
    return action since M13) stays in app/services/md_approval_service.py,
    not a CHECK constraint, for the same reason as M16's identical rule -
    a CHECK constraint can't express "required only for this action".

    Also note: Employee_Performance.IsLocked is set to 1 by this module's
    /approve endpoint (app/services/md_approval_service.finalize_and_lock),
    modelling the workflow diagram's actor-less "FINAL_APPROVED -> LOCKED:
    System locks record" arrow as an immediate consequence of approval
    rather than a distinct stage/table of its own.
*/
GO


-- =============================================================================
-- source: sql/021_seed_md_approval_permissions.sql
-- =============================================================================
/*
    M17 permission wiring. The RBAC matrix's "MD Approval: C,V,A,R" row is
    the narrowest yet - MD alone gets create/view/approve/return rights,
    and only HR Administrator gets View alongside them. Notably, Plant
    Head (the immediately preceding stage) gets NO access at all here,
    unlike every other stage where the immediately preceding role at
    least kept View. Employee, Manager, HOD and HR get no access either.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('MD_APPROVAL.VIEW', 'MD_APPROVAL', 'View MD Approval records'),
    ('MD_APPROVAL.EDIT', 'MD_APPROVAL', 'Approve or return a record at MD Approval (MD only)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== MD_APPROVAL.VIEW: MD + HR Administrator only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MD_APPROVAL.VIEW'
WHERE r.RoleCode IN ('MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== MD_APPROVAL.EDIT: MD only =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'MD_APPROVAL.EDIT'
WHERE r.RoleCode = 'MD'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/022_create_scoring_engine_tables.sql
-- =============================================================================
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


-- =============================================================================
-- source: sql/023_seed_scoring_engine_permissions.sql
-- =============================================================================
/*
    M18 permission wiring. SCORING_ENGINE.VIEW follows the exact same
    broad grant as ASSIGNMENT.VIEW (M11) - everyone who can see the
    underlying appraisal record can see its final score/rating too, with
    app-layer scoping (self/reports/dept/broad-access, mirroring
    assignments.py's _apply_scope) narrowing it per role. There is no
    SCORING_ENGINE.EDIT - this module never exposes a manual write path
    (see scoring_engine_service.py: the engine runs automatically, once,
    from MD Approval's own /approve action).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SCORING_ENGINE.VIEW', 'SCORING_ENGINE', 'View computed component scores, final score and rating')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SCORING_ENGINE.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'SCORING_ENGINE.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/024_create_workflow_engine_tables.sql
-- =============================================================================
/*
    M19 DDL: Workflow_History (spec Section 4.5). A dedicated, insert-only
    per-record transition log, distinct from Audit_Log (see the model's
    own docstring for why both exist). Run after 023 (Scoring Engine).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Workflow_History')
BEGIN
    CREATE TABLE Workflow_History (
        WorkflowHistoryID INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        FromStatus      VARCHAR(30) NULL,
        ToStatus        VARCHAR(30) NULL,
        ActionedBy      INT NULL REFERENCES Users(UserID),
        ActionedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        Comments        VARCHAR(500) NULL
    );
END;
GO

-- Workflow_History has no UPDATE/DELETE grants for the application role,
-- matching Audit_Log's own insert-only convention (Sec 32).
GO


-- =============================================================================
-- source: sql/025_seed_workflow_engine_permissions.sql
-- =============================================================================
/*
    M19 permission wiring. WORKFLOW_ENGINE.VIEW follows the same broad
    grant as ASSIGNMENT.VIEW (M11) and SCORING_ENGINE.VIEW (M18) -
    everyone who can see the underlying appraisal record can see its
    workflow status/history too, narrowed by the identical app-layer
    self/reports/dept/broad-access scoping. No .EDIT code - this module
    is entirely read-only (see workflow_engine_service.py).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('WORKFLOW_ENGINE.VIEW', 'WORKFLOW_ENGINE', 'View workflow status, SLA and transition history')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== WORKFLOW_ENGINE.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'WORKFLOW_ENGINE.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/026_create_development_plan_tables.sql
-- =============================================================================
/*
    M20 DDL: Development_Plans (spec Section 4.5). Zero or more rows per
    Employee_Performance (no UniqueConstraint - several skill gaps can be
    tracked independently). Run after 025 (Workflow Engine).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Development_Plans')
BEGIN
    CREATE TABLE Development_Plans (
        DevPlanID       INT IDENTITY PRIMARY KEY,
        PerformanceID   INT NOT NULL REFERENCES Employee_Performance(PerformanceID) ON DELETE CASCADE,
        DevelopmentArea VARCHAR(200) NULL,
        SkillGap        VARCHAR(500) NULL,
        TrainingRequired VARCHAR(500) NULL,
        ActionPlan      VARCHAR(500) NULL,
        ResponsiblePersonID INT NULL REFERENCES Employees(EmployeeID),
        TargetDate      DATE NULL,
        CompletionStatus VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        ReviewComments  VARCHAR(500) NULL,
        CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT CK_DevelopmentPlan_CompletionStatus CHECK (CompletionStatus IN ('PENDING', 'IN_PROGRESS', 'COMPLETED'))
    );
END;
GO

/*
    Note: CompletionStatus's vocabulary (PENDING/IN_PROGRESS/COMPLETED) is
    inferred, not read off the DDL (which only gives a default value, no
    enum/CHECK) - see the model module's own docstring for the reasoning.
    This table also deliberately has no lock/stage gate in the service
    layer - a development plan's tracked lifetime routinely outlives the
    appraisal cycle that created it.
*/
GO


-- =============================================================================
-- source: sql/027_seed_development_plan_permissions.sql
-- =============================================================================
/*
    M20 permission wiring. No RBAC matrix row exists for this module (see
    model docstring), so DEVELOPMENT_PLAN.VIEW/.EDIT reuse the exact same
    role split as ASSIGNMENT.VIEW/.EDIT (M11): everyone views (Employee
    sees own via app-layer scope, matching the "My Development Plan"
    screen), and Manager/HR/Plant Head/MD/HR Administrator may create/edit
    - HOD is added to the edit set here (unlike M11's ASSIGNMENT.EDIT)
    because HODReview already captures DevelopmentRecommendation/
    TrainingRequirement during HOD's own review stage, making HOD a
    natural author of the resulting development plan too.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('DEVELOPMENT_PLAN.VIEW', 'DEVELOPMENT_PLAN', 'View development plans (scope depends on role)'),
    ('DEVELOPMENT_PLAN.EDIT', 'DEVELOPMENT_PLAN', 'Create/edit development plans (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== DEVELOPMENT_PLAN.VIEW: everyone (Employee sees own via app-layer scope) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DEVELOPMENT_PLAN.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== DEVELOPMENT_PLAN.EDIT: Manager, HOD, HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DEVELOPMENT_PLAN.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/028_create_pip_tables.sql
-- =============================================================================
/*
    M21 DDL: PIP (spec Section 4.5). EmployeeID-scoped, not tied to one
    Employee_Performance record - a PIP can be opened independent of where
    the employee sits in a given cycle's workflow. Run after 027
    (Development Plan).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PIP')
BEGIN
    CREATE TABLE PIP (
        PIPID               INT IDENTITY PRIMARY KEY,
        EmployeeID          INT NOT NULL REFERENCES Employees(EmployeeID),
        PerformanceGap      VARCHAR(500) NULL,
        ExpectedPerformance VARCHAR(500) NULL,
        ImprovementTarget   VARCHAR(500) NULL,
        ActionPlan          VARCHAR(1000) NULL,
        Training            VARCHAR(500) NULL,
        ManagerID           INT NULL REFERENCES Employees(EmployeeID),
        ReviewDate          DATE NULL,
        PIPStartDate        DATE NULL,
        PIPEndDate          DATE NULL,
        Outcome             VARCHAR(30) NULL,
        Comments            VARCHAR(1000) NULL,
        CreatedAt           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt           DATETIME2 NULL,
        CONSTRAINT CK_PIP_Outcome CHECK (Outcome IS NULL OR Outcome IN ('SUCCESSFUL', 'UNSUCCESSFUL', 'EXTENDED'))
    );
END;
GO

/*
    Note: Outcome is nullable and stays NULL while a PIP is open - only a
    dedicated /close action sets it, one-way (see model/service docstrings).
    ManagerID here is the PIP's own assigned-manager field, not read from
    Employee.ManagerID's org-chart line - see model module docstring for why.
*/
GO


-- =============================================================================
-- source: sql/029_seed_pip_permissions.sql
-- =============================================================================
/*
    M21 permission wiring. No RBAC matrix row exists for this module (see
    model docstring) - Section 7's screen list places PIP management under
    HR, and the table's own ManagerID column names a specifically assigned
    manager per PIP. PIP.VIEW is granted broadly (Employee sees own PIP via
    app-layer scope, Manager sees PIPs assigned to them, HR/Plant Head/MD/
    HR Administrator see all); PIP.EDIT is granted to the same broad-access
    roles plus Manager (scoped in-app to PIPs where PIP.ManagerID matches
    the caller - enforced in pip_service.ensure_can_act, not by this table
    alone). Creating a brand-new PIP is further restricted, in the route
    handler itself, to the broad-access roles only - a Manager holding
    PIP.EDIT may work PIPs already assigned to them but may not open one.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PIP.VIEW', 'PIP', 'View PIPs (scope depends on role)'),
    ('PIP.EDIT', 'PIP', 'Create/edit/close PIPs (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PIP.VIEW: Employee (own), Manager (assigned), HR/Plant Head/MD/HR Admin (all) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PIP.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);

-- ===== PIP.EDIT: Manager (scoped to assigned PIPs, in-app), HR, Plant Head, MD, HR Admin =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PIP.EDIT'
WHERE r.RoleCode IN ('MANAGER', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/030_create_attachment_tables.sql
-- =============================================================================
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


-- =============================================================================
-- source: sql/031_seed_attachment_permissions.sql
-- =============================================================================
/*
    M22 permission wiring. No RBAC matrix row exists for this module (see
    router docstring). ATTACHMENT.VIEW/.EDIT reuse the same broad
    review-chain visibility scope as ASSIGNMENT/SELF_ASSESSMENT: Employee
    (own evidence, app-layer scope), Manager/HOD (their reports/
    department, app-layer scope), HR/Plant Head/MD/HR Administrator
    (everyone). Uploading (ATTACHMENT.EDIT) is granted alongside viewing
    to the same full set, since ownership within that scope is checked
    per-request in the route handler (_ensure_can_upload_for) rather than
    narrowed by role at grant time - unlike Self-Assessment, this module
    also has to support HR/Manager-uploaded evidence (e.g. PIP supporting
    documents), not employee-authored evidence alone.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ATTACHMENT.VIEW', 'ATTACHMENT', 'View attachments/evidence (scope depends on role)'),
    ('ATTACHMENT.EDIT', 'ATTACHMENT', 'Upload attachments/evidence (scope depends on role)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== ATTACHMENT.VIEW / ATTACHMENT.EDIT: everyone (scope enforced in-app) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('ATTACHMENT.VIEW', 'ATTACHMENT.EDIT')
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/032_create_notification_tables.sql
-- =============================================================================
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


-- =============================================================================
-- source: sql/033_seed_notification_permissions.sql
-- =============================================================================
/*
    M23 permission wiring. No RBAC matrix row exists for this module (see
    service module docstring) - Section 7's "Notifications panel" is a
    Common screen for every role, so NOTIFICATION.VIEW is granted to all
    eight roles including System Administrator (a technical account may
    have no linked Employee row at all - handled in-app as "no possible
    notifications" rather than an error). There is no NOTIFICATION.EDIT -
    marking a notification read is bundled into NOTIFICATION.VIEW as part
    of using your own inbox, not a separately grantable capability.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('NOTIFICATION.VIEW', 'NOTIFICATION', 'View and mark read your own notifications')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== NOTIFICATION.VIEW: every role (always self-scoped, enforced in-app) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'NOTIFICATION.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/034_seed_dashboard_permissions.sql
-- =============================================================================
/*
    M24 permission wiring. Unlike every module since M18, this one HAS an
    explicit RBAC matrix row to work from - Section 5's "Dashboards" row:
    Own | Team | Dept | Org | Plant | Org | Org | System health only, for
    Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator/System
    Administrator respectively. There is no dedicated table for this
    module (it aggregates Employee_Performance/Audit_Log/Notifications
    live), so this is the only SQL file M24 needs.

    A single DASHBOARD.VIEW permission is granted to all eight roles -
    which of the two dashboard shapes (business summary vs. system
    health) a given caller gets is decided in the route handler by role,
    not by a second permission code (see dashboard.py's own docstring).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('DASHBOARD.VIEW', 'DASHBOARD', 'View your role-scoped dashboard (business summary or system health)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== DASHBOARD.VIEW: every role (scope/shape enforced in-app per the matrix row) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'DASHBOARD.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/035_seed_report_permissions.sql
-- =============================================================================
/*
    M25 permission wiring. Like Dashboards (M24), this module has an
    explicit RBAC matrix row - Section 5's "Reports/Exports" row:
    Own | Team-scoped | Dept-scoped | Org-scoped | Plant-scoped |
    Org-scoped | Org-scoped | X, for Employee/Manager/HOD/HR/Plant
    Head/MD/HR Administrator/System Administrator respectively. There is
    no dedicated table for this module either (the catalog is a static
    list in code; the one new report aggregates Employee_Performance
    live, exactly like Dashboards), so this is the only SQL file M25
    needs.

    REPORT.VIEW gates both the catalog (GET /reports/catalog, filtered to
    whichever OTHER permissions the caller already holds - see
    report_service.list_available_reports) and the new consolidated
    Appraisal Status report. It is granted to every role except System
    Administrator, matching the matrix's "X" for that column exactly -
    unlike Dashboards (M24), where Sys Admin gets a genuine, if
    different, dashboard, here it gets nothing at all.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('REPORT.VIEW', 'REPORT', 'View the Reports & Export Center catalog and the consolidated Appraisal Status report')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== REPORT.VIEW: every role except System Administrator (matrix: X) =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'REPORT.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/036_seed_audit_log_permissions.sql
-- =============================================================================
/*
    M26 permission wiring. Audit_Log itself and its write path
    (write_audit()) have existed since M1 - this is only the reader's
    permission, following Section 5's "Audit Log" row exactly:
    X | X | X | V(dept) | V(plant) | V(all) | V(all) | V(all, no edit)
    for Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator/System
    Administrator. There is no AUDIT_LOG.EDIT - nobody edits an audit
    trail, matching the matrix's own "no edit" note for every role that
    can see it at all, and the DB-grant-level insert-only enforcement
    already documented on the Audit_Log table itself (sql/001_...).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('AUDIT_LOG.VIEW', 'AUDIT_LOG', 'View the audit trail (scope depends on role - see matrix row)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== AUDIT_LOG.VIEW: HR (dept), Plant Head (plant), MD/HR Admin/Sys Admin (all) =====
-- Employee/Manager/HOD deliberately excluded - the matrix's "X".
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'AUDIT_LOG.VIEW'
WHERE r.RoleCode IN ('HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN', 'SYS_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/037_seed_performance_history_permissions.sql
-- =============================================================================
/*
    M27 permission wiring. Performance History has no matrix row of its
    own (the same kind of gap M18/M20/M21/M22/M23 already hit) - Section
    7's Employee screen #8, "My Performance History," is the only textual
    anchor. No new table: this module aggregates Employee_Performance,
    Performance_Scores and Workflow_History, all of which already exist.

    Granted to all 7 business roles - every role can at minimum see their
    own history via GET /performance-history/me, and the broader roles
    (Manager/HOD/HR/Plant Head/MD/HR Administrator) can additionally see
    in-scope employees via GET /performance-history/{employee_id}, gated
    at the service layer by can_view_employee_history(), not by this
    permission grant.

    System Administrator is deliberately excluded - performance history is
    business content (scores, ratings), and this codebase's running
    principle since M2 is that System Administrator "has no business
    approval rights." This mirrors M25's Reports & Exports decision, not
    M24's Dashboards system-health carve-out (Performance History has no
    technical-only equivalent for Sys Admin to view instead).
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('PERFORMANCE_HISTORY.VIEW', 'PERFORMANCE_HISTORY', 'View own or in-scope employees'' historical appraisal records')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== PERFORMANCE_HISTORY.VIEW: all 7 business roles, System Administrator excluded =====
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'PERFORMANCE_HISTORY.VIEW'
WHERE r.RoleCode IN ('EMPLOYEE', 'MANAGER', 'HOD', 'HR', 'PLANT_HEAD', 'MD', 'HR_ADMIN')
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- source: sql/038_create_system_config_tables.sql
-- =============================================================================
/*
    M28 DDL: System_Config (spec Section 5 row 545 / screen #37). Run
    after 037 (Performance History permissions).

    One row per named setting (key/value) - see the SystemConfig model's
    docstring for why this is a key/value table rather than one column
    per setting, and for why it is scoped to non-secret operational
    settings only (SMTP relay, AD server/domain, file storage path) and
    never true credentials (DB_PASSWORD, AD_BIND_PASSWORD,
    SESSION_SECRET_KEY - those remain environment-variable-only, per
    Section 33/42, enforced by system_config_service.py's NON_SECRET_KEYS
    allowlist at the application layer, not by this table's schema).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'System_Config')
BEGIN
    CREATE TABLE System_Config (
        ConfigID        INT IDENTITY PRIMARY KEY,
        ConfigKey       VARCHAR(100) NOT NULL UNIQUE,
        ConfigValue     VARCHAR(500) NULL,
        Description     VARCHAR(300) NULL,
        ModifiedBy      INT NULL REFERENCES Users(UserID),
        ModifiedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

/*
    No default rows are seeded here deliberately - an empty table means
    every operational setting falls back to its environment-variable
    default (see app/core/config.py's Settings class) until a System
    Administrator explicitly overrides it through this screen, matching
    the "never hard-coded" principle this module's own docstring
    documents at length.
*/
GO


-- =============================================================================
-- source: sql/039_seed_system_config_permissions.sql
-- =============================================================================
/*
    M28 permission wiring. The last row in the whole RBAC matrix
    (Section 5): System Configuration (SMTP, AD server, storage path) is
    "X" for every role except System Administrator, who gets C,V,E - the
    single narrowest-reach row in the entire matrix, and the only module
    in this codebase granted to System Administrator alone.
*/

INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('SYSTEM_CONFIG.VIEW', 'SYSTEM_CONFIG', 'View app-wide operational configuration'),
    ('SYSTEM_CONFIG.EDIT', 'SYSTEM_CONFIG', 'Create/edit app-wide operational configuration')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

-- ===== SYSTEM_CONFIG.VIEW / .EDIT: System Administrator only =====
-- Note: the route layer itself gates on require_any_role("SYS_ADMIN"),
-- not these permission codes, since no other role holds them - these
-- grants exist for completeness/consistency with every other module's
-- Permissions/Role_Permissions wiring, and for any future UI that wants
-- to check "can this user reach the System Configuration screen at all."
INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode IN ('SYSTEM_CONFIG.VIEW', 'SYSTEM_CONFIG.EDIT')
WHERE r.RoleCode = 'SYS_ADMIN'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


/*
    Employee self-service KPA/KPI proposal (sql/044). Adds
    ASSIGNMENT.PROPOSE, a narrower sibling of ASSIGNMENT.EDIT above,
    granted to EMPLOYEE only - see app/api/routes/assignments.py's
    "DESIGN NOTE on ASSIGNMENT.PROPOSE" for the full design: an employee
    may create/edit their own DRAFT appraisal record's KPAs/KPIs, but
    submission (moving it out of DRAFT) stays ASSIGNMENT.EDIT-only, so a
    Manager/HR reviewing and submitting an employee-proposed draft is
    what "approves" it. No schema change.
*/
INSERT INTO Permissions (PermissionCode, Module, Description)
SELECT v.Code, v.Module, v.Description
FROM (VALUES
    ('ASSIGNMENT.PROPOSE', 'KPA_KPI_ASSIGNMENT', 'Employee: create/edit own DRAFT KPA/KPI assignment (subject to Manager/HR submitting it before it takes effect)')
) AS v(Code, Module, Description)
WHERE NOT EXISTS (SELECT 1 FROM Permissions p WHERE p.PermissionCode = v.Code);
GO

INSERT INTO Role_Permissions (RoleID, PermissionID)
SELECT r.RoleID, p.PermissionID
FROM Roles r
JOIN Permissions p ON p.PermissionCode = 'ASSIGNMENT.PROPOSE'
WHERE r.RoleCode = 'EMPLOYEE'
  AND NOT EXISTS (SELECT 1 FROM Role_Permissions rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID);
GO


-- =============================================================================
-- Schema + seed data complete. Next steps (run separately, not part of this
-- script):
--   1. Edit and run sql/040_bootstrap_first_admin.sql to create your first
--      SYS_ADMIN login (production/AD-backed installs), OR
--      sql/demo_only/041_create_demo_login_table.sql +
--      sql/demo_only/042_bootstrap_first_admin_demo_local.sql (Windows 11
--      Home / no-AD demo only, AUTH_MODE=demo_local).
--   2. Point the app's .env DB_SERVER/DB_NAME=PMS_DB at this database and
--      start uvicorn — see DEPLOYMENT.md or DEPLOY_WINDOWS11_HOME_DEMO.md.
-- =============================================================================
