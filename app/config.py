import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Detect Vercel / serverless runtime environment
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

if IS_VERCEL:
    INSTANCE_DIR = Path("/tmp/instance")
    DEFAULT_UPLOAD_DIR = Path("/tmp/uploads")
else:
    INSTANCE_DIR = BASE_DIR / "instance"
    DEFAULT_UPLOAD_DIR = BASE_DIR / "instance" / "uploads"

try:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    INSTANCE_DIR = Path("/tmp/instance")
    DEFAULT_UPLOAD_DIR = Path("/tmp/uploads")
    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

load_dotenv(BASE_DIR / ".env")

DEFAULT_DB_PATH = (INSTANCE_DIR / "interview_studio.db").as_posix()
raw_db_url = (
    os.getenv("DATABASE_URL", "").strip() or 
    os.getenv("POSTGRES_URL", "").strip() or 
    os.getenv("POSTGRES_URL_NON_POOLING", "").strip()
)
if not raw_db_url or "sqlite:///instance/" in raw_db_url or raw_db_url == "sqlite:///instance/interview_studio.db":
    RESOLVED_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"
else:
    if raw_db_url.startswith("postgres://"):
        RESOLVED_DB_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        RESOLVED_DB_URL = raw_db_url


class Config:
    """Base application configuration."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Database
    DATABASE_URL = RESOLVED_DB_URL
    SQLALCHEMY_DATABASE_URI = RESOLVED_DB_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # MongoDB Database
    MONGO_URI = os.getenv("MONGO_URI", "").strip()
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "").strip() or None
    
    # Upload settings
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))  # 10 MB
    UPLOAD_FOLDER = DEFAULT_UPLOAD_DIR if IS_VERCEL else (BASE_DIR / os.getenv("UPLOAD_FOLDER", "instance/uploads"))
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
    
    # ElevenLabs Conversational AI
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    ELEVENLABS_AUTH_MODE = os.getenv("ELEVENLABS_AUTH_MODE", "signed_url").lower().strip()  # 'signed_url' or 'public'
    ELEVENLABS_ALLOWED_ORIGIN = os.getenv("ELEVENLABS_ALLOWED_ORIGIN", "").strip()
    ELEVENLABS_WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    
    # LLM Settings (OpenAI fixed for assessment & planning)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("CLAUDE_API_KEY", "").strip()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip() or OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY
    
    # Provider-specific models
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022").strip()
    GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-exp").strip()
    OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip()
    OPENAI_REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "alloy").strip()
    
    # Fixed Voice Engine
    VOICE_ENGINE = os.getenv("VOICE_ENGINE", "elevenlabs").lower().strip()

    # Sarvam AI Voice Configuration (legacy)
    SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
    SARVAM_VOICE_ID = os.getenv("SARVAM_VOICE_ID", "01a0e8fc-9123-73bb-bd4e-04df4741957a").strip()
    SARVAM_AGENT_ID = os.getenv("SARVAM_AGENT_ID", "interview-02c7fae8-dbd6").strip()
    SARVAM_SPEAKER = os.getenv("SARVAM_SPEAKER", "aditya").strip()
    SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()
    SARVAM_LANGUAGE_CODE = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN").strip()
    SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip()
    
    # Auto-detect Gemini if key starts with AIza
    if LLM_API_KEY.startswith("AIza") and LLM_PROVIDER not in ("gemini", "mock"):
        LLM_PROVIDER = "gemini"

    # Default model depending on provider
    default_model = (
        OPENAI_MODEL if LLM_PROVIDER == "openai"
        else GEMINI_MODEL if LLM_PROVIDER == "gemini"
        else CLAUDE_MODEL if LLM_PROVIDER == "claude"
        else "mock"
    )
    LLM_MODEL = os.getenv("LLM_MODEL", default_model).strip()
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or None

    @classmethod
    def is_elevenlabs_configured(cls) -> bool:
        if cls.ELEVENLABS_AUTH_MODE == "public":
            return bool(cls.ELEVENLABS_AGENT_ID)
        return bool(cls.ELEVENLABS_API_KEY and cls.ELEVENLABS_AGENT_ID)

    @classmethod
    def is_gemini_live_configured(cls) -> bool:
        return bool(cls.GEMINI_API_KEY and not cls.GEMINI_API_KEY.startswith("your_"))

    @classmethod
    def is_openai_realtime_configured(cls) -> bool:
        key = cls.OPENAI_API_KEY or cls.LLM_API_KEY
        return bool(key and not key.startswith("your_") and not key.startswith("AIza"))

    @classmethod
    def is_sarvam_configured(cls) -> bool:
        return bool(cls.SARVAM_API_KEY and not cls.SARVAM_API_KEY.startswith("your_"))

    @classmethod
    def is_mongo_configured(cls) -> bool:
        return bool(cls.MONGO_URI and not cls.MONGO_URI.startswith("your_"))

    @classmethod
    def is_pinecone_configured(cls) -> bool:
        return False

    @classmethod
    def is_provider_configured(cls, provider: str) -> bool:
        prov = (provider or "").lower().strip()
        if prov == "mock":
            return True
        elif prov == "gemini":
            return bool(cls.GEMINI_API_KEY and not cls.GEMINI_API_KEY.startswith("your_"))
        elif prov == "openai":
            key = cls.OPENAI_API_KEY or cls.LLM_API_KEY
            return bool(key and not key.startswith("your_") and not key.startswith("AIza"))
        elif prov == "claude":
            key = cls.ANTHROPIC_API_KEY
            return bool(key and not key.startswith("your_"))
        return False

    @classmethod
    def is_llm_configured(cls) -> bool:
        return cls.is_provider_configured(cls.LLM_PROVIDER)


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LLM_PROVIDER = "mock"
    ELEVENLABS_AGENT_ID = "mock-agent-id-123"
    ELEVENLABS_API_KEY = "mock-api-key-xyz"
    OPENAI_API_KEY = "mock-openai-key-realtime"


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
