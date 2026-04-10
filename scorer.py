"""
Job Scorer -- 10-Dimension A-F Scoring
========================================
Scores jobs across 10 weighted dimensions (A-F) using local Ollama.
Falls back to Gemini if Ollama isn't running.

Run `ollama create job-scorer -f Modelfile` once before first use.
"""

import json
import logging
import time
import requests
import config

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# MODEL CONFIG
# -------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
CUSTOM_MODEL = "job-scorer"
FALLBACK_MODEL = "qwen2.5:7b"

GEMINI_AVAILABLE = False
try:
    from google import genai
    if config.GEMINI_API_KEY and not config.GEMINI_API_KEY.startswith("your_"):
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
except ImportError:
    pass


def _check_ollama() -> tuple[bool, str]:
    """Check Ollama and determine which model to use."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            model_names = [m.split(":")[0] for m in models]
            if CUSTOM_MODEL in model_names:
                logger.info(f"Using custom model: {CUSTOM_MODEL}")
                return True, CUSTOM_MODEL
            if FALLBACK_MODEL.split(":")[0] in model_names:
                logger.warning(f"Custom model not found. Run: ollama create {CUSTOM_MODEL} -f Modelfile")
                return True, FALLBACK_MODEL
            return False, ""
    except Exception:
        return False, ""


USE_OLLAMA, OLLAMA_MODEL = _check_ollama()

if USE_OLLAMA:
    logger.info(f"Scoring engine: LOCAL ({OLLAMA_MODEL}) -- no rate limits")
elif GEMINI_AVAILABLE:
    logger.info("Scoring engine: GEMINI API")
else:
    logger.error("No scoring engine available.")

# -------------------------------------------------------------------
# GRADE WEIGHTS (how much each dimension matters for final score)
# -------------------------------------------------------------------
DIMENSION_WEIGHTS = {
    "role_match": 2.0,       # Most important -- is this actually a PM role?
    "seniority_fit": 1.5,    # Right level for you?
    "domain_match": 1.5,     # Industry overlap?
    "technical_fit": 1.3,    # Skills match?
    "leadership_fit": 0.8,   # Team scale match?
    "location_fit": 1.0,     # Location works?
    "growth_potential": 0.7,  # Career growth?
    "company_quality": 0.5,  # Company reputation?
    "compensation_signal": 0.4,  # Pay reasonable?
    "requirements_gap": 1.3,  # Hard gaps?
}

GRADE_TO_SCORE = {"A": 10, "B": 8, "C": 6, "D": 4, "E": 2, "F": 0}


def _grade_to_numeric(grade: str) -> float:
    """Convert A-F grade (with optional +/-) to numeric."""
    grade = grade.strip().upper()
    base = grade[0] if grade else "C"
    score = GRADE_TO_SCORE.get(base, 5)
    if "+" in grade:
        score += 1
    elif "-" in grade:
        score -= 1
    return max(0, min(10, score))


def _calculate_weighted_score(dimensions: dict) -> float:
    """Calculate weighted average from dimension grades."""
    total_weight = 0
    total_score = 0

    for dim, weight in DIMENSION_WEIGHTS.items():
        grade = dimensions.get(dim, "C")
        score = _grade_to_numeric(grade)
        total_score += score * weight
        total_weight += weight

    if total_weight == 0:
        return 5.0

    return round(total_score / total_weight, 1)


# -------------------------------------------------------------------
# PRE-FILTER
# -------------------------------------------------------------------
REJECT_KEYWORDS = [
    "nurse", "nursing", "registered nurse", "lpn", "rn ",
    "physician", "surgeon", "dentist", "pharmacist",
    "truck driver", "cdl", "forklift", "warehouse associate",
    "janitor", "custodian", "housekeeper",
    "hair stylist", "barber", "esthetician",
    "cashier", "barista", "server", "bartender",
    "security guard", "correctional officer",
    "electrician", "plumber", "hvac", "welder",
    "teacher", "substitute teacher", "tutor",
    "veterinary", "vet tech",
    "real estate agent", "loan officer", "mortgage",
    "insurance agent", "claims adjuster",
    "mechanical engineer", "civil engineer", "chemical engineer",
    "devops engineer", "site reliability", "sre ",
    "frontend developer", "backend developer", "full stack developer",
    "machine learning engineer", "ml engineer",
    # Guardrail traps
    "production manager", "production lead", "production supervisor",
    "product support manager", "customer success manager",
]

REQUIRE_KEYWORDS = [
    "product", "analyst", "business analyst", "solution architect",
    "program manager", "project manager", "scrum master",
    "data analyst", "strategy", "operations",
]


def pre_filter(jobs: list[dict]) -> list[dict]:
    """Fast keyword filter."""
    kept = []
    filtered = 0
    for job in jobs:
        title_lower = job["title"].lower()
        desc_lower = job.get("description", "").lower()[:500]
        combined = title_lower + " " + desc_lower
        if any(kw in title_lower for kw in REJECT_KEYWORDS):
            filtered += 1
            continue
        if any(kw in title_lower for kw in REQUIRE_KEYWORDS):
            kept.append(job)
            continue
        if any(kw in combined for kw in REQUIRE_KEYWORDS):
            kept.append(job)
        else:
            filtered += 1
    logger.info(f"Pre-filter: {len(kept)} kept, {filtered} removed")
    return kept


# -------------------------------------------------------------------
# SCORING PROMPTS
# -------------------------------------------------------------------

# For custom model (Modelfile has system prompt with all rules)
SIMPLE_PROMPT = """Score this job posting across all 10 dimensions. Return ONLY JSON.

