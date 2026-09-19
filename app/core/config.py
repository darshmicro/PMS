"""
Central configuration. All environment-specific values (DB, AD, secrets) come
from environment variables / .env - never hard-coded (spec Section 33/42).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application
    APP_NAME: str = "Performance Management System"
    SESSION_SECRET_KEY: str
    SESSION_TIMEOUT_MINUTES: int = 30
    ENVIRONMENT: str = "production"

    # Database
    DB_SERVER: str
    DB_PORT: int = 1433
    DB_NAME: str
    DB_AUTH_MODE: str = "sql"  # sql | windows
    DB_USER: str | None = None
    DB_PASSWORD: str | None = None
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    # ODBC Driver 18 encrypts by default and validates the server certificate
    # against a trusted CA. A real production SQL Server should have a
    # properly-issued certificate, so this stays "no" (validate it) unless
    # explicitly overridden. A local SQL Server Express instance (e.g. the
    # Windows 11 Home demo) only has a self-signed certificate, so that demo
    # setup sets this to "yes" in .env - see DEPLOY_WINDOWS11_HOME_DEMO.md.
    DB_TRUST_SERVER_CERTIFICATE: str = "no"  # no | yes

    # Auth mode
    # iis_forwarded | ldap_bind | demo_local | hybrid
    #   iis_forwarded: IIS/Windows Integrated Auth in front of the app; the
    #     app only trusts the header IIS forwards (AD users only).
    #   ldap_bind: the app itself binds to AD with a submitted username +
    #     password, no IIS needed (AD users only).
    #   demo_local: local-demo-only path with no AD dependency at all (see
    #     app/services/demo_auth_service.py) - refused outright whenever
    #     ENVIRONMENT=production.
    #   hybrid: every login is checked against the app's own local account
    #     table first, and falls through to an AD bind (same as ldap_bind)
    #     only if no local account matches - one login screen serving both
    #     real AD users and local-only accounts. Permitted in production -
    #     see DEPLOYMENT.md's "Hybrid (AD + local users)" section.
    AUTH_MODE: str = "iis_forwarded"
    IIS_FORWARDED_USER_HEADER: str = "X-Remote-User"

    # Active Directory
    AD_SERVER: str
    AD_DOMAIN: str
    AD_USE_SSL: bool = True
    AD_PORT: int = 636
    AD_BIND_DN: str | None = None
    AD_BIND_PASSWORD: str | None = None
    AD_BASE_DN: str | None = None

    # File storage / email placeholders (config completeness, used by later modules)
    FILE_STORAGE_PATH: str = ""
    MAX_UPLOAD_SIZE_MB: int = 25
    SMTP_SERVER: str | None = None
    SMTP_PORT: int = 25
    SMTP_FROM: str | None = None

    @property
    def sqlalchemy_database_uri(self) -> str:
        driver = self.DB_DRIVER.replace(" ", "+")
        if self.DB_AUTH_MODE == "windows":
            return (
                f"mssql+pyodbc://@{self.DB_SERVER},{self.DB_PORT}/{self.DB_NAME}"
                f"?driver={driver}&trusted_connection=yes&Encrypt=yes"
                f"&TrustServerCertificate={self.DB_TRUST_SERVER_CERTIFICATE}"
            )
        return (
            f"mssql+pyodbc://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_SERVER},{self.DB_PORT}"
            f"/{self.DB_NAME}?driver={driver}&Encrypt=yes"
            f"&TrustServerCertificate={self.DB_TRUST_SERVER_CERTIFICATE}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
