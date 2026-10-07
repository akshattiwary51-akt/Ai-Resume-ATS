# Architecture Document — AI Resume Intelligence Platform

## 1. Current Architecture (Pre-Upgrade)

```
┌──────────────────┐      HTTP/REST       ┌──────────────────────────┐
│  Streamlit UI    │  ──────────────────>  │  FastAPI Backend         │
│  (frontend/)     │  <──────────────────  │  (backend/)              │
│                  │                       │                          │
│  views/          │                       │  api/routes.py           │
│  components/     │                       │  services/               │
│  services/       │                       │    ├── groq_parser.py    │
│    api_client    │                       │    ├── ats_scorer.py     │
│    supabase_clt  │                       │    ├── resume_parser.py  │
│                  │                       │    ├── resume_analyzer.py│
└──────────────────┘                       │    ├── jd_matcher.py     │
                                           │    ├── feedback_engine.py│
                                           │    ├── recommendation.py │
                                           │    ├── report_generator  │
                                           │    └── pdf_export.py     │
                                           │                          │
                                           │  database/               │
                                           │    └── supabase_db.py    │
                                           │                          │
                                           │  External:               │
                                           │    Groq LLM (Llama 3.3) │
                                           │    Supabase (PostgreSQL) │
                                           │    spaCy (en_core_web_md)│
                                           │    SentenceTransformers  │
                                           └──────────────────────────┘
```

### Data Flow

```
User Upload (PDF/DOCX)
  → File Validation (size, MIME, extension)
  → Text Extraction (pdfplumber → PyPDF2 fallback)
  → Groq LLM Parsing (resume → structured JSON) ← HARD DEPENDENCY
  → Skill Validation (embedding similarity)
  → JD Comparison (if provided)
  → ATS Scoring (5 components)
  → Feedback Generation
  → Save to Supabase
  → Return AnalysisResponse
```

---

## 2. Bugs and Issues Discovered

### CRITICAL BUGS

| # | File | Issue |
|---|------|-------|
| 1 | `groq_parser.py:118` | **Inverted JSON parse logic.** `if result is None` on line 118 calls `_validate_resume_result(None)` — passing `None` to a function that expects `dict`. When parsing succeeds (result is NOT None), it falls through to the retry path. The condition should be `if result is not None`. |
| 2 | `groq_parser.py:210` | **`_validate_resume_result` crashes on `None` input.** It calls `result.get(...)` and iterates `result.keys()` with no null guard. When called with `None` from the inverted logic above, it throws `AttributeError`. |
| 3 | `config.py:37` | **Malformed spaCy model name.** `SPACY_MODEL_SECONDARY='\"en_core_web_sm'` — contains a leading double-quote character inside the string. `spacy.load('"en_core_web_sm')` will fail with `OSError`. |
| 4 | `resume_parser.py:25-29` | **Duplicate `FileParsingError` class.** Shadows the imported `FileParsingError` from `file_utils.py`. The `from backend.utils.file_utils import FileParsingError` on line 10 is immediately overridden by the local class on line 25. |
| 5 | `feedback_engine.py:1` | **Syntax error / stray comment.** Line 1 is `so yeah#what is specifically wrong in my resume?` — a non-comment, non-code string that will cause a `SyntaxError` on import. |
| 6 | `config.py:19-21` | **CORS misconfiguration.** `ALLOWED_ORIGINS` only contains the deployed Streamlit URL with a trailing slash. `localhost` is not listed, so local development CORS requests fail silently. |

### HIGH-PRIORITY ISSUES

| # | File | Issue |
|---|------|-------|
| 7 | `resume_analyzer.py:71-72` | **Grammar and location always use defaults.** `grammar_results = get_default_grammar_results()` returns `total_errors=0, penalty=0`. This means every resume gets a "perfect grammar" bonus (+1 point) and no grammar penalty. Grammar is never actually analyzed. |
| 8 | `ats_scorer.py:350-352` | **False "perfect grammar" bonus.** `if grammar_results.get('total_errors', 0) == 0: score += 1.0` — always true since grammar analysis is stubbed out, inflating every score by 1 point. |
| 9 | `groq_parser.py` | **Hard Groq dependency.** If `GROQ_API_KEY` is missing, `parse_resume()` raises `ValueError`, crashing the entire analysis pipeline. No fallback parser exists. The README claims "scoring still works" without Groq — this is false. |
| 10 | `.gitignore` | **Missing critical entries.** `.env`, `secrets.toml`, `*.pem`, `*.key`, `/logs/`, and generated PDF files are not gitignored. Secrets can be accidentally committed. |
| 11 | `supabase_db.py:84` | **Hard-coded job title.** `"job_title": "Software Engineer"` — every history entry shows the same role regardless of actual analysis. |
| 12 | `jd_matcher.py:1-9` | **Duplicate imports.** Lines 1-9 contain exact duplicate import blocks. |
| 13 | `config.py:40-44` | **SCORE_WEIGHTS config unused.** The `SCORE_WEIGHTS` dict is defined but never imported by `ats_scorer.py`. The scorer uses hard-coded maximums (`20, 25, 25, 15, 15`) and hard-coded blend weights (`0.40, 0.30, 0.15, 0.15`). |
| 14 | `ats_scorer.py:75-90` | **Per-skill embedding is O(n*m).** Each skill is individually encoded against the full text. For 20 skills x 5 projects, this is 100+ embedding calls. No batching, no caching. |
| 15 | `jd_matcher.py:18` | **Truncated embedding input.** `resume_text[:5000]` — arbitrary character truncation loses context from longer resumes. |

### MODERATE ISSUES

