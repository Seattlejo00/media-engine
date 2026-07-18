#!/usr/bin/env python3
"""Validate and email an engineering-focused build-in-public brief."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import quote


MAX_POST_LENGTH = 280
DEFAULT_ENV_FILE = Path.home() / ".config" / "context-window" / "build-in-public.env"


def load_env_file(path: Path) -> None:
    """Load a simple KEY=VALUE file without overwriting process environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _required_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _validated_post(text: str, label: str) -> str:
    post = text.strip()
    if not post:
        raise ValueError(f"{label} must not be empty")
    if len(post) > MAX_POST_LENGTH:
        raise ValueError(f"{label} is {len(post)} characters; maximum is {MAX_POST_LENGTH}")
    return post


def validate_brief(data: dict) -> dict:
    """Return a normalized brief or raise with a precise validation error."""
    if not isinstance(data, dict):
        raise ValueError("Brief must be a JSON object")

    work_date = _required_text(data, "work_date")
    try:
        date.fromisoformat(work_date)
    except ValueError as exc:
        raise ValueError("work_date must use YYYY-MM-DD") from exc

    raw_thread = data.get("thread_posts", [])
    if not isinstance(raw_thread, list) or not 2 <= len(raw_thread) <= 3:
        raise ValueError("thread_posts must contain 2 or 3 posts")
    thread_posts = [
        _validated_post(str(post), f"thread_posts[{index}]")
        for index, post in enumerate(raw_thread)
    ]

    raw_commits = data.get("commits", [])
    if not isinstance(raw_commits, list) or not raw_commits:
        raise ValueError("commits must contain at least one commit")
    commits = []
    for index, commit in enumerate(raw_commits):
        if not isinstance(commit, dict):
            raise ValueError(f"commits[{index}] must be an object")
        commits.append(
            {
                "sha": _required_text(commit, "sha")[:12],
                "subject": _required_text(commit, "subject"),
            }
        )

    return {
        "work_date": work_date,
        "engineering_summary": _required_text(data, "engineering_summary"),
        "engineering_insight": _required_text(data, "engineering_insight"),
        "standalone_post": _validated_post(
            _required_text(data, "standalone_post"), "standalone_post"
        ),
        "thread_posts": thread_posts,
        "commits": commits,
    }


def _composer_url(post: str) -> str:
    return "https://twitter.com/intent/tweet?text=" + quote(post)


def render_email(brief: dict) -> tuple[str, str, str]:
    parsed_date = date.fromisoformat(brief["work_date"])
    subject = f"Engineering build note — {parsed_date.strftime('%b %d').replace(' 0', ' ')}"
    commit_lines = "\n".join(
        f"- {commit['subject']} ({commit['sha']})" for commit in brief["commits"]
    )
    thread_text = "\n\n".join(
        f"{index}/{len(brief['thread_posts'])}\n{post}\n[{len(post)}/280]"
        for index, post in enumerate(brief["thread_posts"], start=1)
    )
    text_body = (
        f"ENGINEERING BUILD NOTE — {brief['work_date']}\n\n"
        f"WHAT CHANGED\n{brief['engineering_summary']}\n\n"
        f"ENGINEERING INSIGHT\n{brief['engineering_insight']}\n\n"
        f"STANDALONE X POST\n{brief['standalone_post']}\n"
        f"[{len(brief['standalone_post'])}/280]\n"
        f"Open in X: {_composer_url(brief['standalone_post'])}\n\n"
        f"OPTIONAL ENGINEERING THREAD\n{thread_text}\n\n"
        f"EVIDENCE\n{commit_lines}\n\n"
        "Draft only. Nothing was posted automatically."
    )

    thread_cards = "".join(
        f"""
        <div style="padding:18px;border:1px solid #ddd;border-radius:10px;margin:12px 0">
          <div style="color:#666;font-size:13px">{index}/{len(brief['thread_posts'])} · {len(post)}/280</div>
          <div style="font-size:17px;white-space:pre-wrap;margin-top:8px">{html.escape(post)}</div>
          <p><a href="{html.escape(_composer_url(post))}">Open this post in X</a></p>
        </div>
        """
        for index, post in enumerate(brief["thread_posts"], start=1)
    )
    commit_items = "".join(
        f"<li>{html.escape(commit['subject'])} <code>{html.escape(commit['sha'])}</code></li>"
        for commit in brief["commits"]
    )
    standalone = brief["standalone_post"]
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#171717;line-height:1.55">
      <p style="color:#666">Engineering build note · {html.escape(brief['work_date'])}</p>
      <h2>What changed</h2>
      <div style="white-space:pre-wrap">{html.escape(brief['engineering_summary'])}</div>
      <h2>Engineering insight</h2>
      <div style="white-space:pre-wrap">{html.escape(brief['engineering_insight'])}</div>
      <h2>Standalone X post</h2>
      <div style="font-size:20px;padding:22px;border:2px solid #222;border-radius:12px;white-space:pre-wrap">{html.escape(standalone)}</div>
      <p style="color:#666">{len(standalone)}/280 characters</p>
      <p><a href="{html.escape(_composer_url(standalone))}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:11px 16px;border-radius:8px">Open in X</a></p>
      <h2 style="margin-top:30px">Optional engineering thread</h2>
      {thread_cards}
      <h2>Evidence</h2>
      <ul>{commit_items}</ul>
      <p style="color:#666;font-size:13px">Draft only. Nothing was posted automatically.</p>
    </div>
    """.strip()
    return subject, text_body, html_body


def send_with_resend(
    api_key: str,
    from_email: str,
    to_emails: list[str],
    subject: str,
    text_body: str,
    html_body: str,
) -> str:
    payload = json.dumps(
        {
            "from": from_email,
            "to": to_emails,
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "context-window-build-in-public/2.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend rejected the email ({exc.code}): {detail}") from exc
    return str(result.get("id", "unknown"))


def _read_input(path: str) -> dict:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="Brief JSON path, or - for stdin")
    parser.add_argument("--dry-run", action="store_true", help="Print the email without sending")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.getenv("BUILD_IN_PUBLIC_ENV_FILE", DEFAULT_ENV_FILE)),
        help="Local email configuration file",
    )
    args = parser.parse_args()

    brief = validate_brief(_read_input(args.input))
    subject, text_body, html_body = render_email(brief)
    if args.dry_run:
        print(text_body)
        return 0

    load_env_file(args.env_file)
    api_key = os.getenv("RESEND_API_KEY", "")
    from_email = os.getenv("BUILD_IN_PUBLIC_FROM_EMAIL", "")
    to_emails = [
        address.strip()
        for address in os.getenv("BUILD_IN_PUBLIC_TO_EMAIL", "").split(",")
        if address.strip()
    ]
    missing = [
        name
        for name, value in (
            ("RESEND_API_KEY", api_key),
            ("BUILD_IN_PUBLIC_FROM_EMAIL", from_email),
            ("BUILD_IN_PUBLIC_TO_EMAIL", to_emails),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Missing email configuration: " + ", ".join(missing))

    email_id = send_with_resend(api_key, from_email, to_emails, subject, text_body, html_body)
    print(f"Emailed engineering build note for {brief['work_date']} (Resend id: {email_id}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Build-in-public email failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
