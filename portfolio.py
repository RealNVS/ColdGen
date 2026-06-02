import csv
import os
import re
from typing import Any, Dict, List

from loguru import logger


class Portfolio:
    STOP_SKILL_TERMS = {
        "and", "or", "the", "with", "for", "to", "of", "in", "on", "at",
         "tool", "tools",
    }

    def __init__(self, file_path: str = None):
        self.file_path = file_path or os.path.join("resource", "project_portfolio.csv")
        self.projects: List[Dict[str, str]] = []
        self._load_csv()

    def _load_csv(self) -> None:
        if not os.path.exists(self.file_path):
            logger.warning(f"Portfolio file not found at {self.file_path}")
            self.projects = []
            return

        try:
            with open(self.file_path, newline="", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file)
                self.projects = [
                    {
                        "title": (row.get("Title") or "").strip(),
                        "description": (row.get("Description") or "").strip(),
                        "techstack": (row.get("Techstack") or "").strip(),
                    }
                    for row in reader
                    if (row.get("Description") or "").strip()
                ]
            logger.info(f"Loaded {len(self.projects)} portfolio projects")
        except Exception as e:
            logger.error(f"Failed to load portfolio CSV: {e}")
            self.projects = []

    def load_portfolio(self) -> bool:
        return self.is_ready()

    def query_links(self, skills: List[str]) -> List[Dict[str, Any]]:
        return self._format_projects(self.find_matching_projects(skills))

    def find_matching_projects(self, skills: List[str]) -> List[Dict[str, str]]:
        if not self.is_ready():
            return []

        skill_terms = {
            skill.strip().lower()
            for skill in skills
            if isinstance(skill, str) and skill.strip()
        }
        if not skill_terms:
            return []

        scored_projects = []
        for project in self.projects:
            searchable_text = f"{project['title']} {project['techstack']} {project['description']}".lower()
            score = self._score_project(searchable_text, skill_terms)
            if score > 0:
                scored_projects.append((score, project))

        scored_projects.sort(key=lambda item: item[0], reverse=True)
        matches = [project for _, project in scored_projects[:5]]

        logger.info(f"Matched {len(matches)} portfolio projects")
        return matches

    def get_all_projects(self) -> List[Dict[str, str]]:
        return list(self.projects)

    def add_project(self, techstack: str, description: str, title: str = "Untitled Project") -> bool:
        if not techstack or not description:
            logger.error("Both techstack and description are required")
            return False

        project = {
            "title": title.strip() or "Untitled Project",
            "description": description.strip(),
            "techstack": techstack.strip(),
        }

        try:
            file_exists = os.path.exists(self.file_path)
            with open(self.file_path, "a", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["Title", "Description", "Techstack"])
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "Title": project["title"],
                    "Description": project["description"],
                    "Techstack": project["techstack"],
                })
            self.projects.append(project)
            logger.info(f"Added project: {project['title']}")
            return True
        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return False

    def is_ready(self) -> bool:
        return bool(self.projects)

    def _contains_skill(self, text: str, skill: str) -> bool:
        if len(skill) <= 2:
            return re.search(rf"\b{re.escape(skill)}\b", text) is not None
        return skill in text

    def _score_project(self, text: str, skill_terms: set[str]) -> int:
        score = 0
        for skill in skill_terms:
            if self._contains_skill(text, skill):
                score += 3
                continue

            tokens = self._skill_tokens(skill)
            score += sum(1 for token in tokens if self._contains_skill(text, token))

        return score

    def _skill_tokens(self, skill: str) -> List[str]:
        return [
            token
            for token in re.split(r"[^a-z0-9+#.]+", skill.lower())
            if len(token) >= 2 and token not in self.STOP_SKILL_TERMS
        ]

    def _format_projects(self, projects: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [
            {
                "description": (
                    f"{project['title']}: {project['description']} "
                    f"Tech stack: {project['techstack']}"
                ).strip()
            }
            for project in projects
        ]