Title: {title}
Company: {company}
Location: {location}
Description:
{description}"""

# For base model / Gemini (no Modelfile context)
FULL_PROMPT = """You are a career strategist. Score this job for the candidate below across 10 dimensions (A-F).

CANDIDATE: 10+ yrs PM/Data Strategy/BA. Domains: AgTech (AI/ML), Telecom/Supply Chain, GIS. Skills: VLM, NLP, MLOps, SQL, Snowflake, Tableau. Led 75+ team. Kellogg PM cert. Atlanta GA.

DIMENSIONS (score each A-F):
1. role_match: Software/digital PM/PO role? (Program/Project Mgr = D-E)
2. seniority_fit: Right level? (Mid/Sr = A-B, Principal = C-D, VP = E-F)
3. domain_match: Industry? (AgTech/Supply Chain/Telecom/GIS = A-B, Gaming/Fitness/AdTech = E-F)
4. technical_fit: Skills match? (AI/ML/Data/SQL = A-B, pure eng = D-E)
5. leadership_fit: Team scope match?
6. location_fit: Atlanta/Remote-US = A-B, relocation = D-E
7. growth_potential: Career growth?
8. company_quality: Brand/funding?
9. compensation_signal: Pay reasonable?
10. requirements_gap: Hard gaps? (required domain exp = E-F)

GUARDRAILS (apply BEFORE scoring):
- PHYSICAL PRODUCT: If JD mentions formulation/manufacturing/R&D/packaging/ingredients/beverage/food science = NOT software PM. Cap 4.
- PRODUCT SUPPORT/CUSTOMER SUCCESS in title = not PM. Cap 4.
- PRODUCT MARKETING in title = different track. Cap 6.
- PRODUCTION MANAGER = factory ops. Cap 3.
- Score the ROLE not the company brand. Weak role at great company = still weak.
- "Remote - EMEA/Europe/APAC/UK" = not US-remote. Cap 3.
- "Hybrid" outside Georgia = requires relocation. Cap 5.
- JD says "15+ years"/"P&L ownership"/"executive leadership" but title says PM = VP in disguise. Cap 5.

Return ONLY JSON:
{{"dimensions": {{"role_match": "A", "seniority_fit": "B", "domain_match": "A", "technical_fit": "A", "leadership_fit": "B", "location_fit": "A", "growth_potential": "B", "company_quality": "B", "compensation_signal": "C", "requirements_gap": "B"}}, "overall_grade": "B+", "overall_score": 8, "fit_reason": "<specific reason>", "seniority": "<level>", "key_skills": ["s1","s2","s3"], "requires_cover_letter": false}}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

