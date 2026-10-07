"""
Skill Taxonomy and Alias Normalization Engine.

Maps variations, acronyms, and abbreviations to canonical skill names,
categorizes skills, and matches skills across resumes and job descriptions.
"""
import re
from typing import Dict, List, Optional, Set, Tuple


# Canonical skill database categorized by technical domains
SKILL_TAXONOMY: Dict[str, Dict[str, any]] = {
    # ── Programming Languages ──
    "python": {"canonical": "Python", "category": "Languages", "aliases": ["python3", "py"]},
    "javascript": {"canonical": "JavaScript", "category": "Languages", "aliases": ["js", "es6", "ecmascript"]},
    "typescript": {"canonical": "TypeScript", "category": "Languages", "aliases": ["ts"]},
    "java": {"canonical": "Java", "category": "Languages", "aliases": ["java 8", "java 11", "java 17", "java 21", "core java"]},
    "c++": {"canonical": "C++", "category": "Languages", "aliases": ["cpp", "c plus plus"]},
    "c#": {"canonical": "C#", "category": "Languages", "aliases": ["c sharp", "csharp", ".net c#"]},
    "golang": {"canonical": "Go", "category": "Languages", "aliases": ["go", "golang"]},
    "rust": {"canonical": "Rust", "category": "Languages", "aliases": []},
    "ruby": {"canonical": "Ruby", "category": "Languages", "aliases": ["ruby on rails", "ror"]},
    "php": {"canonical": "PHP", "category": "Languages", "aliases": ["php7", "php8"]},
    "swift": {"canonical": "Swift", "category": "Languages", "aliases": []},
    "kotlin": {"canonical": "Kotlin", "category": "Languages", "aliases": []},
    "sql": {"canonical": "SQL", "category": "Languages", "aliases": ["structured query language", "t-sql", "pl/sql"]},
    "r": {"canonical": "R", "category": "Languages", "aliases": ["r programming", "r language"]},
    "bash": {"canonical": "Bash / Shell", "category": "Languages", "aliases": ["shell script", "shell scripting", "sh", "zsh", "powershell"]},

    # ── Frontend Frameworks & Libraries ──
    "react": {"canonical": "React", "category": "Frontend", "aliases": ["react.js", "reactjs", "react native"]},
    "next.js": {"canonical": "Next.js", "category": "Frontend", "aliases": ["nextjs", "next"]},
    "vue": {"canonical": "Vue.js", "category": "Frontend", "aliases": ["vue.js", "vuejs", "vue3", "vue2"]},
    "angular": {"canonical": "Angular", "category": "Frontend", "aliases": ["angular.js", "angularjs", "angular 2+"]},
    "svelte": {"canonical": "Svelte", "category": "Frontend", "aliases": ["sveltekit"]},
    "html": {"canonical": "HTML5", "category": "Frontend", "aliases": ["html", "html5"]},
    "css": {"canonical": "CSS3", "category": "Frontend", "aliases": ["css", "css3"]},
    "tailwind": {"canonical": "Tailwind CSS", "category": "Frontend", "aliases": ["tailwind css", "tailwindcss"]},
    "sass": {"canonical": "Sass / SCSS", "category": "Frontend", "aliases": ["scss", "sass"]},
    "redux": {"canonical": "Redux", "category": "Frontend", "aliases": ["redux toolkit", "rtk"]},

    # ── Backend Frameworks ──
    "fastapi": {"canonical": "FastAPI", "category": "Backend", "aliases": ["fast-api"]},
    "flask": {"canonical": "Flask", "category": "Backend", "aliases": []},
    "django": {"canonical": "Django", "category": "Backend", "aliases": ["django rest framework", "drf"]},
    "node.js": {"canonical": "Node.js", "category": "Backend", "aliases": ["nodejs", "node"]},
    "express": {"canonical": "Express.js", "category": "Backend", "aliases": ["express.js", "expressjs"]},
    "spring": {"canonical": "Spring Boot", "category": "Backend", "aliases": ["spring boot", "spring framework", "spring-boot"]},
    "nest.js": {"canonical": "NestJS", "category": "Backend", "aliases": ["nestjs", "nest"]},
    "asp.net": {"canonical": "ASP.NET Core", "category": "Backend", "aliases": ["asp.net core", ".net core", "dotnet"]},
    "graphql": {"canonical": "GraphQL", "category": "Backend", "aliases": ["apollo graphql"]},
    "rest api": {"canonical": "REST API", "category": "Backend", "aliases": ["restful api", "rest apis", "rest", "restful web services"]},
    "grpc": {"canonical": "gRPC", "category": "Backend", "aliases": ["protobuf", "protocol buffers"]},
    "microservices": {"canonical": "Microservices", "category": "Backend", "aliases": ["microservice architecture", "distributed systems"]},

    # ── Databases & Storage ──
    "postgresql": {"canonical": "PostgreSQL", "category": "Database", "aliases": ["postgres", "pgsql", "psql"]},
    "mysql": {"canonical": "MySQL", "category": "Database", "aliases": []},
    "mongodb": {"canonical": "MongoDB", "category": "Database", "aliases": ["mongo"]},
    "redis": {"canonical": "Redis", "category": "Database", "aliases": []},
    "elasticsearch": {"canonical": "Elasticsearch", "category": "Database", "aliases": ["elastic search", "elk", "opensearch"]},
    "sqlite": {"canonical": "SQLite", "category": "Database", "aliases": []},
    "dynamodb": {"canonical": "DynamoDB", "category": "Database", "aliases": ["amazon dynamodb"]},
    "cassandra": {"canonical": "Cassandra", "category": "Database", "aliases": ["apache cassandra"]},
    "snowflake": {"canonical": "Snowflake", "category": "Database", "aliases": []},
    "supabase": {"canonical": "Supabase", "category": "Database", "aliases": []},
    "firebase": {"canonical": "Firebase", "category": "Database", "aliases": ["firestore"]},

    # ── Cloud & DevOps ──
    "docker": {"canonical": "Docker", "category": "DevOps", "aliases": ["containerization", "containers", "dockerfile", "docker-compose"]},
    "kubernetes": {"canonical": "Kubernetes", "category": "DevOps", "aliases": ["k8s", "k8", "k8-s"]},
    "aws": {"canonical": "Amazon Web Services (AWS)", "category": "Cloud", "aliases": ["amazon web services", "aws cloud", "ec2", "s3", "lambda", "ecs", "eks", "fargate"]},
    "gcp": {"canonical": "Google Cloud Platform (GCP)", "category": "Cloud", "aliases": ["google cloud", "google cloud platform", "cloud run", "gke"]},
    "azure": {"canonical": "Microsoft Azure", "category": "Cloud", "aliases": ["azure cloud", "microsoft azure"]},
    "terraform": {"canonical": "Terraform", "category": "DevOps", "aliases": ["iac", "infrastructure as code"]},
    "ansible": {"canonical": "Ansible", "category": "DevOps", "aliases": []},
    "ci/cd": {"canonical": "CI/CD", "category": "DevOps", "aliases": ["continuous integration", "continuous deployment", "ci cd", "cicd"]},
    "jenkins": {"canonical": "Jenkins", "category": "DevOps", "aliases": []},
    "github actions": {"canonical": "GitHub Actions", "category": "DevOps", "aliases": ["gha", "gh actions"]},
    "git": {"canonical": "Git", "category": "DevOps", "aliases": ["github", "gitlab", "bitbucket", "version control"]},
    "linux": {"canonical": "Linux", "category": "DevOps", "aliases": ["ubuntu", "debian", "redhat", "centos", "alpine"]},
    "kafka": {"canonical": "Apache Kafka", "category": "DevOps", "aliases": ["kafka", "message queue", "event-driven", "rabbitmq"]},

    # ── AI / ML / Data Science ──
    "machine learning": {"canonical": "Machine Learning", "category": "AI / ML", "aliases": ["ml", "machine-learning"]},
    "deep learning": {"canonical": "Deep Learning", "category": "AI / ML", "aliases": ["neural networks", "dl"]},
    "nlp": {"canonical": "Natural Language Processing (NLP)", "category": "AI / ML", "aliases": ["natural language processing", "text mining", "spacy", "nltk", "transformers", "huggingface", "llm", "large language models"]},
    "computer vision": {"canonical": "Computer Vision", "category": "AI / ML", "aliases": ["cv", "opencv", "image recognition"]},
    "pytorch": {"canonical": "PyTorch", "category": "AI / ML", "aliases": ["torch"]},
    "tensorflow": {"canonical": "TensorFlow", "category": "AI / ML", "aliases": ["tf", "keras"]},
    "scikit-learn": {"canonical": "Scikit-Learn", "category": "AI / ML", "aliases": ["sklearn", "scikit learn"]},
    "pandas": {"canonical": "Pandas", "category": "AI / ML", "aliases": []},
    "numpy": {"canonical": "NumPy", "category": "AI / ML", "aliases": []},
    "generative ai": {"canonical": "Generative AI", "category": "AI / ML", "aliases": ["genai", "prompt engineering", "langchain", "llamaindex", "rag", "retrieval augmented generation"]},

    # ── Testing & Quality ──
    "pytest": {"canonical": "Pytest", "category": "Testing", "aliases": ["python unittest"]},
    "jest": {"canonical": "Jest", "category": "Testing", "aliases": []},
    "cypress": {"canonical": "Cypress", "category": "Testing", "aliases": []},
    "selenium": {"canonical": "Selenium", "category": "Testing", "aliases": []},
    "junit": {"canonical": "JUnit", "category": "Testing", "aliases": []},
    "unit testing": {"canonical": "Unit Testing", "category": "Testing", "aliases": ["automated testing", "tdd", "test driven development", "integration testing"]},

    # ── Methodologies & Practices ──
    "agile": {"canonical": "Agile", "category": "Methodologies", "aliases": ["scrum", "kanban", "sprints"]},
    "system design": {"canonical": "System Design", "category": "Architecture", "aliases": ["distributed architecture", "high availability", "scalability", "load balancing"]},
    "clean code": {"canonical": "Software Engineering Best Practices", "category": "Methodologies", "aliases": ["solid principles", "design patterns", "refactoring", "code reviews"]},
}

