"""
AI Enhancement Layer.

Provides bullet rewriting, tailored cover letter generation, and
interview preparation question generation with deterministic fallbacks.
"""
import re
import json
import logging
from typing import Dict, List, Optional

from backend.services.groq_parser import _get_client, _call_groq, _try_parse_json
from backend.services.skill_taxonomy import normalize_skill_name

logger = logging.getLogger('ats_resume_scorer')

STRONG_ACTION_VERBS = [
    "Spearheaded", "Architected", "Engineered", "Orchestrated", "Implemented",
    "Streamlined", "Accelerated", "Delivered", "Pioneered", "Automated",
    "Optimized", "Scaled", "Revamped", "Established", "Transformed",
]


def rewrite_bullet_point(
    bullet: str,
    target_role: Optional[str] = None,
    target_skill: Optional[str] = None,
) -> Dict[str, any]:
    """
    Rewrite a weak resume bullet point into an impactful, metrics-driven bullet.
    Strategy: Try Groq LLM first, fall back to deterministic pattern rewriting.
    """
    clean_bullet = bullet.strip().lstrip("•-*◦ \t")
    client = _get_client()

    if client is not None:
        try:
            prompt = f"""You are an executive resume coach and ATS optimization expert.
Rewrite the following resume bullet point to make it compelling, action-oriented, and quantified.
Role context: {target_role or 'Software Professional'}
Target skill: {target_skill or 'general technical competence'}

Original Bullet:
"{clean_bullet}"

Return ONLY a JSON object with this schema:
{{
  "rewritten_bullet": "Strong rewritten bullet starting with powerful past-tense action verb and measurable result",
  "action_verb": "Action verb used",
  "critique": "1-2 sentences on what was weak about original",
  "suggested_metrics": ["e.g. latency reduced by X%", "e.g. scaled to Y active users"]
}}
"""
            response = _call_groq(
                client,
                "You are an expert resume writer. Output ONLY valid JSON.",
                prompt
            )
            parsed = _try_parse_json(response)
            if parsed and parsed.get("rewritten_bullet"):
                return {
                    "original": clean_bullet,
                    "rewritten": parsed.get("rewritten_bullet"),
                    "action_verb": parsed.get("action_verb", "Implemented"),
                    "critique": parsed.get("critique", "Replaced passive phrasing with active ownership."),
                    "suggested_metrics": parsed.get("suggested_metrics", ["percentage improvement", "scale of impact"]),
                    "_source": "llm",
                }
        except Exception as exc:
            logger.warning(f"LLM bullet rewrite failed: {exc} — using fallback")

    # Deterministic fallback bullet rewriter
    return _rewrite_bullet_deterministic(clean_bullet, target_skill)


def _rewrite_bullet_deterministic(bullet: str, target_skill: Optional[str] = None) -> Dict[str, any]:
    """Pattern-based rewriting when LLM is unavailable."""
    words = bullet.split()
    first_word = words[0] if words else "Contributed"

    # Pick a strong replacement verb
    chosen_verb = "Engineered" if "code" in bullet.lower() or "built" in bullet.lower() else "Spearheaded"
    if "helped" in bullet.lower() or "responsible for" in bullet.lower():
        critique = "Original used passive language ('helped' or 'responsible for'). ATS filters favor direct ownership."
    else:
        critique = "Original lacked measurable scale and strong action verbs."

    skill_clause = f" utilizing {target_skill}" if target_skill else ""
    # Strip weak prefixes
    stripped = re.sub(r'^(?:responsible for|worked on|helped with|assisted in|involved in)\s+', '', bullet, flags=re.IGNORECASE)

    rewritten = f"{chosen_verb} {stripped.lower()}{skill_clause}, improving system reliability and performance by 25%."

    return {
        "original": bullet,
        "rewritten": rewritten,
        "action_verb": chosen_verb,
        "critique": critique,
        "suggested_metrics": [
            "latency or execution time reduction (e.g. 30%)",
            "volume of data/requests handled (e.g. 100k daily requests)",
            "team velocity or hours saved per sprint",
        ],
        "_source": "deterministic",
    }


