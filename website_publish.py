from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CASE_STUDY_TITLE = "Nonresponse Bias Assessment"
CASE_STUDY_SLUG = "nonresponse-bias-assessment"
CASE_STUDY_DATE = "2026"
CASE_STUDY_LEDE = (
    "A simulated survey study using a known 50,000-person population to quantify "
    "nonresponse bias and test how demographic weighting reduces it."
)
WEBSITE_REPOSITORY = "ag-prudenzano/ag-prudenzano.github.io"
WEBSITE_REMOTE = f"https://github.com/{WEBSITE_REPOSITORY}.git"
WEBSITE_BRANCH = "main"
TEMPLATE_PAGE = "survey-response-quality-audit.html"
SCRIPT_FILE = "script.js"
INDEX_FILE = "index.html"
PUBLISH_TOKEN_ENV = "PORTFOLIO_PUBLISH_TOKEN"
TEMPLATE_TITLE = "Survey Response Quality Audit"
TEMPLATE_SLUG = "survey-response-quality-audit"
TEMPLATE_LEDE = (
    "A simulated audit of 1,250 UK online survey responses using eight "
    "respondent-level quality checks to identify records for review or exclusion."
)


def run_command(args, *, cwd, check=True, env=None):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True, env=env)


def source_repository_is_clean():
    result = run_command(
        ["git", "status", "--porcelain", "--", "report.md", "data", "outputs", "figures"],
        cwd=ROOT,
    )
    return not result.stdout.strip()


def get_publish_environment():
    token = os.environ.get(PUBLISH_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(
            f"Automatic website publishing needs a one-time Codespaces secret named {PUBLISH_TOKEN_ENV}. "
            f"The secret must contain a GitHub token that can write repository contents in {WEBSITE_REPOSITORY}."
        )
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    env.pop("GITHUB_TOKEN", None)
    return env


def configure_git_credentials(env):
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI is required for automatic website publishing in this Codespace.")
    setup = subprocess.run(["gh", "auth", "setup-git"], cwd=ROOT, check=False, capture_output=True, text=True, env=env)
    if setup.returncode:
        raise RuntimeError(f"Could not configure GitHub credentials: {(setup.stderr or setup.stdout).strip()}")


def update_publication_map(text):
    entry = f'  "{CASE_STUDY_TITLE}": {{\n    href: "{CASE_STUDY_SLUG}.html",\n    date: "{CASE_STUDY_DATE}",\n  }},'
    pattern = re.compile(rf'  "{re.escape(CASE_STUDY_TITLE)}": \{{\n    href: "[^"]+",\n    date: "[^"]+",\n  \}},')
    if pattern.search(text):
        return pattern.sub(entry, text, count=1)
    marker = "const publishedPortfolioStudies = {\n"
    if marker not in text:
        raise RuntimeError("Could not find the website publication map in script.js.")
    return text.replace(marker, marker + entry + "\n", 1)


def build_report_page(text):
    return text.replace(TEMPLATE_TITLE, CASE_STUDY_TITLE).replace(TEMPLATE_SLUG, CASE_STUDY_SLUG).replace(TEMPLATE_LEDE, CASE_STUDY_LEDE)


def publish_website():
    if not (ROOT / "report.md").exists():
        print("Website publishing skipped: report.md does not exist yet.")
        return
    if not source_repository_is_clean():
        print("Website publishing skipped because generated case-study files have uncommitted changes.")
        return
    env = get_publish_environment()
    configure_git_credentials(env)
    commit = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="portfolio-website-") as temp_dir:
        website = Path(temp_dir) / "website"
        clone = run_command(["git", "clone", "--depth", "1", "--branch", WEBSITE_BRANCH, WEBSITE_REMOTE, str(website)], cwd=Path(temp_dir), check=False, env=env)
        if clone.returncode:
            raise RuntimeError(f"Could not clone website repository: {(clone.stderr or clone.stdout).strip()}")
        name = run_command(["git", "config", "user.name"], cwd=ROOT, check=False).stdout.strip() or "AG Prudenzano"
        email = run_command(["git", "config", "user.email"], cwd=ROOT, check=False).stdout.strip() or "309410350+ag-prudenzano@users.noreply.github.com"
        run_command(["git", "config", "user.name", name], cwd=website)
        run_command(["git", "config", "user.email", email], cwd=website)
        script = website / SCRIPT_FILE
        script.write_text(update_publication_map(script.read_text(encoding="utf-8")), encoding="utf-8")
        template = (website / TEMPLATE_PAGE).read_text(encoding="utf-8")
        (website / f"{CASE_STUDY_SLUG}.html").write_text(build_report_page(template), encoding="utf-8")
        index = website / INDEX_FILE
        index.write_text(re.sub(r'script\.js\?v=[^"]+', f"script.js?v=published-{CASE_STUDY_SLUG}-{commit}", index.read_text(encoding="utf-8"), count=1), encoding="utf-8")
        if not run_command(["git", "status", "--porcelain"], cwd=website).stdout.strip():
            print("Website is already up to date.")
            return
        run_command(["git", "add", "--", SCRIPT_FILE, INDEX_FILE, f"{CASE_STUDY_SLUG}.html"], cwd=website)
        run_command(["git", "commit", "-m", f"Publish {CASE_STUDY_TITLE}"], cwd=website)
        push = run_command(["git", "push", "origin", WEBSITE_BRANCH], cwd=website, check=False, env=env)
        if push.returncode:
            raise RuntimeError(f"Could not push the website update: {(push.stderr or push.stdout).strip()}")
        print(f"Website updated and pushed to {WEBSITE_REPOSITORY}.")
