"""
LLM-based resume and job description parsing.

Supports Groq as primary provider with a deterministic fallback parser
that uses regex + spaCy when no LLM API key is available.
"""
import os
import re
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger('ats_resume_scorer')

# ── LLM Client ──

GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

_client = None


def _get_client():
    """Lazy-init the Groq client. Returns None if no API key."""
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv('GROQ_API_KEY', '')
    if not api_key:
        return None
    try:
        from groq import Groq
        _client = Groq(api_key=api_key)
        return _client
    except Exception as exc:
        logger.warning(f'Failed to initialize Groq client: {exc}')
        return None


# ── Prompts ──

RESUME_SYSTEM_PROMPT = (
    "You are a resume parser. Extract information from the resume "
    "and return ONLY a valid JSON object. No explanation, no markdown."
)

RESUME_USER_PROMPT = """Extract the following from this resume and return as JSON:
{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "linkedin": "LinkedIn URL if present, otherwise null",
  "github": "GitHub URL if present, otherwise null",
  "professional_summary": "the full text of the Summary, Profile, About Me, Objective, or Professional Summary section at the top of the resume. Copy the ENTIRE paragraph exactly as written. If no such section exists, return an empty string.",
  "skills": ["list", "of", "skills"],
  "experience": [
    {{
      "job_title": "",
      "company": "",
      "start_date": "",
      "end_date": "",
      "duration_months": 0,
      "description": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "year": ""
    }}
  ],
  "certifications": ["list of certifications"],
  "projects": [
    {{
      "title": "project name",
      "description": "what the project does and how it was built",
      "technologies": ["tech", "used"]
    }}
  ],
  "action_verbs": ["strong action verbs used in bullet points, e.g. developed, implemented, designed"],
  "keywords": ["important keywords and phrases from the resume for ATS matching"]
}}

Important instructions:
- For duration_months, calculate the number of months between start_date and end_date. If end_date is "Present" or "Current", calculate from start_date to now.
- For skills, extract ALL technical and soft skills mentioned anywhere in the resume.
- For action_verbs, find verbs that start bullet points or describe achievements.
- For keywords, extract noun phrases and technical terms relevant to ATS matching.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Resume Text:
{raw_text}"""

JD_SYSTEM_PROMPT = (
    "You are a job description parser. Extract information and "
    "return ONLY a valid JSON object. No explanation, no markdown."
)

JD_USER_PROMPT = """Extract the following from this job description and return as JSON:
{{
  "job_title": "",
  "required_skills": ["list of must-have skills"],
  "preferred_skills": ["list of nice-to-have skills"],
  "experience_required": "",
  "education_required": "",
  "key_responsibilities": ["list of responsibilities"],
  "keywords": ["important keywords and phrases for ATS matching"]
}}

Important instructions:
- required_skills: skills explicitly stated as required or must-have.
- preferred_skills: skills stated as preferred, nice-to-have, or bonus.
- keywords: extract ALL important terms an ATS system would match against,
  including skills, technologies, certifications, and domain terms.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Job Description Text:
{raw_text}"""


# ── LLM Call ──

def _call_groq(client, system_prompt: str, user_prompt: str) -> str:
    """Make a chat completion request to Groq."""
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        temperature=0.0,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


def _try_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse JSON from LLM response, stripping markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ── Deterministic Fallback Parser ──

# Common section headings found in resumes
_SECTION_PATTERNS = {
    'experience': re.compile(
        r'^(?:work\s+)?experience|employment|work\s+history|professional\s+experience',
        re.IGNORECASE
    ),
    'education': re.compile(
        r'^education|academic|qualifications|degrees?',
        re.IGNORECASE
    ),
    'skills': re.compile(
        r'^(?:technical\s+)?skills|technologies|competenc|tools\s+(?:and|&)',
        re.IGNORECASE
    ),
    'projects': re.compile(
        r'^projects?|personal\s+projects?|academic\s+projects?',
        re.IGNORECASE
    ),
    'summary': re.compile(
        r'^(?:professional\s+)?summary|(?:career\s+)?objective|about\s+me|profile',
        re.IGNORECASE
    ),
    'certifications': re.compile(
        r'^certifications?|licenses?|credentials?',
        re.IGNORECASE
    ),
}

# Contact info extraction patterns
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_PHONE_RE = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')
_LINKEDIN_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?', re.IGNORECASE)
_GITHUB_RE = re.compile(r'(?:https?://)?(?:www\.)?github\.com/[\w-]+/?', re.IGNORECASE)

# Action verbs commonly found in resumes
_ACTION_VERBS = {
    'developed', 'built', 'designed', 'implemented', 'created', 'managed',
    'led', 'improved', 'optimized', 'deployed', 'automated', 'integrated',
    'established', 'maintained', 'reduced', 'increased', 'achieved',
    'delivered', 'analyzed', 'configured', 'migrated', 'architected',
    'collaborated', 'mentored', 'presented', 'published', 'launched',
    'streamlined', 'engineered', 'refactored', 'tested', 'debugged',
    'documented', 'coordinated', 'facilitated', 'spearheaded', 'pioneered',
    'orchestrated', 'transformed', 'revamped', 'standardized', 'consolidated',
}


