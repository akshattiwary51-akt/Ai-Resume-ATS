# Upgrade Plan — AI Resume Intelligence Platform

## Current State Summary

- Working: File parsing (PDF/DOCX), Supabase auth, basic ATS scoring, JD comparison, PDF reports
- Broken: Groq JSON parsing (inverted logic), spaCy fallback model name, feedback engine syntax error
- Missing: Grammar analysis, LLM fallback, deterministic parsing, tests, proper security
- Dead code: recommendation_engine.py (438 lines, never called)

## Weaknesses

1. **Single point of failure**: Groq API key required for any analysis to work
2. **Inflated scores**: Grammar bonus always applied (+1pt), no grammar analysis exists
3. **Critical bugs**: 6 bugs that cause crashes or incorrect behavior
4. **No tests**: Zero test coverage
5. **Security gaps**: `.env` not gitignored, CORS misconfigured, no rate limiting
6. **Performance**: O(n×m) embedding calls per skill validation, no batching
7. **Streamlit limitations**: No multi-page routing, no interactive editor, poor state management

## Implementation Phases

### PHASE 1: Fix Critical Bugs & Stabilize (Current Priority)

**Goal**: Make the existing system actually work correctly.

- [x] Fix `groq_parser.py` inverted JSON logic (line 118: `is None` → `is not None`)
- [x] Fix `config.py` malformed spaCy model name (remove stray quote)
- [x] Fix `feedback_engine.py` syntax error on line 1
- [x] Fix `.gitignore` — add `.env`, `secrets.toml`, `logs/`, `*.pem`
- [x] Fix CORS — add localhost origins
- [x] Fix duplicate imports in `jd_matcher.py`, `resume_parser.py`
- [x] Fix `supabase_db.py` hard-coded job title
- [x] Fix version mismatch between config and main
- [x] Add missing `__init__.py` files
- [x] Fix grammar bonus to not award points when grammar is unavailable

### PHASE 2: Backend Architecture Refactor

**Goal**: Clean separation of concerns, configurable scoring.

- [ ] Create `backend/core/scoring_config.py` — single source of truth for all weights
- [ ] Refactor `ats_scorer.py` to use configurable weights
- [ ] Create LLM provider abstraction (`backend/services/ai/`)
- [ ] Build deterministic fallback parser (regex + spaCy based)
- [ ] Create repository layer (`backend/repositories/`)
- [ ] Move business logic out of route handlers
- [ ] Integrate `recommendation_engine.py` into the pipeline (currently dead code)
- [ ] Add proper error handling with structured exceptions

### PHASE 3: Parsing & Scoring Engine Upgrade

**Goal**: Robust, evidence-based analysis without LLM dependency.

- [ ] Build deterministic resume section detector (regex + heading patterns)
- [ ] Build spaCy-based skill/keyword extractor
- [ ] Implement grammar analysis (language_tool_python or equivalent)
- [ ] Implement location/privacy detection (currently stubbed)
- [ ] Implement skill taxonomy with aliases
- [ ] Batch embedding operations
- [ ] Section-aware semantic similarity
- [ ] Evidence-based skill validation with confidence scores

### PHASE 4: AI Enhancement Layer

**Goal**: LLM-powered improvements that enhance but don't replace deterministic analysis.

- [ ] Resume improvement suggestions (before/after with evidence)
- [ ] AI bullet rewriting (with action verbs, metrics guidance)
- [ ] JD-targeted resume optimization
- [ ] Cover letter generation
- [ ] Interview question generation
- [ ] Career role recommendation

### PHASE 5: Resume Editor & Versioning

- [ ] Browser-based resume section editor
- [ ] Resume version management
- [ ] Side-by-side comparison view
- [ ] Auto-save and undo/redo
- [ ] Live ATS score preview

### PHASE 6: React Frontend

**Goal**: Professional SaaS-quality interface.

- [ ] Initialize Vite + React + TypeScript project
- [ ] Design system and component library
- [ ] Auth integration (Supabase client)
- [ ] Dashboard with charts (score trends, skill coverage)
- [ ] Upload with drag-and-drop
- [ ] Analysis results page with interactive components
- [ ] History with search, filter, pagination
- [ ] Responsive layouts, dark/light mode

### PHASE 7-10: Advanced Features & Production

- Analytics dashboard, job matching, career gap analysis
- Testing suite (pytest, TestClient, mocked LLM)
- Docker + docker-compose
- CI/CD with GitHub Actions
- Production documentation

## Migration Risks

1. **Supabase schema changes**: Adding columns to `analyses` table requires migration
2. **API breaking changes**: New endpoint structure needs frontend coordination
3. **Model loading time**: Adding more NLP models increases startup time
4. **LLM cost**: Multiple LLM calls per analysis can get expensive
5. **WeasyPrint system deps**: PDF generation requires Cairo/Pango on Linux

## Environment Variables Required

```env
# Required
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...  (service role)
SUPABASE_ANON_KEY=eyJ...  (public)
SUPABASE_JWT_SECRET=your-jwt-secret

# Optional (LLM enhancement)
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...

# Optional (customization)
SENTENCE_TRANSFORMER_MODEL=all-MiniLM-L6-v2
SPACY_MODEL=en_core_web_md
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8501
```
