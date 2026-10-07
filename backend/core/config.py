import os
from pathlib import Path

# Load .env from the project root (two levels up from this file) explicitly —
# load_dotenv() with no args relies on caller-frame inspection that can fail
# silently under uvicorn reload, leaving env vars unset.
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parents[2] / '.env'
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

# ── API metadata ──
APP_TITLE = 'AI Resume Intelligence Platform API'
APP_VERSION = '2.0.0'
APP_DESCRIPTION = (
    'Analyze resumes against job descriptions using NLP, ML, and AI. '
    'Provides ATS compatibility scoring, skill validation, keyword matching, '
    'and actionable improvement recommendations.'
)

# ── CORS ──
# Parse from env or fall back to sensible development defaults.
_origins_env = os.getenv('ALLOWED_ORIGINS', '')
ALLOWED_ORIGINS = [
    o.strip() for o in _origins_env.split(',') if o.strip()
] if _origins_env else [
    'http://localhost:5173',   # Vite React dev server
    'http://localhost:3000',   # Alternative React dev
    'http://localhost:8501',   # Streamlit dev server
    'http://127.0.0.1:5173',
    'http://127.0.0.1:8501',
]

# ── File upload limits ──
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '5'))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# ── Supported MIME types and their short names ──
SUPPORTED_MIME_TYPES = {
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'text/plain': 'txt',
}

SUPPORTED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt'}

# ── NLP Models ──
SPACY_MODEL_PRIMARY = os.getenv('SPACY_MODEL_PRIMARY', 'en_core_web_md')
SPACY_MODEL_SECONDARY = os.getenv('SPACY_MODEL_SECONDARY', 'en_core_web_sm')
SENTENCE_TRANSFORMER_MODEL = os.getenv('SENTENCE_TRANSFORMER_MODEL', 'all-MiniLM-L6-v2')

# ── Scoring configuration ──
# Component weights — defines the max points for each scoring dimension.
# These are the ONLY source of truth for scoring weights.
SCORE_WEIGHTS = {
    'formatting':       15,
    'keywords':         20,
    'content':          15,
    'skill_validation': 20,
    'ats_compatibility': 15,
    'contact':           5,
    'grammar':          10,
}

# JD matching blend weights (keyword vs semantic)
JD_KEYWORD_WEIGHT = float(os.getenv('JD_KEYWORD_WEIGHT', '0.6'))
JD_SEMANTIC_WEIGHT = float(os.getenv('JD_SEMANTIC_WEIGHT', '0.4'))

# ── External services ──
SUPABASE_URL        = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY        = os.getenv('SUPABASE_KEY', '')          # service_role — DB writes
SUPABASE_ANON_KEY   = os.getenv('SUPABASE_ANON_KEY', '')     # public anon — frontend auth
SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET', '')    # verify access tokens

GROQ_API_KEY     = os.getenv('GROQ_API_KEY', '')
OPENAI_API_KEY   = os.getenv('OPENAI_API_KEY', '')

# ── LLM Configuration ──
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '4096'))
LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.0'))
