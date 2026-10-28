"""Export an explicit public presentation without reading private source records."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field

from .url_safety import is_public_host
from .validation.hashing import canonical_json_bytes, sha256_digest
from .validation.models import StrictModel
from .validation.store import atomic_write_canonical_json


class Link(StrictModel):
    label: str
    href: str


class Education(StrictModel):
    degree: str
    institution: str
    period: str
    detail: str


class Experience(StrictModel):
    role: str
    organization: str
    period: str
    detail: str
    points: list[str] = Field(default_factory=list)


class Highlight(StrictModel):
    label: str
    value: str


class Interest(StrictModel):
    title: str
    note: str
    items: list[str]


class ShortProject(StrictModel):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    href: str | None = None
    link_label: str | None = Field(default=None, alias="linkLabel")
    status: str | None = None
    featured: bool = False


class Research(StrictModel):
    name: str
    points: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    location: str | None = None
    period: str | None = None
    supervisor: str | None = None


class Seminar(StrictModel):
    role: str
    period: str
    url: str | None = None
    link_label: str | None = Field(default=None, alias="linkLabel")
    points: list[str] = Field(default_factory=list)


class School(StrictModel):
    title: str
    url: str
    date: str | None = None


class Profile(StrictModel):
    name: str
    title: str = ""
    location: str = ""
    summary: str = ""
    intro: str = ""
    links: list[Link] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    home_highlights: list[Highlight] = Field(default_factory=list, alias="homeHighlights")
    open_source: list[ShortProject] = Field(default_factory=list, alias="openSourceContributions")
    side_projects: list[ShortProject] = Field(default_factory=list, alias="sideProjects")
    interests: list[Interest] = Field(default_factory=list)
    research: list[Research] = Field(default_factory=list)
    master_thesis: list[Research] = Field(default_factory=list, alias="masterThesis")
    seminars: list[Seminar] = Field(default_factory=list)
    selected_schools: list[School | str] = Field(default_factory=list, alias="selectedSchools")
    skills: list[str] = Field(default_factory=list)


class Section(StrictModel):
    label: str
    text: str | None = None
    bullets: list[str] | None = None


class Project(StrictModel):
    visibility: Literal["public", "private"] = "private"
    id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    type: str
    summary: str
    status: str | None = None
    links: list[Link] = Field(default_factory=list)
    report_url: str | None = Field(default=None, alias="reportUrl")
    report_label: str | None = Field(default=None, alias="reportLabel")
    sections: list[Section] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    featured: bool = False
    compact: bool = False


class LearningTerm(StrictModel):
    name: str
    level: Literal["core", "medium", "small"]
    column: int
    row: int
    detail: str


class LearningMap(StrictModel):
    description: str = ""
    credentials_url: str | None = Field(default=None, alias="credentialsUrl")
    terms: list[LearningTerm] = Field(default_factory=list)


class Knowledge(StrictModel):
    visibility: Literal["public", "private"] = "private"
    title: str
    summary: str
    kind: str
    links: list[Link] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class PublicSiteSource(StrictModel):
    schema_version: Literal["public-site-source/v1"]
    publication_status: Literal["draft", "public"] = "draft"
    profile: Profile
    ai_projects: list[Project] = Field(default_factory=list)
    finance_projects: list[Project] = Field(default_factory=list)
    learning_map: LearningMap = Field(default_factory=LearningMap)
    knowledge: list[Knowledge] = Field(default_factory=list)


def _public_url(value: str) -> None:
    if "\\" in value or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError("public-site-link-invalid")
    parsed = urlsplit(value)
    if (
        value.startswith("/")
        and not parsed.scheme
        and not parsed.netloc
        and not value.startswith("//")
        and ".." not in unquote(parsed.path).split("/")
    ):
        return
    if parsed.scheme == "mailto" and "@" in parsed.path and not parsed.query:
        return
    host = parsed.hostname or ""
    if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
        raise ValueError("public-site-link-invalid")
    if not is_public_host(host):
        raise ValueError("public-site-link-private")


class _PublicMarkup(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"a", "em", "strong", "br"}:
            raise ValueError("public-site-markup-invalid")
        for key, value in attrs:
            if tag != "a" or key not in {"href", "class", "target", "rel"} or value is None:
                raise ValueError("public-site-markup-invalid")
            if key == "href":
                _public_url(value)

    def handle_endtag(self, tag: str) -> None:
        if tag not in {"a", "em", "strong", "br"}:
            raise ValueError("public-site-markup-invalid")


def _check_public_values(value: object, key: str = "") -> None:
    if isinstance(value, dict):
        for name, item in value.items():
            _check_public_values(item, name)
    elif isinstance(value, list):
        for item in value:
            _check_public_values(item, key)
    elif isinstance(value, str):
        if re.search(r"/Users/|/Volumes/|/home/|\.career-evidence/|file:|[A-Za-z]:\\", value):
            raise ValueError("public-site-private-locator")
        if key in {"href", "url", "reportUrl", "credentialsUrl"}:
            _public_url(value)
        markup = _PublicMarkup()
        markup.feed(value)
        if re.search(r"<[a-zA-Z/!]", markup.rawdata):
            raise ValueError("public-site-markup-invalid")
        markup.close()


def public_site_payload(source: PublicSiteSource) -> dict:
    """Project only selected presentation fields; never derive a mastery score."""
    if source.publication_status != "public":
        raise ValueError("public-site-not-selected")
    profile = source.profile.model_dump(mode="json", by_alias=True, exclude_none=True)

    def visible(items: list) -> list[dict]:
        return [
            item.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"visibility"})
            for item in items
            if item.visibility == "public"
        ]

    payload = {
        "schema_version": "public-site/v1",
        "authority": "public-presentation",
        "profile": profile,
        "aiProjects": visible(source.ai_projects),
        "financeProjects": visible(source.finance_projects),
        "learningMap": source.learning_map.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "knowledge": visible(source.knowledge),
    }
    skills: dict[str, dict] = {}

    def add_skill(name: str, title: str | None = None, href: str | None = None) -> None:
        name = name.strip()
        if not name:
            return
        record = skills.setdefault(
            name.casefold(), {"name": name, "authority": "declared", "projects": []}
        )
        link = {"title": title, "href": href}
        if title and link not in record["projects"]:
            record["projects"].append(link)

    for name in profile["skills"]:
        add_skill(name)
    for key, route in (("aiProjects", "/ai-ml"), ("financeProjects", "/finance")):
        for item in payload[key]:
            item["anchor"] = (
                item.get("id")
                or "project-" + sha256_digest((route + ":" + item["title"]).encode())[7:23]
            )
            href = route + "#" + item["anchor"]
            for name in item["skills"]:
                add_skill(name, item["title"], href)
    for key in ("sideProjects", "openSourceContributions"):
        for item in profile[key]:
            for name in item["tags"]:
                add_skill(name, item["title"], item.get("href", "/"))
    payload["skills"] = sorted(skills.values(), key=lambda item: item["name"].casefold())
    _check_public_values(payload)
    payload["revision"] = sha256_digest(canonical_json_bytes(payload))
    return payload


def load_public_site(path: Path) -> dict:
    if (
        path.is_symlink()
        or any(parent.is_symlink() for parent in path.parents)
        or path.stat().st_size > 2_000_000
    ):
        raise ValueError("public-site-source-unsafe")
    return public_site_payload(PublicSiteSource.model_validate_json(path.read_bytes(), strict=True))


def export_public_site(source: Path, destination: Path) -> dict:
    """Validate before atomically replacing the site's one public snapshot."""
    if (
        destination.suffix != ".json"
        or destination.is_symlink()
        or any(parent.is_symlink() for parent in destination.parents)
        or source.resolve() == destination.resolve()
    ):
        raise ValueError("public-site-destination-unsafe")
    payload = load_public_site(source)
    changed = not destination.exists() or json.loads(destination.read_bytes()) != payload
    if changed:
        atomic_write_canonical_json(destination, payload)
    return {"changed": changed, "revision": payload["revision"], "authority": payload["authority"]}
