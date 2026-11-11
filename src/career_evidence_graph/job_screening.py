"""Explain candidate relevance, unresolved requirements and worker compatibility."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from functools import cache
from urllib.parse import urlsplit

from .application_automation import (
    _job_identity,
    deadline_passed,
    duplicate_applications,
    record_label,
)
from .career_portal_data import APPLICATION_DECISIONS, STATUS_LABELS, PortalDataError

PLATFORMS = {
    "lever": "Lever",
    "greenhouse": "Greenhouse",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "workday": "Workday",
    "successfactors": "SAP SuccessFactors",
    "icims": "iCIMS",
    "taleo": "Taleo",
    "linkedin": "LinkedIn",
    "other": "企业自有站点或其他平台",
    "missing": "缺少岗位链接",
    "invalid": "链接需要核对",
}
DOMAINS = {
    "lever.co": "lever",
    "greenhouse.io": "greenhouse",
    "ashbyhq.com": "ashby",
    "smartrecruiters.com": "smartrecruiters",
    "myworkdayjobs.com": "workday",
    "myworkdaysite.com": "workday",
    "successfactors.com": "successfactors",
    "successfactors.eu": "successfactors",
    "icims.com": "icims",
    "taleo.net": "taleo",
    "linkedin.com": "linkedin",
}
TARGET = re.compile(
    r"\b(ai|ml|machine learning|deep learning|llm|nlp|computer vision|inference"
    r"|quant(?:itative)?)\b"
    r"|人工智能|机器学习|量化",
    re.I,
)
LABELS = {
    "recorded": "已有进度记录",
    "excluded": "暂不进入批次",
    "manual": "需直达链接或平台适配",
    "review": "需核对岗位条件",
    "preparable": "技术上可准备",
    "other": "其他方向",
}
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
ROUTE_LABELS = {
    "batch": "批量投递",
    "manual": "人工精准投递",
    "review": "待判断",
    "hold": "暂缓投递",
    "excluded": "暂不进入投递",
    "recorded": "已有进度",
}


def application_route(record: dict, *, relevant: bool) -> tuple[str, list[str]]:
    """Use saved operator judgments; document presence never proves a match."""
    if any(record.get(key, "") not in values for key, values in APPLICATION_DECISIONS.items()):
        return "review", ["岗位评价含未知值，请重新核对并保存"]
    strategy = record.get("application_strategy")
    if strategy:
        return strategy, ["已保存的人工分流决定"]
    high_value = []
    if record.get("target_company") == "target":
        high_value.append("已标记为目标公司")
    if record.get("compensation_priority") == "exceptional":
        high_value.append("已核对为超高薪资机会")
    if record.get("personal_priority") == "high":
        high_value.append("个人优先意愿高")
    if record.get("jd_match") == "strong" and record.get("evidence_match") == "direct":
        high_value.append("已核对 JD 高匹配，并有直接相关经历证据")
    if high_value:
        return "manual", high_value
    if record.get("jd_match") == "weak" or record.get("evidence_match") == "missing":
        return "hold", ["已核对 JD 匹配较低或相关经历证据不足"]
    if record.get("personal_priority") == "low":
        return "hold", ["个人优先意愿低"]
    if not relevant:
        return "review", ["目标方向尚未明确，请核对后选择投递方式"]
    if not str(record.get("job_description") or "").strip():
        return "review", ["请先保存并核对 JD"]
    pending = []
    for key, label in (
        ("jd_match", "JD 匹配"),
        ("evidence_match", "经历证据"),
        ("personal_priority", "个人优先意愿"),
        ("target_company", "目标公司"),
        ("compensation_priority", "薪资吸引力"),
    ):
        if not record.get(key):
            pending.append(label)
    if pending:
        return "review", ["待核对：" + "、".join(pending)]
    return "batch", ["评价已核对，当前未标记重点投入信号"]


def _language_requirement(sentence: str, language: str) -> str:
    names = {"French": r"French|法语", "German": r"German|德语"}[language]
    if not re.search(rf"\b(?:{names})\b|{names}", sentence, re.I):
        return ""
    if re.search(
        r"not required|not mandatory|optional|preferred|nice.to.have|非必需|不要求", sentence, re.I
    ):
        return ""
    if not re.search(
        r"\brequired\b|\bmandatory\b|\bmust\b|at least|minimum|必须|要求", sentence, re.I
    ):
        return ""
    # Alternative languages do not establish a mismatch without all alternatives.
    if (
        re.search(r"\bor\b|\beither\b|或", sentence, re.I)
        and len(set(re.findall(r"French|German|English|法语|德语|英语", sentence, re.I))) > 1
    ):
        return ""
    level = re.search(
        rf"(?:{names})\s*(?:(?:proficiency|level|CEFR|at least|minimum|of)\s*|[:=\-]\s*)*"
        r"([ABC][12])\b"
        rf"|\b([ABC][12])\s*(?:level\s*)?(?:in\s*)?(?:{names})\b",
        sentence,
        re.I,
    )
    if level:
        return (level[1] or level[2]).upper()
    if re.search(
        rf"(?:fluent|fluency|native)\s*(?:(?:in|of|speaker|proficiency)\s+)*(?:{names})"
        rf"|(?:{names})\s*(?:(?:language|proficiency|level|is|must|be)\s+)*"
        r"(?:fluent|fluency|native|流利|母语)"
        rf"|(?:流利|母语)\s*(?:{names})",
        sentence,
        re.I,
    ):
        return "advanced"
    return ""


def _platform(value: str, *, allow_generic: bool = False) -> tuple[str, object, bool]:
    if not value:
        return "missing", None, False
    try:
        platform, normalized = _job_identity(value)
        # Match the existing duplicate gate, including GH aliases and Lever /apply.
        return platform, (platform, urlsplit(normalized).path), True
    except PortalDataError:
        pass
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            return "invalid", None, False
    except ValueError:
        return "invalid", None, False
    platform = next(
        (
            name
            for domain, name in DOMAINS.items()
            if parsed.hostname == domain or parsed.hostname.endswith("." + domain)
        ),
        "other",
    )
    if allow_generic:
        try:
            _, normalized = _job_identity(value, allow_generic=True)
            return platform, ("generic", normalized), True
        except PortalDataError:
            pass
    # Unknown sites may encode job identity in query or fragment. Preserve both.
    return platform, value, False


_COUNTRIES = {
    "CHE": ("Switzerland", "Schweiz", "Suisse", "瑞士", "CHE"),
    "USA": ("United States", "United States of America", "USA", "US"),
    "GBR": ("United Kingdom", "Great Britain", "UK", "GBR", "英国"),
    "DEU": ("Germany", "Deutschland", "DEU", "德国"),
    "FRA": ("France", "FRA", "法国"),
    "CAN": ("Canada", "CAN", "加拿大"),
}
# Explicit country names prevent a second, unsupported country being mistaken for
# a city. Unrecognized or ambiguous locations stay unresolved, never CHE by default.
# 2026-11-11 (user decision): a well-known city names its country by itself
# ("8048 Zürich, ZH", "New York", "Dubai"). Names shared by cities in two countries
# (Cambridge, Birmingham, Valencia) are left out; an unlisted place stays unresolved.
_CITY_COUNTRIES = {
    "CHE": "zürich|zurich|zuerich|genève|geneve|geneva|genf|basel|bern|berne|lausanne|zug|lugano"
    "|luzern|lucerne|winterthur|st. gallen|st.gallen|sankt gallen|biel|neuchâtel|fribourg"
    "|schaffhausen|chur|baden|aarau|thun|sion|oerlikon|schlieren|dübendorf|wallisellen|opfikon",
    "USA": "new york|new york city|nyc|san francisco|los angeles|seattle|boston|chicago|austin"
    "|san jose|palo alto|mountain view|menlo park|sunnyvale|cupertino|redmond|san diego"
    "|washington|washington dc|atlanta|denver|houston|dallas|miami|philadelphia|pittsburgh"
    "|new york metropolitan area|san francisco bay area",
    "GBR": "london|manchester|edinburgh|oxford|glasgow|bristol|leeds|belfast|cardiff",
    "DEU": "berlin|munich|münchen|muenchen|hamburg|frankfurt|frankfurt am main|stuttgart"
    "|cologne|köln|düsseldorf|duesseldorf|heidelberg|karlsruhe|dresden|leipzig|nürnberg"
    "|nuremberg|bonn|aachen|tübingen|darmstadt",
    "FRA": "paris|lyon|toulouse|marseille|grenoble|nice|bordeaux|lille|nantes|strasbourg",
    "CAN": "toronto|montreal|montréal|vancouver|ottawa|calgary|waterloo|edmonton",
    "OTHER": "dubai|abu dhabi|beijing|shanghai|shenzhen|hangzhou|guangzhou|hong kong|singapore"
    "|tokyo|osaka|seoul|taipei|bangalore|bengaluru|mumbai|delhi|new delhi|hyderabad|sydney"
    "|melbourne|amsterdam|rotterdam|eindhoven|brussels|vienna|wien|madrid|barcelona|lisbon"
    "|milan|milano|rome|stockholm|copenhagen|oslo|helsinki|dublin|warsaw|prague|budapest"
    "|luxembourg|tel aviv|istanbul|riyadh|doha|são paulo|sao paulo|mexico city",
}
_CITIES = {city: country for country, names in _CITY_COUNTRIES.items() for city in names.split("|")}
_OTHER_COUNTRIES = (
    "Afghanistan",
    "Albania",
    "Algeria",
    "Andorra",
    "Angola",
    "Antigua and Barbuda",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Azerbaijan",
    "Bahamas",
    "Bahrain",
    "Bangladesh",
    "Barbados",
    "Belarus",
    "Belgium",
    "Belize",
    "Benin",
    "Bhutan",
    "Bolivia",
    "Bosnia and Herzegovina",
    "Botswana",
    "Brazil",
    "Brunei",
    "Bulgaria",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cambodia",
    "Cameroon",
    "Central African Republic",
    "Chad",
    "Chile",
    "China",
    "Colombia",
    "Comoros",
    "Congo",
    "Costa Rica",
    "Croatia",
    "Cuba",
    "Cyprus",
    "Czechia",
    "Czech Republic",
    "Democratic Republic of the Congo",
    "Denmark",
    "Djibouti",
    "Dominica",
    "Dominican Republic",
    "Ecuador",
    "Egypt",
    "El Salvador",
    "Equatorial Guinea",
    "Eritrea",
    "Estonia",
    "Eswatini",
    "Ethiopia",
    "Fiji",
    "Finland",
    "Gabon",
    "Gambia",
    "Georgia",
    "Ghana",
    "Greece",
    "Grenada",
    "Guatemala",
    "Guinea",
    "Guinea-Bissau",
    "Guyana",
    "Haiti",
    "Honduras",
    "Hungary",
    "Iceland",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Ireland",
    "Israel",
    "Italy",
    "Ivory Coast",
    "Jamaica",
    "Japan",
    "Jordan",
    "Kazakhstan",
    "Kenya",
    "Kiribati",
    "Kosovo",
    "Kuwait",
    "Kyrgyzstan",
    "Laos",
    "Latvia",
    "Lebanon",
    "Lesotho",
    "Liberia",
    "Libya",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Madagascar",
    "Malawi",
    "Malaysia",
    "Maldives",
    "Mali",
    "Malta",
    "Marshall Islands",
    "Mauritania",
    "Mauritius",
    "Mexico",
    "Micronesia",
    "Moldova",
    "Monaco",
    "Mongolia",
    "Montenegro",
    "Morocco",
    "Mozambique",
    "Myanmar",
    "Namibia",
    "Nauru",
    "Nepal",
    "Netherlands",
    "New Zealand",
    "Nicaragua",
    "Niger",
    "Nigeria",
    "North Korea",
    "North Macedonia",
    "Norway",
    "Oman",
    "Pakistan",
    "Palau",
    "Palestine",
    "Panama",
    "Papua New Guinea",
    "Paraguay",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Qatar",
    "Romania",
    "Russia",
    "Rwanda",
    "Saint Kitts and Nevis",
    "Saint Lucia",
    "Saint Vincent and the Grenadines",
    "Samoa",
    "San Marino",
    "Sao Tome and Principe",
    "Saudi Arabia",
    "Senegal",
    "Serbia",
    "Seychelles",
    "Sierra Leone",
    "Singapore",
    "Slovakia",
    "Slovenia",
    "Solomon Islands",
    "Somalia",
    "South Africa",
    "South Korea",
    "South Sudan",
    "Spain",
    "Sri Lanka",
    "Sudan",
    "Suriname",
    "Sweden",
    "Syria",
    "Taiwan",
    "Tajikistan",
    "Tanzania",
    "Thailand",
    "Timor-Leste",
    "Togo",
    "Tonga",
    "Trinidad and Tobago",
    "Tunisia",
    "Turkey",
    "Turkiye",
    "Turkmenistan",
    "Tuvalu",
    "Uganda",
    "Ukraine",
    "United Arab Emirates",
    "Uruguay",
    "Uzbekistan",
    "Vanuatu",
    "Vatican City",
    "Venezuela",
    "Vietnam",
    "Yemen",
    "Zambia",
    "Zimbabwe",
)


def job_country(record):
    """The location's explicit country, else the page's own structured country.

    2026-11-08, Mistral: the location said only "Zurich", while the job page's
    structured field, kept in the JD as "addressCountry: Switzerland", named one.
    Last comes the country site of the Indeed listing the job was read from.
    """
    country = application_country(record.get("location"))
    if country is not None:
        return country
    named = {
        application_country(value.strip())
        for value in re.findall(
            r"addressCountry:\s*([^\n,;]+)", str(record.get("job_description") or "")
        )
    }
    if len(named) == 1 and None not in named:
        return named.pop()
    if named:
        return None
    # 2026-11-10, Julius Baer: "8048 Zürich, ZH" named no country, while the job came
    # from ch.indeed.com; Indeed's country site lists that country's jobs.
    host = urlsplit(str(record.get("listing_url") or "")).hostname or ""
    return (
        _INDEED_SITES.get(host.removesuffix(".indeed.com"))
        if host.endswith(".indeed.com")
        else None
    )


_INDEED_SITES = {"ch": "CHE", "de": "DEU", "fr": "FRA", "uk": "GBR", "ca": "CAN"}


@cache
def _name_patterns(name):
    """A country or city name's exact-part and mention patterns, compiled once.

    2026-11-11: with the city lists, every location compiled hundreds of patterns
    past re's cache, and the workbench's state request took 37 s.
    """
    code = name.isascii() and name.isupper()
    literal = re.escape(name) if code else "(?i:" + re.escape(name) + ")"
    return (
        re.compile(r"(?i:remote(?:\s+in)?\s+)?" + literal + r"(?i:\s+remote)?"),
        re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", 0 if code else re.I),
    )


def application_country(location):
    """Only an explicit unique country in the job location establishes scope."""
    if not isinstance(location, str) or re.search(
        r"[;/|]|\b(?:or|exclude[ds]?|excluding|except|outside|not|non|without|other\s+than)\b",
        location,
        re.I,
    ):
        return None
    components = [part.strip() for part in re.split(r"[,()\[\]—–-]", location)]
    matches = set()
    labels = [*_COUNTRIES.items(), *((name, (name,)) for name in _OTHER_COUNTRIES)]
    for country, names in labels:
        positive, mentioned = False, False
        for name in names:
            exact, mention = _name_patterns(name)
            positive = positive or any(exact.fullmatch(part) for part in components)
            mentioned = mentioned or bool(mention.search(location))
        if positive:
            matches.add(country)
        elif mentioned:
            # A country mentioned in prose or an unrecognized qualifier cannot
            # establish a positive jurisdiction or be silently discarded.
            return None
    if not matches:
        # 2026-11-11, Celonis: "Zürich Metropolitan Area". A well-known city named
        # anywhere in the location counts, whatever stands around it.
        text = location.casefold()
        cities = {
            country for city, country in _CITIES.items() if _name_patterns(city)[1].search(text)
        }
        if len(cities) == 1:
            return cities.pop()
    if len(matches) != 1:
        return None
    country = matches.pop()
    return country if country in _COUNTRIES else "OTHER"


def screen_applications(
    records: list[dict],
    *,
    application_id: str | None = None,
    today: date | None = None,
    language_levels: dict | Callable[[dict], dict] | None = None,
    allow_generic: bool = False,
) -> list[dict]:
    """Screen selected records against full history without changing saved facts."""
    output = []
    for record in records:
        if application_id is not None and record["id"] != application_id:
            continue
        platform, _key, supported = _platform(
            str(record.get("url") or ""), allow_generic=allow_generic
        )
        title = str(record.get("role_title") or "")
        relevant = record.get("track") in {"AI", "AI/ML", "Quant"} or bool(TARGET.search(title))
        history_matches = duplicate_applications(record, records)
        duplicate = bool(history_matches)
        company = record_label(record.get("company"))
        company_history = [
            {field: other.get(field, "") for field in ("id", "role_title", "status", "url")}
            for other in records
            if other["id"] != record["id"]
            and company
            and record_label(other.get("company")) == company
            and other.get("status") != "drafting"
        ]
        expired = deadline_passed(record.get("deadline"), today)
        draft = record.get("status") == "drafting"
        reviews = ["申请地区、职级和个人资格尚需确认"] if draft else []
        if draft and company_history:
            reviews.append(
                "同公司已有投递进度，请核对是否为本轮岗位："
                + "；".join(
                    f"{other['role_title']}（{STATUS_LABELS.get(other['status'], '未知状态')}"
                    + ("；缺少岗位链接" if not other["url"] else "")
                    + "）"
                    for other in company_history
                )
            )
        generic_preflight = supported and platform not in {"lever", "greenhouse"}
        if generic_preflight:
            reviews.append("通用表单需预检；控件和资料发送路径尚未验证")
        jd = str(record.get("job_description") or "").strip()
        mismatches = []
        language_questions = []
        country = record.get("country") or job_country(record)
        context = record | {"country": country} if country is not None else record
        levels = language_levels(context) if callable(language_levels) else language_levels
        for language, level in (levels or {}).items():
            if language not in {"French", "German"}:
                continue
            for sentence in re.split(r"[.!?;\n]", jd):
                required = _language_requirement(sentence, language)
                if level is None and required:
                    language_questions.append("适用语言信息有冲突或缺少明确等级，请核对")
                    break
                if level not in LEVELS:
                    continue
                if (required in LEVELS and LEVELS.index(level) < LEVELS.index(required)) or (
                    required == "advanced" and level in {"A1", "A2"}
                ):
                    name = "法语" if language == "French" else "德语"
                    mismatches.append(f"明确{name}要求与已确认水平不匹配")
                    break
        if not jd:
            reviews.append("未保存 JD，资格和岗位开放状态尚未核对")
        if re.search(
            r"\b(senior|staff|principal|lead|head|director|manager)\b|高级|资深|总监", title, re.I
        ):
            reviews.append("职级要求需核对")
        if re.search(r"\b\d+\s*\+\s*years?\b|\bat least \d+ years?\b|\d+\s*年以上", jd, re.I):
            reviews.append("工作年限要求需核对")
        if re.search(r"\bintern(?:ship)?\b|\bgraduate\b|实习|应届", title, re.I):
            reviews.append("在读、毕业时间和入职时间需核对")
        languages = r"(?:English|French|German|Chinese|Spanish|Italian|法语|德语|英语|中文)"
        for sentence in re.split(r"[.!?\n]", jd):
            if re.search(
                r"not required|not mandatory|optional|nice.to.have|非必需|不要求", sentence, re.I
            ):
                continue
            if re.search(
                rf"\b(?:fluent|fluency|native)\b.{{0,40}}{languages}"
                rf"|{languages}.{{0,60}}\b(?:required|mandatory|fluent|fluency|native)\b"
                rf"|(?:必须|流利|母语).{{0,20}}{languages}",
                sentence,
                re.I,
            ):
                reviews.append("明确语言要求需核对")
                break
        if re.search(
            r"\b(sponsorship|work authori[sz]ation|work permit)\b|工作许可|签证担保", jd, re.I
        ):
            reviews.append("工作资格和签证担保需按国家核对")
        reasons = []
        if not draft:
            reasons.append("仅准备投递记录可进入批次；保留已有状态")
        if duplicate:
            reasons.append(
                "已有相同岗位链接，请使用原记录"
                if any(match["basis"] == "job_url" for match in history_matches)
                else "已有相同公司和岗位名称的记录，链接缺失，需先核实是否重复投递"
            )
        if expired:
            reasons.append("记录中的截止日期已过，请核对后更新")
        reasons.extend(mismatches)
        reasons.extend(language_questions)
        if not supported:
            reasons.append(
                "请保存公开 HTTPS 岗位直达链接"
                if allow_generic
                else "当前 worker 仅支持 Lever / Greenhouse 托管直达链接"
            )
        preparable = (
            draft
            and supported
            and not duplicate
            and not expired
            and not mismatches
            and not language_questions
        )
        route, route_reasons = application_route(record, relevant=relevant)
        if not draft:
            route, route_reasons = "recorded", ["保留已有投递进度"]
        elif duplicate or expired or mismatches:
            route, route_reasons = "excluded", reasons.copy()
        elif language_questions:
            route, route_reasons = "review", language_questions.copy()
        if not draft:
            category = "recorded"
        elif duplicate or expired or mismatches:
            category = "excluded"
        elif language_questions:
            category = "review"
        elif not relevant:
            category = "other"
        elif not supported:
            category = "manual"
        else:
            category = "review" if reviews else "preparable"
        priority = {
            "preparable": 0,
            "review": 1,
            "manual": 2,
            "other": 3,
            "recorded": 4,
            "excluded": 5,
        }[category]
        screening = {
            "category": category,
            "label": LABELS[category],
            "platform": platform,
            "platform_label": PLATFORMS[platform],
            "target_relevant": relevant,
            "worker_supported": supported,
            "worker_preparable": preparable,
            "application_route": route,
            "route_label": ROUTE_LABELS[route],
            "route_reasons": route_reasons,
            "batch_preparable": preparable and route == "batch",
            "precision_preparable": preparable and route == "manual",
            "generic_preflight": generic_preflight,
            "duplicate": duplicate,
            "history_matches": history_matches,
            "company_history": company_history,
            "expired": expired,
            "language_mismatch": bool(mismatches),
            "language_needs_input": bool(language_questions),
            "review_reasons": reviews,
            "reasons": reasons,
            "priority": priority,
        }
        output.append({**record, "screening": screening})
    return output