| # | File | Issue |
|---|------|-------|
| 16 | `ats_scorer.py:323-330` | **Scoring formula doesn't match SCORE_WEIGHTS.** The base_score formula uses `0.40/0.30/0.15/0.15` with a combined `skills_keywords_pct`. The SCORE_WEIGHTS config says `formatting:20, keywords:25, content:25, skill_validation:15, ats_compatibility:15`. These two representations are inconsistent. |
| 17 | `routes.py:41-45` | **Imports inside request handlers.** Service modules are imported inside each route function, adding import overhead to every request. |
| 18 | `resume_analyzer.py` | **`recommendation_engine` never called.** The `recommendation_engine.py` (438 lines) is never invoked anywhere in the analysis pipeline. Dead code. |
| 19 | `schemas.py:36-53` | **Duplicate response fields.** `AnalysisResponse` has both `ATS_score` and `ats_score`, both `jd_match_analysis` and `jd_comparison`. This inflates the response size and creates confusion. |
| 20 | `landing.py:71-73` | **Misleading privacy claim.** "All analysis runs locally with no external API calls" — false. The app calls Groq API, Supabase, and requires network access. |
| 21 | `resume_parser.py:3` | **Duplicate import.** `from typing import Tuple, Optional, Tuple` — `Tuple` imported twice. |

### LOW-PRIORITY ISSUES

| # | File | Issue |
|---|------|-------|
| 22 | Various | **Typos in log messages.** `valiudation`, `deteminin`, `moetod02`, `dedeuction01`. |
| 23 | `file_utils.py:6-8` | **Creates `/logs` directory on import.** Side effect at module level. |
| 24 | `config.py:15-16` | **Version mismatch.** `APP_VERSION='1.0.0'` but `main.py:67` returns `'version': '2.0.0'`. |
| 25 | Various | **No `__init__.py` files** in `backend/`, `backend/api/`, `backend/core/`, etc. — works with uvicorn but breaks direct imports. |

---

## 3. Security Issues

1. **`.gitignore` missing `.env`** — API keys can be committed
2. **Service-role key used in backend REST calls** — `SUPABASE_KEY` with `service_role` bypasses RLS
3. **No file content sanitization** — uploaded PDFs could contain malicious payloads
4. **CORS allows all methods/headers** — `allow_methods=['*'], allow_headers=['*']`
5. **No rate limiting** on any endpoint
6. **Error messages expose internal details** — `detail=f'Analysis pipeline failed: {exc}'`

---

## 4. Target Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    React + Vite + TypeScript Frontend             │
│                                                                  │
│  pages/           components/         stores/         services/  │
│  ├── Landing      ├── ScoreCard      ├── authStore   ├── api    │
│  ├── Dashboard    ├── UploadZone     ├── resumeStore ├── auth   │
│  ├── Analyze      ├── ScoreBreak     ├── analysisStr │          │
│  ├── History      ├── SkillMatrix    └── uiStore     │          │
│  ├── Optimizer    ├── JDComparison                   │          │
│  ├── CoverLetter  ├── ResumeEditor                   │          │
│  ├── Interview    ├── CompareView                    │          │
│  ├── CareerGap    ├── Charts                         │          │
│  └── Settings     └── Layout                         │          │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST API
┌───────────────────────────┴──────────────────────────────────────┐
│                    FastAPI Backend (Refactored)                   │
│                                                                  │
│  api/v1/                                                         │
│  ├── resumes.py        POST /upload, GET /, GET /{id}, DELETE    │
│  ├── analysis.py       POST /analyze, GET /status                │
│  ├── jobs.py           POST /analyze-jd, POST /match             │
│  ├── optimizer.py      POST /optimize, POST /apply               │
│  ├── cover_letter.py   POST /generate                            │
│  ├── interview.py      POST /generate                            │
│  ├── analytics.py      GET /dashboard, GET /history              │
│  └── auth.py           (JWT verification middleware)             │
│                                                                  │
│  services/                                                       │
│  ├── parsing/          ResumeParser, JDParser, OCRProvider       │
│  ├── analysis/         ScoringEngine, Analyzers (11 types)       │
│  ├── matching/         SkillMatcher, KeywordMatcher, Taxonomy    │
│  ├── ai/               LLMProvider (Groq/OpenAI/Fallback)       │
│  ├── optimization/     ResumeOptimizer, CoverLetterGen           │
│  └── export/           PDFReport, HTMLReport                     │
│                                                                  │
│  repositories/                                                   │
│  ├── resume_repo.py                                              │
│  ├── analysis_repo.py                                            │
│  └── user_repo.py                                                │
│                                                                  │
│  core/                                                           │
│  ├── config.py         Environment-driven configuration          │
│  ├── security.py       Auth, rate limiting, file validation      │
│  └── scoring_config.py Configurable scoring weights              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Key Design Decisions

1. **Deterministic-first analysis**: Core ATS scoring, keyword matching, formatting analysis, and structure validation work without any LLM. Groq/LLM enhances with explanations and rewrites.

2. **Configurable scoring engine**: All weights loaded from `scoring_config.py`, overridable via environment. No hard-coded magic numbers in scoring logic.

3. **LLM provider abstraction**: `LLMProvider` interface with `GroqProvider`, `OpenAIProvider`, and `FallbackProvider` (regex/spaCy based). Graceful degradation when no API key exists.

4. **Section-aware NLP**: Embeddings computed per-section (summary, experience, skills, projects) rather than on truncated full text. Batch encoding for efficiency.

5. **Evidence-based skill validation**: Every detected skill linked to source section, evidence text, and confidence score.
