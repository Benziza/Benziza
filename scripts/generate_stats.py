#!/usr/bin/env python3
"""Generate self-hosted SVG cards for the profile README."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any


USERNAME = os.getenv("GITHUB_USERNAME", "Benziza")
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets"
TOKEN = os.getenv("GITHUB_TOKEN", "")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"{USERNAME}-profile-stats",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

LANGUAGE_COLORS = {
    "C#": "#178600",
    "CSS": "#663399",
    "Dart": "#00B4AB",
    "Go": "#00ADD8",
    "HTML": "#e34c26",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Kotlin": "#A97BFF",
    "PHP": "#4F5D95",
    "Python": "#3572A5",
    "Shell": "#89e051",
    "TypeScript": "#3178c6",
    "Vue": "#41b883",
}


def request_text(url: str, *, api: bool = True) -> str:
    headers = HEADERS if api else {"User-Agent": HEADERS["User-Agent"]}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub request failed ({error.code}) for {url}: {details}") from error


def request_json(url: str) -> Any:
    return json.loads(request_text(url))


def get_repositories() -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = request_json(
            f"https://api.github.com/users/{USERNAME}/repos"
            f"?type=owner&sort=updated&per_page=100&page={page}"
        )
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
        page += 1


def get_languages(repositories: list[dict[str, Any]]) -> Counter[str]:
    totals: Counter[str] = Counter()
    for repository in repositories:
        if repository.get("fork") or repository.get("disabled"):
            continue
        totals.update(request_json(repository["languages_url"]))
    return totals


def get_contributions() -> dict[date, int]:
    contribution_html = request_text(
        f"https://github.com/users/{USERNAME}/contributions", api=False
    )
    pattern = re.compile(
        r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*>\s*</td>\s*'
        r'<tool-tip[^>]*>([^<]+)</tool-tip>',
        re.DOTALL,
    )
    contributions: dict[date, int] = {}
    for iso_date, tooltip in pattern.findall(contribution_html):
        match = re.match(r"(\d+) contributions?", tooltip)
        contributions[date.fromisoformat(iso_date)] = int(match.group(1)) if match else 0

    if not contributions:
        raise RuntimeError("GitHub contribution calendar could not be parsed")
    return contributions


def calculate_streaks(
    contributions: dict[date, int],
) -> tuple[int, date | None, date | None, int, date | None, date | None]:
    ordered_days = sorted(contributions)
    latest = ordered_days[-1]

    current_end = latest
    if contributions.get(current_end, 0) == 0:
        current_end -= timedelta(days=1)

    current_start = current_end
    while contributions.get(current_start, 0) > 0:
        current_start -= timedelta(days=1)
    current_start += timedelta(days=1)
    current_length = (
        (current_end - current_start).days + 1
        if contributions.get(current_end, 0) > 0
        else 0
    )

    longest_length = 0
    longest_start: date | None = None
    longest_end: date | None = None
    run_start: date | None = None
    previous_day: date | None = None

    for day in ordered_days:
        if contributions[day] > 0:
            if run_start is None or previous_day is None or day != previous_day + timedelta(days=1):
                run_start = day
            run_length = (day - run_start).days + 1
            if run_length > longest_length:
                longest_length = run_length
                longest_start = run_start
                longest_end = day
            previous_day = day
        else:
            run_start = None
            previous_day = None

    return (
        current_length,
        current_start if current_length else None,
        current_end if current_length else None,
        longest_length,
        longest_start,
        longest_end,
    )


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def card_start(title: str, height: int = 200) -> list[str]:
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" width="420" '
        f'height="{height}" viewBox="0 0 420 {height}" role="img" aria-label="{escape(title)}">',
        "<style>",
        "  .title { fill: #58a6ff; font: 600 18px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }",
        "  .label { fill: #8b949e; font: 400 12px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }",
        "  .value { fill: #c9d1d9; font: 600 23px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }",
        "  .small { fill: #8b949e; font: 400 11px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }",
        "</style>",
        f'<rect width="419" height="{height - 1}" x="0.5" y="0.5" rx="6" fill="#0d1117" stroke="#30363d"/>',
        f'<text x="22" y="32" class="title">{escape(title)}</text>',
    ]


def metric(lines: list[str], x: int, y: int, label: str, value: object) -> None:
    lines.append(f'<circle cx="{x}" cy="{y - 5}" r="4" fill="#58a6ff"/>')
    lines.append(f'<text x="{x + 12}" y="{y}" class="label">{escape(label)}</text>')
    lines.append(f'<text x="{x + 12}" y="{y + 25}" class="value">{escape(value)}</text>')


def generate_stats_card(user: dict[str, Any], repositories: list[dict[str, Any]], total: int) -> str:
    original_repositories = [repo for repo in repositories if not repo.get("fork")]
    stars = sum(repo.get("stargazers_count", 0) for repo in original_repositories)
    forks = sum(repo.get("forks_count", 0) for repo in original_repositories)

    lines = card_start(f"{USERNAME}'s GitHub Stats")
    metric(lines, 24, 70, "Total Stars", stars)
    metric(lines, 220, 70, "Total Forks", forks)
    metric(lines, 24, 132, "Public Repositories", user["public_repos"])
    metric(lines, 220, 132, "Contributions (1 year)", total)
    lines.append(f'<text x="24" y="184" class="small">{escape(user["followers"])} followers</text>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def format_period(start: date | None, end: date | None) -> str:
    if not start or not end:
        return "No active streak"
    if start == end:
        return start.strftime("%b %d, %Y")
    return f'{start.strftime("%b %d")} - {end.strftime("%b %d, %Y")}'


def generate_streak_card(contributions: dict[date, int]) -> str:
    current, current_start, current_end, longest, longest_start, longest_end = calculate_streaks(
        contributions
    )
    total = sum(contributions.values())
    columns = [
        (70, current, "Current streak", format_period(current_start, current_end)),
        (210, longest, "Longest streak", format_period(longest_start, longest_end)),
        (350, total, "Contributions", "Last 12 months"),
    ]

    lines = card_start("GitHub Contribution Streak")
    lines.extend(
        [
            '<line x1="140" y1="57" x2="140" y2="168" stroke="#30363d"/>',
            '<line x1="280" y1="57" x2="280" y2="168" stroke="#30363d"/>',
        ]
    )
    for x, value, label, period in columns:
        lines.append(f'<text x="{x}" y="94" text-anchor="middle" class="value">{escape(value)}</text>')
        lines.append(f'<text x="{x}" y="119" text-anchor="middle" class="label">{escape(label)}</text>')
        lines.append(f'<text x="{x}" y="145" text-anchor="middle" class="small">{escape(period)}</text>')
    lines.append('<text x="210" y="184" text-anchor="middle" class="small">Generated from the public contribution calendar</text>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def generate_languages_card(languages: Counter[str]) -> str:
    top_languages = languages.most_common(5)
    total = sum(languages.values()) or 1
    lines = card_start("Most Used Languages")

    for index, (language, size) in enumerate(top_languages):
        y = 57 + index * 27
        percentage = size / total * 100
        color = LANGUAGE_COLORS.get(language, "#8b949e")
        width = max(3, round(205 * percentage / 100))
        lines.extend(
            [
                f'<circle cx="26" cy="{y - 4}" r="5" fill="{color}"/>',
                f'<text x="38" y="{y}" class="label">{escape(language)}</text>',
                f'<rect x="145" y="{y - 11}" width="205" height="9" rx="4.5" fill="#21262d"/>',
                f'<rect x="145" y="{y - 11}" width="{width}" height="9" rx="4.5" fill="{color}"/>',
                f'<text x="395" y="{y}" text-anchor="end" class="small">{percentage:.1f}%</text>',
            ]
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> None:
    user = request_json(f"https://api.github.com/users/{USERNAME}")
    repositories = get_repositories()
    languages = get_languages(repositories)
    contributions = get_contributions()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cards = {
        "github-stats.svg": generate_stats_card(user, repositories, sum(contributions.values())),
        "github-streak.svg": generate_streak_card(contributions),
        "top-languages.svg": generate_languages_card(languages),
    }
    for filename, content in cards.items():
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8", newline="\n")
        print(f"Generated {OUTPUT_DIR / filename}")


if __name__ == "__main__":
    main()
