"""
Job Scorer -- Local Ollama + Gemini Fallback
=============================================
Uses a local Ollama model for scoring (zero rate limits).
Falls back to Gemini API if Ollama isn't running.

IMPORTANT: Edit CANDIDATE_PROFILE below to match YOUR background.
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
OLLAMA_MODEL = "qwen2.5:7b"  # Change to "llama3.2:3b" if too slow on your hardware

# Gemini fallback
GEMINI_AVAILABLE = False
try:
    from google import genai
    if config.GEMINI_API_KEY and not config.GEMINI_API_KEY.startswith("your_"):
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
except ImportError:
    pass


def _check_ollama() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            for m in models:
                if OLLAMA_MODEL.split(":")[0] in m:
                    logger.info(f"Ollama running with model: {m}")
                    return True
            logger.warning(f"Ollama running but '{OLLAMA_MODEL}' not found. Available: {models}")
            logger.warning(f"Run: ollama pull {OLLAMA_MODEL}")
            return False
    except Exception:
        return False


USE_OLLAMA = _check_ollama()

if USE_OLLAMA:
    logger.info("Scoring engine: LOCAL (Ollama) -- no rate limits")
elif GEMINI_AVAILABLE:
    logger.info("Scoring engine: GEMINI API (Ollama not running) -- rate limits apply")
else:
    logger.error("No scoring engine available. Install Ollama or configure Gemini API.")

# -------------------------------------------------------------------
# PRE-FILTER: Skip obviously irrelevant jobs before scoring
# -------------------------------------------------------------------

# Add keywords for roles you definitely DON'T want
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
]

# Keywords that signal a relevant job
REQUIRE_KEYWORDS = [
    "product", "analyst", "business analyst", "solution architect",
    "program manager", "project manager", "scrum master",
    "data analyst", "strategy", "operations",
]


def pre_filter(jobs: list[dict]) -> list[dict]:
    """Fast keyword filter to remove obviously irrelevant jobs."""
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
# CANDIDATE PROFILE -- EDIT THIS TO MATCH YOUR BACKGROUND
# -------------------------------------------------------------------
# This is the context the AI uses to score each job against your fit.
# Be specific: include your actual titles, skills, domains, and education.

CANDIDATE_PROFILE = """
- YOUR YEARS of experience in YOUR FIELD
- Current/recent title: YOUR TITLE
- Domains: YOUR INDUSTRIES
- Technical skills: YOUR KEY SKILLS
- Leadership: YOUR LEADERSHIP EXPERIENCE
- Education: YOUR DEGREES AND CERTS
- Location: YOUR CITY, STATE (and remote preference)
"""

# -------------------------------------------------------------------
# SCORING PROMPT -- Customize scoring criteria if needed
# -------------------------------------------------------------------

SCORING_PROMPT = """You are a career strategist evaluating job fit for a specific candidate.

CANDIDATE PROFILE:
{candidate_profile}

Evaluate this job posting and return ONLY valid JSON (no markdown, no backticks, no explanation):

{{"score": <1-10>, "fit_reason": "<1 sentence>", "seniority": "<junior/mid/senior/unclear>", "key_skills": ["skill1", "skill2", "skill3"], "requires_cover_letter": <true/false>}}

Scoring guide:
- 9-10: Strong match on role, level, skills, and domain
- 7-8:  Good match on most criteria, minor gaps
- 5-6:  Adjacent role or partial match
- 3-4:  Weak match, wrong level, or mostly unrelated
- 1-2:  Irrelevant

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

Return ONLY the JSON object. Nothing else."""


# -------------------------------------------------------------------
# SCORING FUNCTIONS
# -------------------------------------------------------------------

def _score_with_ollama(prompt: str) -> str | None:
    """Call local Ollama model."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300,
                },
            },
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        else:
            logger.warning(f"Ollama returned {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Ollama error: {e}")
        return None


def _score_with_gemini(prompt: str) -> str | None:
    """Call Gemini API as fallback."""
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower():
            logger.warning(f"Gemini rate limited: {e}")
        else:
            logger.warning(f"Gemini error: {e}")
        return None


def _parse_score_response(text: str, job: dict) -> dict | None:
    """Parse JSON response and attach score fields to the job."""
    text = text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

    try:
        result = json.loads(text)
        job["score"] = result.get("score", 0)
        job["fit_reason"] = result.get("fit_reason", "")
        job["seniority"] = result.get("seniority", "unclear")
        job["key_skills"] = result.get("key_skills", [])
        job["requires_cover_letter"] = result.get("requires_cover_letter", False)

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
    """Score a single job using Ollama (primary) or Gemini (fallback)."""
    prompt = SCORING_PROMPT.format(
        candidate_profile=CANDIDATE_PROFILE,
        title=job["title"],
        company=job["company"],
        location=job["location"],
        description=job["description"][:2500],
    )

    if USE_OLLAMA:
        text = _score_with_ollama(prompt)
        if text:
            result = _parse_score_response(text, job)
            if result:
                return result
            # Retry once with stricter instruction
            text = _score_with_ollama(prompt + "\n\nIMPORTANT: Return ONLY a JSON object, nothing else.")
            if text:
                result = _parse_score_response(text, job)
                if result:
                    return result

    if GEMINI_AVAILABLE:
        text = _score_with_gemini(prompt)
        if text:
            return _parse_score_response(text, job)

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
# MAIN SCORING PIPELINE
# -------------------------------------------------------------------

def score_and_filter(jobs: list[dict]) -> list[dict]:
    """Pre-filter, skip already-scored, then score. Returns sorted by score desc."""

    logger.info(f"Pre-filtering {len(jobs)} jobs by keyword relevance...")
    jobs = pre_filter(jobs)

    if not jobs:
        logger.info("No jobs survived pre-filter.")
        return []

    already_scored = _load_scored_urls()
    unscored = [j for j in jobs if j["url"] not in already_scored]
    logger.info(f"Already scored: {len(jobs) - len(unscored)}, new to score: {len(unscored)}")

    if not unscored:
        logger.info("All jobs already scored in previous runs.")
        return []

    # Cap per run only for Gemini (rate limits)
    if not USE_OLLAMA:
        MAX_PER_RUN = 15
        if len(unscored) > MAX_PER_RUN:
            logger.info(f"Gemini mode: capping at {MAX_PER_RUN} jobs (had {len(unscored)})")
            unscored = unscored[:MAX_PER_RUN]

    kept = []
    total = len(unscored)

    for i, job in enumerate(unscored, 1):
        logger.info(f"Scoring [{i}/{total}]: {job['title']} @ {job['company']}")
        result = score_job(job)

        _save_scored_url(job["url"])

        if result and result["action"] != "skip":
            kept.append(result)
            logger.info(f"  -> {result['score']}/10 -> {result['action']}")
        elif result:
            logger.info(f"  -> {result['score']}/10 -> skipped")
        else:
            logger.info(f"  -> scoring failed, skipping")

        if not USE_OLLAMA:
            time.sleep(8)

    kept.sort(key=lambda j: j["score"], reverse=True)
    logger.info(f"Kept {len(kept)}/{total} jobs (auto_apply + flag_for_review)")
    return kept