def _detect_sections(text: str) -> Dict[str, str]:
    """Split resume text into named sections based on heading patterns."""
    lines = text.split('\n')
    sections: Dict[str, List[str]] = {}
    current_section = 'header'
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            sections.setdefault(current_section, []).append(line)
            continue

        # Check if line matches a section heading
        matched = False
        for section_name, pattern in _SECTION_PATTERNS.items():
            if pattern.search(stripped) and len(stripped) < 60:
                current_section = section_name
                sections.setdefault(current_section, [])
                matched = True
                break

        if not matched:
            sections.setdefault(current_section, []).append(line)

    return {k: '\n'.join(v).strip() for k, v in sections.items() if v}


def _extract_skills_deterministic(text: str) -> List[str]:
    """Extract skills from the skills section using common patterns."""
    # Look for comma-separated or pipe-separated skill lists
    skills = set()

    # Common tech skills to look for
    tech_terms = [
        'python', 'java', 'javascript', 'typescript', 'c\\+\\+', 'c#', 'ruby', 'go',
        'rust', 'swift', 'kotlin', 'php', 'scala', 'r', 'matlab',
        'react', 'angular', 'vue', 'next\\.js', 'node\\.js', 'express',
        'django', 'flask', 'fastapi', 'spring', 'spring boot',
        'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'terraform',
        'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
        'git', 'jenkins', 'ci/cd', 'linux', 'bash',
        'machine learning', 'deep learning', 'nlp', 'computer vision',
        'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy',
        'html', 'css', 'sass', 'tailwind', 'bootstrap',
        'rest api', 'graphql', 'grpc', 'microservices',
        'agile', 'scrum', 'jira', 'confluence',
        'sql', 'nosql', 'firebase', 'supabase',
    ]

    text_lower = text.lower()
    for term in tech_terms:
        if re.search(r'\b' + term + r'\b', text_lower):
            # Capitalize properly
            match = re.search(r'\b' + term + r'\b', text_lower)
            if match:
                original = text[match.start():match.end()]
                skills.add(original.strip())

    return sorted(skills)


def _extract_action_verbs(text: str) -> List[str]:
    """Find action verbs used at the start of bullet points or sentences."""
    found = set()
    for line in text.split('\n'):
        stripped = line.strip().lstrip('•-*◦').strip()
        if not stripped:
            continue
        first_word = stripped.split()[0].lower().rstrip('ed').rstrip('s')
        # Check against known action verbs (with flexible matching)
        for verb in _ACTION_VERBS:
            if stripped.lower().startswith(verb):
                found.add(verb.capitalize())
                break
    return sorted(found)


