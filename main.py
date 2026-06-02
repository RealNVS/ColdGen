from flask import Flask, render_template, request, jsonify, redirect, url_for
from chains import Chain
from portfolio import Portfolio
from utils import clean_text, validate_job_description, validate_skill_match
from loguru import logger
from functools import lru_cache
import os
import traceback
import requests
from urllib.parse import urlparse

app = Flask(__name__)

# Configure logger
logger.add("app.log", rotation="500 MB")

# Initialize components with error handling
try:
    chain = Chain()
    portfolio = Portfolio()
    # Load portfolio once at startup to avoid overhead during requests
    portfolio.load_portfolio()
    logger.info("Application components initialized successfully")
except Exception as e:
    logger.error(f"Error initializing components: {e}")
    chain = None
    portfolio = None

# Cache for storing last processed data
cached_data = {
    "last_job": None,
    "last_links": None,
    "last_username": None,
    "last_tone": None,
    "last_url": None,
    "last_message_type": None,
    "last_responses": None
}

RESPONSE_VARIANTS = [
    {
        "title": "Direct",
        "instruction": "Write a concise, direct version focused on fit and immediate value."
    },
    {
        "title": "Project-Led",
        "instruction": "Write a version that leads with the most relevant portfolio project evidence."
    },
    {
        "title": "Warm",
        "instruction": "Write a warmer, more conversational version while staying professional."
    },
]

@lru_cache(maxsize=50)
def get_job_data(url):
    """Cached function to fetch and clean job data from a URL"""
    logger.info(f"Scraping and cleaning data from: {url}")

    api_data = get_job_data_from_supported_api(url)
    if api_data:
        return api_data

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        cleaned = clean_text(response.text)
        if cleaned and len(cleaned.strip()) >= 50:
            return cleaned
        logger.warning("Job page returned too little readable content")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch job page: {e}")
        return None


