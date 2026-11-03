/* Run once in SSMS as an administrator. Keeps the existing TelemetryReadings table unchanged. */
USE [TaigunTelemetry];
GO
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
/* Grant the existing Windows-authenticated application login least-privilege access. */
IF USER_ID(N'ECM\ECM_Repair') IS NOT NULL
    GRANT SELECT, INSERT, UPDATE ON dbo.TelemetryTrips TO [ECM\ECM_Repair];
GO

/* Enforce a single active session. Safe to re-run. */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TelemetryTrips')
      AND name = N'UX_TelemetryTrips_OneActive'
)
    CREATE UNIQUE INDEX UX_TelemetryTrips_OneActive
        ON dbo.TelemetryTrips(Status)
        WHERE Status = 'active';
GO
