#!/usr/bin/env python3
"""Fail when the generated Context Window site contains broken internal links."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attr in ("href", "src"):
            value = values.get(attr)
            if value:
                self.links.append((attr, value))


# Paths served by the hosting platform at runtime, not present in the repo
PLATFORM_PATH_PREFIXES = ("/_vercel/",)


def target_path(root: Path, source: Path, value: str) -> Path | None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith(("mailto:", "tel:", "data:")):
        return None
    path = unquote(parsed.path)
    if not path or path.startswith(PLATFORM_PATH_PREFIXES):
        return None
    target = root / path.lstrip("/") if path.startswith("/") else source.parent / path
    if path.endswith("/"):
        target = target / "index.html"
    return target.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    args = parser.parse_args()
    root = args.site_dir.resolve()
    errors: list[str] = []

    for page in sorted(root.rglob("*.html")):
        links = LinkParser()
        links.feed(page.read_text(encoding="utf-8"))
        for attr, value in links.links:
            target = target_path(root, page, value)
            if target is not None and not target.exists():
                errors.append(f"{page.relative_to(root)}: {attr}={value} -> missing {target.relative_to(root)}")

    for required in ("index.html", "podcast-cover.png", "static/site.css"):
        if not (root / required).exists():
            errors.append(f"missing required site file: {required}")

    if errors:
        raise SystemExit("Broken site links:\n" + "\n".join(errors))
    print(f"All internal links resolve in {root}")


if __name__ == "__main__":
    main()