def _extract_keywords(text: str) -> List[str]:
    """Extract important keywords/noun phrases from text."""
    # Simple keyword extraction: capitalized multi-word phrases and tech terms
    keywords = set()

    # Find capitalized phrases (potential proper nouns / technologies)
    for match in re.finditer(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', text):
        phrase = match.group().strip()
        if 2 <= len(phrase) <= 40 and len(phrase.split()) <= 4:
            keywords.add(phrase)

    # Also pick up skills as keywords
    keywords.update(_extract_skills_deterministic(text))

    return sorted(keywords)[:50]


def parse_resume_deterministic(raw_text: str) -> Dict:
    """
    Deterministic resume parser — no LLM required.
    Uses regex, section detection, and pattern matching.
    """
    sections = _detect_sections(raw_text)

    # Contact info from header or full text
    header = sections.get('header', raw_text[:500])

    email_match = _EMAIL_RE.search(header) or _EMAIL_RE.search(raw_text[:1000])
    phone_match = _PHONE_RE.search(header) or _PHONE_RE.search(raw_text[:1000])
    linkedin_match = _LINKEDIN_RE.search(raw_text)
    github_match = _GITHUB_RE.search(raw_text)

    # Extract name (usually first non-empty line)
    name = ''
    for line in raw_text.split('\n'):
        stripped = line.strip()
        if stripped and not _EMAIL_RE.search(stripped) and not _PHONE_RE.search(stripped):
            if len(stripped) < 50 and not any(c.isdigit() for c in stripped[:5]):
                name = stripped
                break

    skills = _extract_skills_deterministic(raw_text)
    action_verbs = _extract_action_verbs(raw_text)
    keywords = _extract_keywords(raw_text)

    summary_text = sections.get('summary', '')

    result = {
        'name': name,
        'email': email_match.group() if email_match else None,
        'phone': phone_match.group() if phone_match else None,
        'linkedin': linkedin_match.group() if linkedin_match else None,
        'github': github_match.group() if github_match else None,
        'professional_summary': summary_text,
        'skills': skills,
        'experience': [],  # Basic extraction without LLM
        'education': [],
        'certifications': [],
        'projects': [],
        'action_verbs': action_verbs,
        'keywords': keywords,
        '_parsed_by': 'deterministic',
    }

    return result


# ── Validation ──

def _validate_resume_result(result: Optional[dict]) -> dict:
    """Ensure all expected fields exist with correct types."""
    if result is None:
        result = {}

    defaults = {
        'name': '',
        'email': None,
        'phone': None,
        'linkedin': None,
        'github': None,
        'professional_summary': '',
        'skills': [],
        'experience': [],
        'education': [],
        'certifications': [],
        'projects': [],
        'action_verbs': [],
        'keywords': [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        # Ensure list fields are actually lists
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    # Validate experience entries
    for exp in result.get('experience', []):
        if not isinstance(exp, dict):
            continue
        exp.setdefault('job_title', '')
        exp.setdefault('company', '')
        exp.setdefault('start_date', '')
        exp.setdefault('end_date', '')
        exp.setdefault('duration_months', 0)
        exp.setdefault('description', '')
        try:
            exp['duration_months'] = int(exp['duration_months'])
        except (ValueError, TypeError):
            exp['duration_months'] = 0

    # Validate project entries
    for proj in result.get('projects', []):
        if not isinstance(proj, dict):
            continue
        proj.setdefault('title', '')
        proj.setdefault('description', '')
        proj.setdefault('technologies', [])

    return result


def _validate_jd_result(result: Optional[dict]) -> dict:
    """Ensure all expected JD fields exist with correct types."""
    if result is None:
        result = {}

    defaults = {
        'job_title': '',
        'required_skills': [],
        'preferred_skills': [],
        'experience_required': '',
        'education_required': '',
        'key_responsibilities': [],
        'keywords': [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    return result


# ── Public API ──

def parse_resume(raw_text: str) -> Dict:
    """
    Parse a resume into structured JSON.

    Strategy:
    1. Try LLM parsing (Groq) if available
    2. Fall back to deterministic parsing if LLM unavailable or fails
    3. Merge: use deterministic extraction to fill gaps in LLM output
    """
    client = _get_client()

    # If no LLM available, use deterministic parser
    if client is None:
        logger.info('No LLM API key configured — using deterministic resume parser')
        result = parse_resume_deterministic(raw_text)
        return _validate_resume_result(result)

    # Try LLM parsing
    try:
        prompt = RESUME_USER_PROMPT.format(raw_text=raw_text[:8000])
        raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, prompt)
        result = _try_parse_json(raw_response)

        # FIX: Original had inverted logic (if result is None → validate None)
        if result is not None:
            result['_parsed_by'] = 'llm'
            return _validate_resume_result(result)

        # First attempt failed — retry with stricter prompt
        logger.warning('Groq resume parse: first attempt returned invalid JSON, retrying...')
        strict_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
            + prompt
        )
        raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, strict_prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            result['_parsed_by'] = 'llm_retry'
            return _validate_resume_result(result)

        # LLM failed both attempts — fall back to deterministic
        logger.warning('Groq returned unparseable JSON after retry — falling back to deterministic parser')
        result = parse_resume_deterministic(raw_text)
        result['_parsed_by'] = 'deterministic_fallback'
        return _validate_resume_result(result)

    except Exception as exc:
        logger.warning(f'LLM resume parsing failed: {exc} — falling back to deterministic parser')
        result = parse_resume_deterministic(raw_text)
        result['_parsed_by'] = 'deterministic_fallback'
        return _validate_resume_result(result)


def parse_job_description(raw_text: str) -> Dict:
    """
    Parse a job description into structured JSON.
    Falls back to basic keyword extraction if LLM is unavailable.
    """
    client = _get_client()

    if client is None:
        logger.info('No LLM API key — using deterministic JD parser')
        return _parse_jd_deterministic(raw_text)

    try:
        prompt = JD_USER_PROMPT.format(raw_text=raw_text[:8000])
        raw_response = _call_groq(client, JD_SYSTEM_PROMPT, prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            return _validate_jd_result(result)

        logger.warning('Groq JD parse: first attempt returned invalid JSON, retrying...')
        strict_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
            + prompt
        )
        raw_response = _call_groq(client, JD_SYSTEM_PROMPT, strict_prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            return _validate_jd_result(result)

        logger.warning('Groq JD parse failed after retry — falling back to deterministic')
        return _parse_jd_deterministic(raw_text)

    except Exception as exc:
        logger.warning(f'LLM JD parsing failed: {exc} — falling back to deterministic parser')
        return _parse_jd_deterministic(raw_text)


def _parse_jd_deterministic(raw_text: str) -> Dict:
    """Basic JD parsing using keyword extraction. No LLM needed."""
    skills = _extract_skills_deterministic(raw_text)
    keywords = _extract_keywords(raw_text)

    return _validate_jd_result({
        'job_title': '',
        'required_skills': skills,
        'preferred_skills': [],
        'experience_required': '',
        'education_required': '',
        'key_responsibilities': [],
        'keywords': keywords,
        '_parsed_by': 'deterministic',
    })