JSON only:"""


# -------------------------------------------------------------------
# SCORING FUNCTIONS
# -------------------------------------------------------------------

def _score_with_ollama(prompt: str) -> str | None:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500, "num_ctx": 4096},
            },
            timeout=300,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        return None
    except Exception as e:
        logger.warning(f"Ollama error: {e}")
        return None


def _score_with_gemini(prompt: str) -> str | None:
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt)
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini error: {e}")
        return None


def _parse_response(text: str, job: dict) -> dict | None:
    """Parse 10-dimension JSON response."""
    text = text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

    try:
        result = json.loads(text)

        dimensions = result.get("dimensions", {})

        # Calculate weighted score if model didn't provide one
        if dimensions:
            calculated_score = _calculate_weighted_score(dimensions)
            # Use model's score if provided, otherwise use calculated
            model_score = result.get("overall_score", 0)
            # Average model and calculated to get best of both
            if model_score > 0:
                final_score = round((model_score + calculated_score) / 2, 1)
            else:
                final_score = calculated_score
        else:
            final_score = result.get("overall_score", result.get("score", 0))

        job["score"] = final_score
        job["overall_grade"] = result.get("overall_grade", "")
        job["dimensions"] = dimensions
        job["fit_reason"] = result.get("fit_reason", "")
        job["seniority"] = result.get("seniority", "unclear")
        job["key_skills"] = result.get("key_skills", [])
        job["requires_cover_letter"] = result.get("requires_cover_letter", False)

        # Build dimension summary for Notion
        if dimensions:
            dim_parts = []
            for dim, grade in dimensions.items():
                short = dim.replace("_", " ").title()
                dim_parts.append(f"{short}: {grade}")
            job["dimension_summary"] = " | ".join(dim_parts)
        else:
            job["dimension_summary"] = ""

        # Determine action
        if job["score"] >= config.AUTO_APPLY_MIN:
            job["action"] = "auto_apply"
        elif job["score"] >= config.FLAG_MIN:
            job["action"] = "flag_for_review"
        else:
            job["action"] = "skip"

        return job

    except json.JSONDecodeError:
        return None


def score_job(job: dict) -> dict | None:
    """Score a single job using best available engine."""
    if USE_OLLAMA and OLLAMA_MODEL == CUSTOM_MODEL:
        prompt = SIMPLE_PROMPT.format(
            title=job["title"], company=job["company"],
            location=job["location"], description=job["description"][:1500])
    else:
        prompt = FULL_PROMPT.format(
            title=job["title"], company=job["company"],
            location=job["location"], description=job["description"][:1500])

    if USE_OLLAMA:
        text = _score_with_ollama(prompt)
        if text:
            result = _parse_response(text, job)
            if result:
                return result
            text = _score_with_ollama(prompt + "\n\nReturn ONLY a JSON object.")
            if text:
                result = _parse_response(text, job)
                if result:
                    return result

    if GEMINI_AVAILABLE:
        gemini_prompt = FULL_PROMPT.format(
            title=job["title"], company=job["company"],
            location=job["location"], description=job["description"][:1500])
        text = _score_with_gemini(gemini_prompt)
        if text:
            return _parse_response(text, job)

    return None


# -------------------------------------------------------------------
# SCORED URL TRACKING
# -------------------------------------------------------------------
SCORED_URLS_FILE = "scored_urls.txt"

def _load_scored_urls() -> set:
    try:
        with open(SCORED_URLS_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def _save_scored_url(url: str):
    with open(SCORED_URLS_FILE, "a") as f:
        f.write(url + "\n")


# -------------------------------------------------------------------
# MAIN PIPELINE
# -------------------------------------------------------------------

def score_and_filter(jobs: list[dict]) -> list[dict]:
    """Pre-filter, skip already-scored, then score with 10 dimensions."""
    logger.info(f"Pre-filtering {len(jobs)} jobs...")
    jobs = pre_filter(jobs)

    if not jobs:
        logger.info("No jobs survived pre-filter.")
        return []

    already_scored = _load_scored_urls()
    unscored = [j for j in jobs if j["url"] not in already_scored]
    logger.info(f"Already scored: {len(jobs) - len(unscored)}, new: {len(unscored)}")

    if not unscored:
        logger.info("All jobs already scored.")
        return []

    if not USE_OLLAMA:
        MAX_PER_RUN = 15
        if len(unscored) > MAX_PER_RUN:
            logger.info(f"Gemini mode: capping at {MAX_PER_RUN}")
            unscored = unscored[:MAX_PER_RUN]

    kept = []
    total = len(unscored)

    for i, job in enumerate(unscored, 1):
        logger.info(f"Scoring [{i}/{total}]: {job['title']} @ {job['company']}")
        result = score_job(job)
        _save_scored_url(job["url"])

        if result and result["action"] != "skip":
            kept.append(result)
            grade = result.get("overall_grade", "")
            dims = result.get("dimensions", {})
            role = dims.get("role_match", "?")
            domain = dims.get("domain_match", "?")
            level = dims.get("seniority_fit", "?")
            logger.info(f"  -> {result['score']}/10 ({grade}) Role:{role} Domain:{domain} Level:{level} -> {result['action']}")
        elif result:
            logger.info(f"  -> {result['score']}/10 -> skipped")
        else:
            logger.info(f"  -> scoring failed, skipping")

        if not USE_OLLAMA:
            time.sleep(8)

    kept.sort(key=lambda j: j["score"], reverse=True)
    logger.info(f"Kept {len(kept)}/{total} jobs")
    return kept