def generate_cover_letter(
    candidate_name: str,
    skills: List[str],
    experience_highlights: List[str],
    job_title: str,
    company_name: str,
    job_description: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a tailored 3-paragraph cover letter connecting candidate skills to the JD.
    """
    client = _get_client()

    top_skills_str = ", ".join(skills[:5]) if skills else "modern software engineering practices"
    first_exp = experience_highlights[0] if experience_highlights else "delivering robust software solutions"

    if client is not None:
        try:
            prompt = f"""Write a professional, compelling cover letter for:
Candidate: {candidate_name}
Target Role: {job_title} at {company_name}
Key Skills: {top_skills_str}
Top Experience: {first_exp}
Job Description summary: {job_description[:1000] if job_description else 'N/A'}

Format requirements:
- Exactly 3 paragraphs:
  1. Strong opening hook stating interest in {company_name} and alignment with {job_title}.
  2. Concrete demonstration of technical achievements using {top_skills_str}.
  3. Enthusiastic closing with call to action.
- Professional, authentic tone (not robotic or clichéd).
"""
            content = _call_groq(
                client,
                "You are an executive career advisor writing a bespoke cover letter.",
                prompt
            )
            if content and len(content) > 100:
                return {
                    "cover_letter": content.strip(),
                    "_source": "llm",
                }
        except Exception as exc:
            logger.warning(f"LLM cover letter generation failed: {exc} — using fallback")

    # Deterministic fallback template
    letter = f"""Dear Hiring Team at {company_name},

I am writing to express my strong enthusiasm for the {job_title} position at {company_name}. With hands-on experience in {top_skills_str}, I have built a track record of architecting scalable systems and delivering measurable impact.

In my recent experience, I focused on {first_exp}. My background aligns directly with the challenges your team is tackling, particularly in creating high-quality, maintainable solutions and collaborating across cross-functional teams to exceed product objectives.

I would welcome the opportunity to discuss how my technical expertise in {top_skills_str} and dedication to continuous improvement can contribute to {company_name}'s ongoing success. Thank you for your time and consideration.

Sincerely,
{candidate_name or 'The Candidate'}"""

    return {
        "cover_letter": letter,
        "_source": "deterministic",
    }


def generate_interview_prep(
    skills: List[str],
    job_title: Optional[str] = None,
    unvalidated_skills: Optional[List[str]] = None,
) -> Dict[str, any]:
    """
    Generate role-specific technical and behavioral interview preparation questions.
    """
    target = job_title or "Software Engineer"
    key_skills = skills[:4] if skills else ["Python", "System Design", "Databases"]

    tech_questions = [
        {
            "skill": s,
            "question": f"Can you describe an architectural challenge you encountered when scaling applications using {s}, and how you resolved it?",
            "what_to_highlight": f"Discuss trade-offs, concurrency, caching, and testing strategies specific to {s}.",
        }
        for s in key_skills
    ]

    behavioral_questions = [
        {
            "category": "Impact & Leadership",
            "question": "Tell me about a project where technical requirements were ambiguous. How did you define scope and align stakeholders?",
            "star_framework_tip": "Situation: context. Task: your specific role. Action: technical decisions taken. Result: metric or operational win.",
        },
        {
            "category": "Handling Incidents",
            "question": "Describe a production outage or critical bug you investigated under pressure. What was the post-mortem outcome?",
            "star_framework_tip": "Focus on root cause analysis, prevention safeguards, and clear communication under pressure.",
        },
    ]

    gap_tips = []
    if unvalidated_skills:
        for u in unvalidated_skills[:3]:
            gap_tips.append(
                f"Prepare a concise STAR example for '{u}' since your resume lists it without explicit project context."
            )

    return {
        "target_role": target,
        "technical_questions": tech_questions,
        "behavioral_questions": behavioral_questions,
        "unvalidated_skill_tips": gap_tips,
    }
