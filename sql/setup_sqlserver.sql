/*
Run this script in SSMS as a SQL Server administrator.
Change [YOURDOMAIN\YourWindowsUser] to the Windows account or AD group
that runs the Python collectors and Streamlit dashboard.
*/
USE [master];
GO
IF DB_ID(N'TaigunTelemetry') IS NULL
    CREATE DATABASE [TaigunTelemetry];
GO

USE [TaigunTelemetry];
GO

IF OBJECT_ID(N'dbo.TelemetryReadings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TelemetryReadings (
        Id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TelemetryReadings PRIMARY KEY,
        ReceivedAtUtc DATETIMEOFFSET(3) NOT NULL,
        Source NVARCHAR(20) NOT NULL,
        PayloadJson NVARCHAR(MAX) NOT NULL,
        CloudSynced BIT NOT NULL CONSTRAINT DF_TelemetryReadings_CloudSynced DEFAULT (0)
    );

    CREATE INDEX IX_TelemetryReadings_ReceivedAtUtc
        ON dbo.TelemetryReadings(ReceivedAtUtc);

    CREATE INDEX IX_TelemetryReadings_Source
        ON dbo.TelemetryReadings(Source);
END;
GO

/*
Create a database user for the Windows identity running Python.
For a local account, use [COMPUTERNAME\WindowsUser].
For an AD identity/group, use [DOMAIN\GroupName].
*/
IF SUSER_ID(N'YOURDOMAIN\YourWindowsUser') IS NULL
    CREATE LOGIN [YOURDOMAIN\YourWindowsUser] FROM WINDOWS;
GO

USE [TaigunTelemetry];
GO
IF USER_ID(N'YOURDOMAIN\YourWindowsUser') IS NULL
    CREATE USER [YOURDOMAIN\YourWindowsUser]
    FOR LOGIN [YOURDOMAIN\YourWindowsUser];
GO

/*
Least privilege: only read telemetry, insert new telemetry and update sync flag.
No db_owner, db_ddladmin, sysadmin, or schema modification permission.
*/
GRANT SELECT, INSERT, UPDATE ON dbo.TelemetryReadings
    TO [YOURDOMAIN\YourWindowsUser];
GO

/* Optional trip-session table used by the telemetry dashboard. */
IF OBJECT_ID(N'dbo.TelemetryTrips', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TelemetryTrips (
        TripId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TelemetryTrips PRIMARY KEY,
        TripName NVARCHAR(100) NOT NULL,
        Notes NVARCHAR(500) NULL,
        StartedAtUtc DATETIMEOFFSET(3) NOT NULL,
        EndedAtUtc DATETIMEOFFSET(3) NULL,
        Status NVARCHAR(20) NOT NULL CONSTRAINT DF_TelemetryTrips_Status DEFAULT ('active'),
        CONSTRAINT CK_TelemetryTrips_Status CHECK (Status IN ('active','completed')),
        CONSTRAINT CK_TelemetryTrips_Time CHECK (EndedAtUtc IS NULL OR EndedAtUtc >= StartedAtUtc)
    );
    CREATE INDEX IX_TelemetryTrips_StartedAtUtc ON dbo.TelemetryTrips(StartedAtUtc);
END;
GO
GRANT SELECT, INSERT, UPDATE ON dbo.TelemetryTrips TO [YOURDOMAIN\YourWindowsUser];
GO

/* Optional trip-session table used by the telemetry dashboard. */
IF OBJECT_ID(N'dbo.TelemetryTrips', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TelemetryTrips (
        TripId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TelemetryTrips PRIMARY KEY,
        TripName NVARCHAR(100) NOT NULL,
        Notes NVARCHAR(500) NULL,
        StartedAtUtc DATETIMEOFFSET(3) NOT NULL,
        EndedAtUtc DATETIMEOFFSET(3) NULL,
        Status NVARCHAR(20) NOT NULL CONSTRAINT DF_TelemetryTrips_Status DEFAULT ('active'),
        CONSTRAINT CK_TelemetryTrips_Status CHECK (Status IN ('active','completed')),
        CONSTRAINT CK_TelemetryTrips_Time CHECK (EndedAtUtc IS NULL OR EndedAtUtc >= StartedAtUtc)
    );
    CREATE INDEX IX_TelemetryTrips_StartedAtUtc ON dbo.TelemetryTrips(StartedAtUtc);
END;
GO
GRANT SELECT, INSERT, UPDATE ON dbo.TelemetryTrips TO [YOURDOMAIN\YourWindowsUser];
GO
