import json
import os
import re
from typing import Dict, List, Union

from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from loguru import logger
from pydantic import BaseModel, Field

from utils import extract_skills_from_text, truncate_text

load_dotenv()


class Job(BaseModel):
    role: str = Field(description="The job title or role")
    experience: str = Field(description="Years of experience or level required")
    skills: List[str] = Field(description="List of required technical skills")
    description: str = Field(description="Brief summary of the job responsibilities")


class Chain:
    def __init__(self):
        self.llm_fast = ChatGroq(
            temperature=0,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant"
        )
        self.llm_quality = ChatGroq(
            temperature=0,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.3-70b-versatile"
        )
        self.output_parser = JsonOutputParser(pydantic_object=Job)

    def extract_jobs(self, cleaned_text: str) -> List[Dict[str, Union[str, List[str]]]]:
        if not cleaned_text or not cleaned_text.strip():
            logger.error("Empty or invalid text provided for job extraction.")
            raise ValueError("Empty or invalid text provided for job extraction.")

        prompt_extract = PromptTemplate(
            template="""
            ### SCRAPED TEXT:
            {page_data}

            ### TASK:
            Extract the PRIMARY job posting.

            Return ONLY valid JSON:

            {{
            "role": "Job title",
            "experience": "Required experience level",
            "skills": ["skill1", "skill2"],
            "description": "Summary of responsibilities"
            }}

            IMPORTANT:
            - Never return empty JSON.
            - If role is unclear, infer the most likely role.
            - If skills are missing, extract technologies mentioned.
            - If this is a careers page with multiple jobs, choose the first engineering role.
            - Prefer Software Engineer, Backend Engineer, Full Stack Engineer, AI Engineer, Data Engineer, DevOps Engineer when applicable.

            Return JSON only.
            """,
            input_variables=["page_data"],
        )

        try:
            chain_extract = prompt_extract | self.llm_fast
            res = chain_extract.invoke(input={"page_data": truncate_text(cleaned_text, 12000)})
            content = res.content if hasattr(res, "content") else str(res)
            parsed = self._parse_json_response(content)
            jobs = self._normalize_jobs(parsed)

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} job{'s' if len(jobs) != 1 else ''}")
                return jobs

            logger.warning("Model returned no usable job; using text fallback")
            return [self._create_fallback_job(cleaned_text)]

        except Exception as e:
            logger.error(f"Error in job extraction: {e}")
            return [self._create_fallback_job(cleaned_text)]

    def _parse_json_response(self, content: str):
        if not content:
            return {}

        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(cleaned[index:])
                return parsed
            except json.JSONDecodeError:
                continue

        return {}

    def _normalize_jobs(self, parsed) -> List[Dict[str, Union[str, List[str]]]]:
        if isinstance(parsed, dict):
            parsed = [parsed] if parsed else []

        if not isinstance(parsed, list):
            return []

        jobs = []
        for job in parsed:
            if not isinstance(job, dict) or not job:
                continue

            skills = job.get("skills", [])
            if isinstance(skills, str):
                skills = [skill.strip() for skill in re.split(r"[,;/|]", skills) if skill.strip()]

            jobs.append({
                "role": str(job.get("role") or job.get("title") or "Unknown Role").strip(),
                "experience": str(job.get("experience") or "Not specified").strip(),
                "skills": skills if isinstance(skills, list) else [],
                "description": str(job.get("description") or job.get("responsibilities") or "").strip(),
            })

        return jobs

    def _create_fallback_job(self, text: str) -> Dict[str, Union[str, List[str]]]:
        skills = extract_skills_from_text(text)

        return {
            "role": self._infer_role(text),
            "experience": self._infer_experience(text),
            "skills": skills if skills else ["Python"],
            "description": truncate_text(text, 1500),
        }

    def _infer_role(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()

        role_patterns = [
            r"\bassociate software engineer\b",
            r"\bgraduate engineer trainee\b",
            r"\bsoftware development engineer\b",
            r"\bsde\s*[1-3]?\b",
            r"\bjunior software engineer\b",
            r"\bsoftware engineer\b",
            r"\bbackend engineer\b",
            r"\bfrontend engineer\b",
            r"\bfull stack engineer\b",
            r"\bdata engineer\b",
            r"\bmachine learning engineer\b",
            r"\bai engineer\b",
            r"\bdevops engineer\b",
            r"\bcloud engineer\b",
            r"\bqa engineer\b",
            r"\btest engineer\b",
            r"\bdeveloper\b",
            r"\bintern\b",
            r"\btrainee\b",
        ]

        for pattern in role_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).title()

        return "Software Engineer"

    def _infer_experience(self, text: str) -> str:
        match = re.search(r"\b\d+\+?\s*(?:-|to)?\s*\d*\+?\s+years?\b", text or "", re.IGNORECASE)
        return match.group(0) if match else "Not specified"

    def write_mail(
        self,
        job: Dict[str, Union[str, List[str]]],
        links: List[Dict[str, str]],
        username: str = "User",
        tone: str = "formal",
        message_type: str = "cold_email",
        variant_instruction: str = ""
    ) -> str:
        link_str = "No specific projects matched."
        if links and isinstance(links, list):
            descriptions = [
                link["description"]
                for link in links
                if isinstance(link, dict) and link.get("description")
            ]
            if descriptions:
                link_str = "\n".join(descriptions)

        job_description = (
            f"Role: {job.get('role')}\n"
            f"Skills: {', '.join(job.get('skills', []))}\n"
            f"Description: {job.get('description')}"
        )

        message_type_labels = {
            "cold_email": "cold email",
            "linkedin_message": "LinkedIn message",
            "referral_request": "referral request",
        }
        message_label = message_type_labels.get(message_type, "cold email")

        examples = """
        Example 1 (Tone: Professional):
        Subject: Strategic AI Implementation for [Company Name]
        Dear Hiring Manager,
        I am [Name], an AI Developer with experience building scalable Flask and LLM applications. I noticed your opening for an AI Engineer and was impressed by your work in [Industry]. My portfolio includes a similar project where I automated job-description analysis and personalized outreach. I would love to discuss how my expertise can contribute to your team.
        Best regards, [Name]

        Example 2 (Tone: Friendly):
        Subject: Huge fan of your recent work!
        Hi team,
        I'm [Name], and I've been following your AI initiatives for a while. Your recent post about [Topic] really resonated with me. I've built a few AI tools myself, including an automated lead generator that matches skills with job requirements perfectly. I'd love to bring that same energy to your [Role] position. Looking forward to chatting!
        Cheers, [Name]
        """

        prompt_email = PromptTemplate.from_template(
            f"""
            ### EXAMPLES FOR REFERENCE:
            {examples}

            ### JOB DESCRIPTION:
            {{job_description}}

            ### INSTRUCTION:
            You are {{username}}, an AI enthusiast. Write a {{message_label}} for the job above.

            Guidelines:
            - Use a {{tone}} tone
            - Reference these relevant projects:
            {{link_list}}
            - Do NOT use placeholders like [Link]. Use the provided project descriptions directly if relevant.
            - Focus on how your portfolio matches the specific skills: {{skills}}
            - Follow this variant direction: {{variant_instruction}}

            Return only the email content.
            """
        )

        try:
            logger.info(f"Generating {message_label} for {job.get('role')} in {tone} tone")
            res = (prompt_email | self.llm_quality).invoke({
                "job_description": job_description,
                "link_list": link_str,
                "username": username,
                "tone": tone,
                "skills": ", ".join(job.get("skills", [])),
                "message_label": message_label,
                "variant_instruction": variant_instruction or "Write a balanced, polished version.",
            })
            return res.content.strip()

        except Exception as e:
            logger.error(f"Error generating email: {e}")
            return f"Error generating email: {str(e)}"
