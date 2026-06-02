import re
from typing import Optional
from bs4 import BeautifulSoup
from loguru import logger

# Pre-compiled patterns for performance
CLEAN_CHARS_PATTERN = re.compile(r'[^a-zA-Z0-9\s.#+\-(),:;]')
WHITESPACE_PATTERN = re.compile(r'\s+')
HTML_TAG_PATTERN = re.compile(r'<[^>]*?>')
URL_VALIDATION_PATTERN = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)
COMPANY_DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?([^/]+)')
DOMAIN_CLEANUP_PATTERN = re.compile(r'\.(com|org|net|edu|gov|io|co\.uk|co\.in)$')
JOB_SIGNAL_PATTERN = re.compile(
    r'\b(?:responsibilit(?:y|ies)|qualification(?:s)?|requirement(?:s)?|'
    r'experience|skill(?:s)?|role|position|candidate|engineer|developer|'
    r'apply|hiring|job)\b',
    re.IGNORECASE
)
GENERIC_ROLE_VALUES = {"unknown role", "position available", "untitled", "n/a", "none"}

def clean_text(text: str) -> str:
    """
    Clean and normalize text from web scraping using BeautifulSoup.
    
    Args:
        text: Raw text from webpage
        
    Returns:
        Cleaned text string
    """
    if not text or not isinstance(text, str):
        return ""
    
    try:
        # Use BeautifulSoup to parse HTML and handle edge cases
        soup = BeautifulSoup(text, "html.parser")
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
            
        # Get text and handle whitespace
        cleaned_text = soup.get_text(separator=' ')
        
        # Keep alphanumeric, spaces, and common tech symbols
        cleaned_text = CLEAN_CHARS_PATTERN.sub(' ', cleaned_text)
        
        # Normalize whitespace
        cleaned_text = WHITESPACE_PATTERN.sub(' ', cleaned_text)
        
        return cleaned_text.strip()
    except Exception as e:
        logger.error(f"Error cleaning text: {e}")
        # Fallback to basic regex cleaning if BS4 fails
        text = HTML_TAG_PATTERN.sub('', text)
        text = WHITESPACE_PATTERN.sub(' ', text)
        return text.strip()

def extract_skills_from_text(text: str) -> list:
    """
    Extract potential skills/technologies from text.
    """
    if not text:
        return []
    
    # Common tech skills patterns
    tech_patterns = [
        r'\b(?:Python|Java|JavaScript|React|Node\.js|Angular|Vue\.js|Django|Flask|Spring|Express)\b',
        r'\b(?:MySQL|PostgreSQL|MongoDB|Redis|SQLite|Oracle|SQL Server|MSSQL|BigQuery|InnoDB)\b',
        r'\b(?:AWS|Azure|GCP|Docker|Kubernetes|Git|GitHub|GitLab|Jenkins|CI/CD|Terraform|Ansible)\b',
        r'\b(?:SRE|DevOps|DataOps|Database Reliability|Monitoring|Grafana|Datadog|Automation)\b',
        r'\b(?:HTML|CSS|SCSS|SASS|Bootstrap|Tailwind|Material-UI|jQuery)\b',
        r'\b(?:Machine Learning|AI|Deep Learning|TensorFlow|PyTorch|Scikit-learn|Pandas|NumPy)\b',
        r'\b(?:REST|API|GraphQL|Microservices|Agile|Scrum|DevOps|Testing|TDD|BDD)\b'
    ]
    
    skills = []
    for pattern in tech_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        skills.extend(matches)
    
    return list(set(skills))

def validate_url(url: str) -> bool:
    """
    Validate if a URL is properly formatted.
    """
    if not url or not isinstance(url, str):
        return False
    
    return URL_VALIDATION_PATTERN.match(url) is not None

def validate_job_description(job: dict) -> tuple[bool, str]:
    """
    Validate that extracted job data is specific enough for generation.
    More permissive for modern job boards and fresher roles.
    """

    if not job or not isinstance(job, dict):
        return False, "No valid job was extracted from the page."

    role = str(job.get("role") or "").strip()
    description = str(job.get("description") or "").strip()

    skills = job.get("skills") if isinstance(job.get("skills"), list) else []
    clean_skills = [str(skill).strip() for skill in skills if str(skill).strip()]

    # Instead of failing, use defaults
    if not role or role.lower() in GENERIC_ROLE_VALUES:
        logger.warning("Role extraction failed. Using fallback role.")
        job["role"] = "Software Engineer"

    # Only fail if description is completely missing
    if len(description) < 30:
        return False, "Could not extract enough job information from the page."

    # Auto-extract skills if missing
    if not clean_skills:
        logger.warning("No skills found. Attempting automatic extraction.")
        clean_skills = extract_skills_from_text(description)
        job["skills"] = clean_skills

    return True, ""

def validate_skill_match(skills: list, matched_projects: list) -> tuple[bool, str]:
    """
    Require at least one portfolio project match before generation.
    """
    clean_skills = [str(skill).strip() for skill in skills if str(skill).strip()]
    if not clean_skills:
        return False, "No job skills were available for portfolio matching."

    if not matched_projects:
        return (
            False,
            "No portfolio project matches the extracted job skills. "
            "Update project_portfolio.csv or try a job that matches your portfolio."
        )

    return True, ""

def truncate_text(text: str, max_length: int = 1000) -> str:
    """
    Truncate text to maximum length.
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."

def format_job_description(job: dict) -> str:
    """
    Format job dictionary into readable string.
    """
    if not job or not isinstance(job, dict):
        return "No job information available"
    
    parts = []
    
    if job.get('role'):
        parts.append(f"Role: {job['role']}")
    
    if job.get('experience'):
        parts.append(f"Experience: {job['experience']}")
    
    if job.get('skills') and isinstance(job['skills'], list):
        skills_str = ', '.join(job['skills'])
        parts.append(f"Skills: {skills_str}")
    
    if job.get('description'):
        desc = truncate_text(job['description'], 500)
        parts.append(f"Description: {desc}")
    
    return '\n'.join(parts)

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing/replacing invalid characters.
    """
    if not filename:
        return "untitled"
    
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip('. ')
    
    if not filename:
        filename = "untitled"
    
    return filename

def extract_company_name(url: str) -> Optional[str]:
    """
    Extract company name from URL.
    """
    if not url or not isinstance(url, str):
        return None
    
    try:
        domain_match = COMPANY_DOMAIN_PATTERN.search(url)
        if domain_match:
            domain = domain_match.group(1)
            domain = DOMAIN_CLEANUP_PATTERN.sub('', domain)
            return domain.capitalize()
        return None
    except Exception as e:
        logger.warning(f"Failed to extract company name from {url}: {e}")
        return None