def get_job_data_from_supported_api(url):
    """
    Fetch job data from known job-board APIs when the page shell loads details with JavaScript.
    """
    parsed = urlparse(url)
    if parsed.netloc.lower() != "ainterviews.com":
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[0] != "job_board" or parts[2] != "job":
        return None

    slug = parts[1]
    job_id = parts[3]
    api_url = f"{parsed.scheme}://{parsed.netloc}/api/job_board/{slug}/job/{job_id}/"

    try:
        response = requests.get(
            api_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        description = clean_text(data.get("description", ""))
        company_description = clean_text(data.get("company_description", ""))
        fields = [
            f"Role: {data.get('title', '')}",
            f"Company: {data.get('company', '')}",
            f"Location: {data.get('location', '')}",
            f"Job Type: {data.get('job_type', '')}",
            f"Experience: {data.get('experience_level', '')}",
            f"Description: {description}",
            f"Company Description: {company_description}",
        ]
        cleaned = clean_text(" ".join(field for field in fields if field.strip()))
        if cleaned and len(cleaned) >= 80:
            logger.info(f"Fetched job data from supported API: {api_url}")
            return cleaned
    except Exception as e:
        logger.warning(f"Supported API fetch failed for {api_url}: {e}")

    return None

@app.route("/", methods=["GET", "POST"])
def index():
    email_result = None
    error = None
    jobs_found = 0

    if request.method == "POST":
        if chain is None or portfolio is None:
            error = "Application components not properly initialized."
            logger.error(error)
            return render_template("index.html", email=email_result, error=error, jobs_found=jobs_found)

        if "generate" in request.form:
            url = request.form.get("job_url", "").strip()
            username = request.form.get("username", "").strip() or "User"
            tone = request.form.get("tone", "formal").strip()
            message_type = request.form.get("message_type", "cold_email").strip()

            if not url:
                error = "Please provide a valid job URL."
                return render_template("index.html", email=email_result, error=error, jobs_found=jobs_found)

            try:
                logger.info(f"Processing URL: {url}")
                cleaned_data = get_job_data(url)
                
                if not cleaned_data or len(cleaned_data.strip()) < 50:
                    raise ValueError("No valid content could be extracted from the provided URL.")

                logger.info("Extracting jobs...")
                jobs = chain.extract_jobs(cleaned_data)
                jobs_found = len(jobs) if jobs else 0
                
                if not jobs:
                    raise ValueError("No job postings could be extracted.")

                job = jobs[0]
                logger.info(f"EXTRACTED JOB: {job}")
                print(job)
                is_valid_job, validation_error = validate_job_description(job)
                if not is_valid_job:
                    raise ValueError(validation_error)

                skills = job.get("skills", [])
                
                links = []
                if portfolio.is_ready() and skills:
                    links = portfolio.query_links(skills)
                    logger.info(f"Matched {len(links)} portfolio items")

                has_skill_match, match_error = validate_skill_match(skills, links)
                if not has_skill_match:
                    raise ValueError(match_error)

                logger.info("Generating response variants...")
                responses = generate_response_variants(
                    job=job,
                    links=links,
                    username=username,
                    tone=tone,
                    message_type=message_type,
                )

                if not responses:
                    raise ValueError("Response generation returned empty results.")

                cached_data.update({
                    "last_job": job,
                    "last_links": links,
                    "last_username": username,
                    "last_tone": tone,
                    "last_url": url,
                    "last_message_type": message_type,
                    "last_responses": responses
                })

                logger.info("Response variants generated successfully")
                return redirect(url_for("results"))

            except Exception as e:
                error = f"Error: {str(e)}"
                logger.error(f"Processing failed: {error}")
                logger.debug(traceback.format_exc())

        elif "regenerate" in request.form:
            if not cached_data["last_job"]:
                error = "No previous data found."
                return render_template("index.html", email=email_result, error=error, jobs_found=jobs_found)

            try:
                has_skill_match, match_error = validate_skill_match(
                    cached_data["last_job"].get("skills", []),
                    cached_data["last_links"] or []
                )
                if not has_skill_match:
                    raise ValueError(match_error)

                logger.info("Regenerating response variants...")
                responses = generate_response_variants(
                    job=cached_data["last_job"],
                    links=cached_data["last_links"] or [],
                    username=cached_data["last_username"],
                    tone=cached_data["last_tone"],
                    message_type=cached_data["last_message_type"] or "cold_email",
                )
                cached_data["last_responses"] = responses
                jobs_found = 1
                return redirect(url_for("results"))
            except Exception as e:
                error = f"Regeneration failed: {str(e)}"
                logger.error(error)

    return render_template("index.html", email=email_result, error=error, jobs_found=jobs_found)


def generate_response_variants(job, links, username, tone, message_type):
    responses = []
    for variant in RESPONSE_VARIANTS:
        content = chain.write_mail(
            job,
            links,
            username=username,
            tone=tone,
            message_type=message_type,
            variant_instruction=variant["instruction"],
        )
        if content:
            responses.append({
                "title": variant["title"],
                "content": content,
            })
    return responses


@app.route("/results", methods=["GET", "POST"])
def results():
    if request.method == "POST":
        if not cached_data["last_job"]:
            return redirect(url_for("index"))

        try:
            has_skill_match, match_error = validate_skill_match(
                cached_data["last_job"].get("skills", []),
                cached_data["last_links"] or []
            )
            if not has_skill_match:
                raise ValueError(match_error)

            cached_data["last_responses"] = generate_response_variants(
                job=cached_data["last_job"],
                links=cached_data["last_links"] or [],
                username=cached_data["last_username"],
                tone=cached_data["last_tone"],
                message_type=cached_data["last_message_type"] or "cold_email",
            )
        except Exception as e:
            logger.error(f"Result regeneration failed: {e}")

        return redirect(url_for("results"))

    if not cached_data["last_responses"]:
        return redirect(url_for("index"))

    return render_template(
        "results.html",
        responses=cached_data["last_responses"],
        job=cached_data["last_job"],
        url=cached_data["last_url"],
        message_type=cached_data["last_message_type"],
        tone=cached_data["last_tone"],
    )

@app.route("/ping")
def ping():
    return jsonify({"status": "running"}), 200

@app.route("/health")
def health():
    status = "healthy" if chain and portfolio and portfolio.is_ready() else "unhealthy"
    return jsonify({"status": status}), 200 if status == "healthy" else 500

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template("500.html"), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "True").lower() == "true"
    logger.info(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
