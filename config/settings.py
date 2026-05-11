from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


_PARAMS_PATH = Path(__file__).parent.parent / "params.yaml"


def _load_params() -> dict:
    if _PARAMS_PATH.exists():
        with open(_PARAMS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_p = _load_params()
_llm = _p.get("llm", {})
_bp = _p.get("blood_pressure", {})
_sched = _p.get("scheduler", {})
_sess = _p.get("session", {})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== AI / LLM =====
    openai_api_key: str
    openrouter_api_key: str  # required — no default

    # LLM tuneable params (defaults from params.yaml)
    model: str = Field(default=_llm.get("model", "gpt-4o-mini"))
    temperature: float = Field(default=_llm.get("temperature", 0.3))
    report_model: str = Field(default=_llm.get("report_model", "gpt-4o"))
    report_temperature: float = Field(default=_llm.get("report_temperature", 0.0))

    # ===== WHATSAPP / META CLOUD API =====
    whatsapp_access_token: str  # required — no default
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str
    whatsapp_api_version: str = "v24.0"

    # ===== MONGODB =====
    mongodb_uri: str  # required — no default
    db_name: str = "remedi_chronic_care"

    # ===== REDIS =====
    redis_url: str = "redis://localhost:6379"
    redis_password: str = ""

    # ===== MINIO =====
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "remedi"
    minio_secret_key: str = ""
    minio_bucket_reports: str = "patient-reports"
    minio_bucket_pdfs: str = "annual-reports"
    minio_secure: bool = False

    # ===== AUTH / SECURITY =====
    jwt_secret: str  # required — no default
    jwt_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    google_form_secret: str = ""

    # ===== APPLICATION =====
    environment: str = "development"
    port: int = 8000
    debug: bool = True
    host: str = "0.0.0.0"

    # ===== BUSINESS / CONTACT =====
    registration_form_url: str = ""
    payment_link: str = ""
    support_phone: str = ""
    emergency_phone: str = ""

    # ===== ADMIN =====
    admin_email: str = ""
    admin_phone: str = ""

    # ===== BLOOD PRESSURE THRESHOLDS (from params.yaml) =====
    bp_normal_systolic_max: int = Field(default=_bp.get("normal_systolic_max", 120))
    bp_normal_diastolic_max: int = Field(default=_bp.get("normal_diastolic_max", 80))
    bp_warning_systolic_max: int = Field(default=_bp.get("warning_systolic_max", 140))
    bp_warning_diastolic_max: int = Field(default=_bp.get("warning_diastolic_max", 90))
    bp_critical_systolic: int = Field(default=_bp.get("critical_systolic", 180))
    bp_critical_diastolic: int = Field(default=_bp.get("critical_diastolic", 120))

    # ===== SCHEDULER (from params.yaml) =====
    scheduler_health_tip_interval_hours: int = Field(default=_sched.get("health_tip_interval_hours", 84))
    scheduler_bp_reminder_hour: int = Field(default=_sched.get("bp_reminder_hour", 8))
    scheduler_blood_test_reminder_days_before: int = Field(default=_sched.get("blood_test_reminder_days_before", 3))

    # ===== SESSION (from params.yaml) =====
    session_conversation_timeout_minutes: int = Field(default=_sess.get("conversation_timeout_minutes", 30))

    @model_validator(mode="after")
    def _check_critical(self) -> "Settings":
        missing = [
            name for name, val in [
                ("MONGODB_URI", self.mongodb_uri),
                ("JWT_SECRET", self.jwt_secret),
                ("WHATSAPP_ACCESS_TOKEN", self.whatsapp_access_token),
                ("OPENROUTER_API_KEY", self.openrouter_api_key),
            ]
            if not val
        ]
        if missing:
            raise ValueError(
                "\n\n  FATAL: Missing required environment variables:\n"
                + "\n".join(f"    • {m}" for m in missing)
                + "\n\n  Check your .env file.\n"
            )
        return self


settings = Settings()