# Build fast reverse-lookup map: alias_lower -> canonical_name
_ALIAS_LOOKUP: Dict[str, str] = {}
for key, data in SKILL_TAXONOMY.items():
    canonical = data["canonical"]
    _ALIAS_LOOKUP[key] = canonical
    _ALIAS_LOOKUP[canonical.lower()] = canonical
    for alias in data["aliases"]:
        _ALIAS_LOOKUP[alias.lower()] = canonical


def normalize_skill_name(skill: str) -> str:
    """
    Given any skill variation, return its canonical name if known;
    otherwise return cleanly capitalized skill.
    """
    cleaned = skill.strip().lower()
    if cleaned in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[cleaned]

    # Remove extra spaces/dashes for fuzzy canonical match
    compressed = re.sub(r'[\s\-_.]', '', cleaned)
    for alias, canonical in _ALIAS_LOOKUP.items():
        if re.sub(r'[\s\-_.]', '', alias) == compressed:
            return canonical

    # Return title-cased fallback if not in taxonomy
    return skill.strip()


def extract_skills_from_text(text: str) -> List[Dict[str, str]]:
    """
    Scan text using taxonomy patterns to extract all detected technical skills.
    Returns list of dicts: [{'name': 'PostgreSQL', 'category': 'Database', 'matched_as': 'postgres'}]
    """
    found: Dict[str, Dict[str, str]] = {}
    text_lower = text.lower()

    # Sort aliases by length descending so longer phrases match first (e.g. "React Native" before "React")
    all_terms = sorted(_ALIAS_LOOKUP.keys(), key=len, reverse=True)

    for term in all_terms:
        # Avoid single-letter false matches unless surrounded by punctuation/spaces
        if len(term) <= 2:
            pattern = r'(?:\b|(?<=[^a-zA-Z0-9]))' + re.escape(term) + r'(?:\b|(?=[^a-zA-Z0-9]))'
        else:
            pattern = r'\b' + re.escape(term) + r'\b'

        if re.search(pattern, text_lower):
            canonical = _ALIAS_LOOKUP[term]
            if canonical not in found:
                category = "General"
                # Find category
                for data in SKILL_TAXONOMY.values():
                    if data["canonical"] == canonical:
                        category = data["category"]
                        break

                found[canonical] = {
                    "name": canonical,
                    "category": category,
                    "matched_as": term,
                }

    return sorted(list(found.values()), key=lambda x: (x["category"], x["name"]))


def match_skills(resume_skills: List[str], jd_skills: List[str]) -> Dict[str, any]:
    """
    Compare resume skills against JD skills using canonical normalization.
    Returns matched, missing, and additional skill lists.
    """
    resume_canonical_map = {normalize_skill_name(s): s for s in resume_skills if s.strip()}
    jd_canonical_map = {normalize_skill_name(s): s for s in jd_skills if s.strip()}

    matched = []
    missing = []

    for canonical, original_jd in jd_canonical_map.items():
        if canonical in resume_canonical_map:
            matched.append({
                "skill": canonical,
                "resume_term": resume_canonical_map[canonical],
                "jd_term": original_jd,
            })
        else:
            missing.append({
                "skill": canonical,
                "jd_term": original_jd,
            })

    additional = [
        canonical for canonical in resume_canonical_map.keys()
        if canonical not in jd_canonical_map
    ]

    total_jd = len(jd_canonical_map)
    match_pct = round((len(matched) / total_jd * 100), 1) if total_jd > 0 else 100.0

    return {
        "matched": matched,
        "missing": missing,
        "additional": additional,
        "match_percentage": match_pct,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "total_required": total_jd,
    }
