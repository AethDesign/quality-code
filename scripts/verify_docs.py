#!/usr/bin/env python3
"""Verify a staged or committed editorial change using only Git metadata and selected docs."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import posixpath
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = {
    "README.md", "CONTRIBUTING.md", "docs/CASE_STUDY.md", "docs/RESEARCH.md",
    "docs/DELEGATION.md", "docs/DELEGATION_ROUTING.md", "docs/GETTING_STARTED.md",
    "docs/MODULES.md", "docs/PUBLIC_EDITION.md", "docs/VISUAL_REMAKE_REVIEW.md",
    "docs/VISUAL_SOURCES.md",
    "benchmarks/serviceflow-mvp-2026-10/README.md",
    "benchmarks/serviceflow-mvp-2026-10/RESULTS.md",
    "benchmarks/serviceflow-visual-baseline-2026-10/README.md",
    "docs/index.html",
    "docs/benchmarks/serviceflow-mvp-2026-10/index.html",
    "docs/benchmarks/serviceflow-visual-baseline-2026-10/index.html",
}
REGULAR = {"100644"}
PROSE_TAGS = {"strong", "em", "b", "i"}
PROSE_BLOCKS = {"body", "main", "section", "article", "div", "header", "footer", "aside"}
PROSE_INLINE = PROSE_TAGS | {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}
RAW_TAGS = {"script", "style", "template", "textarea", "iframe", "object", "svg", "math"}
PROTECTED_FOLDERS = {"secret", "secrets", "credentials", "sensitive", "private", "scr"}
MARKDOWN_SPACE = r"[ \t]*(?:\r?\n[ \t]*)?"
MARKDOWN_DESTINATION = r"(?:<([^>\r\n]+)>|([^\s)]+))"
MARKDOWN_TITLE = r"""(?:[ \t]+(?:"[^"\r\n]*"|'[^'\r\n]*'|\([^()\r\n]*\)))?[ \t]*"""
MARKDOWN_TARGETS = (
    re.compile(r"\]\(" + MARKDOWN_SPACE + MARKDOWN_DESTINATION + MARKDOWN_TITLE + r"\)"),
    re.compile(r"^[ \t]{0,3}\[[^\]\r\n]+\]:" + MARKDOWN_SPACE
               + MARKDOWN_DESTINATION + MARKDOWN_TITLE + r"\r?$", re.MULTILINE),
)

def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def resolve(root, ref):
    return git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()


def inventory(root, commit):
    listing = (git(root, "ls-tree", "-r", "-z", "--full-tree", commit) if commit
               else git(root, "ls-files", "--stage", "-z"))
    entries = {}
    for entry in listing.decode("utf-8", errors="surrogateescape").split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            mode, _, stage_or_oid = meta.split()
            if path in entries or (not commit and stage_or_oid != "0"):
                raise ValueError("unmerged Git paths")
            entries[path] = mode
    return entries


class Markup(HTMLParser):
    def __init__(self, source, *, strict):
        super().__init__(convert_charrefs=False)
        self.strict = strict
        self.behavior = []
        self.links = []
        self.ids = set()
        self.raw = []
        self.stack = []
        self.feed(source)
        self.close()
        if self.raw or self.stack:
            raise ValueError("unfinished HTML elements")

    def record_attributes(self, attrs):
        for key, value in attrs:
            if key in {"href", "src", "poster"} and value:
                self.links.append(value)
            if key == "id" and value:
                self.ids.add(value)

    def handle_starttag(self, tag, attrs):
        parent = self.stack[-1][0] if self.stack else None
        passive = (
            self.strict and not self.raw and not attrs
            and (tag == "p" and parent in PROSE_BLOCKS
                 or tag in PROSE_TAGS and parent in PROSE_INLINE)
        )
        if tag in RAW_TAGS:
            self.raw.append(tag)
        if not passive:
            prose_ancestors = tuple(name for name, plain in self.stack if plain)
            self.behavior.append(("start", tag, tuple(attrs), prose_ancestors))
        self.record_attributes(attrs)
        if self.strict and tag not in VOID_TAGS:
            self.stack.append((tag, passive))

    def handle_endtag(self, tag):
        if self.strict:
            if not self.stack or self.stack[-1][0] != tag:
                raise ValueError("ambiguous or invalid HTML nesting")
            _, passive = self.stack.pop()
        else:
            passive = False
        if not passive:
            self.behavior.append(("end", tag))
        if self.raw and tag == self.raw[-1]:
            self.raw.pop()

    def handle_startendtag(self, tag, attrs):
        prose_ancestors = tuple(name for name, plain in self.stack if plain)
        self.behavior.append(("selfclosing", tag, tuple(attrs), prose_ancestors))
        self.record_attributes(attrs)
        if self.strict and tag not in VOID_TAGS and not any(
            ancestor in {"svg", "math"} for ancestor in self.raw
        ):
            raise ValueError("ambiguous self-closing HTML element")

    def handle_data(self, data):
        if self.raw or any(name in {"button", "option", "label"} for name, _ in self.stack):
            self.behavior.append(("data", data))

    def handle_entityref(self, name):
        if self.raw or any(tag in {"button", "option", "label"} for tag, _ in self.stack):
            self.behavior.append(("entity", name))

    def handle_charref(self, name):
        if self.raw or any(tag in {"button", "option", "label"} for tag, _ in self.stack):
            self.behavior.append(("char", name))

    def handle_comment(self, data):
        self.behavior.append(("comment", data))

    def handle_decl(self, decl):
        self.behavior.append(("decl", decl))

    def handle_pi(self, data):
        self.behavior.append(("pi", data))

    def unknown_decl(self, data):
        self.behavior.append(("unknown", data))


def parse_document(source, *, is_html):
    # Keep raw markup intact. Angled links that could also parse as HTML
    # remain in the behavior comparison and can make a diff ineligible.
    markup = Markup(source, strict=is_html)
    if not is_html:
        markup.links.extend(match[1] or match[2] for pattern in MARKDOWN_TARGETS
                            for match in pattern.finditer(source))
    return markup


def templated(source):
    first_line = source.lstrip("\ufeff").partition("\n")[0]
    return first_line.strip() == "---" or "{{" in source or "{%" in source


def protected_target(path):
    parts = path.lower().split("/")
    return any(part in PROTECTED_FOLDERS or part.startswith((".env", ".auth-secret"))
               or part.endswith((".env", ".secret", ".pem", ".key")) for part in parts)


def broken_links(path, targets, ids, paths):
    errors = []
    for target in targets:
        url = urlsplit(target)
        if url.scheme in {"http", "https", "mailto", "tel"}:
            continue
        if url.scheme:
            errors.append(f"{path}: unsupported link scheme")
            continue
        if url.netloc:
            continue
        if not url.path:
            if ids is not None and url.fragment and unquote(url.fragment) not in ids:
                errors.append(f"{path}: missing page anchor")
            continue
        link = unquote(url.path)
        destination = posixpath.normpath(
            posixpath.join("docs", link.lstrip("/")) if link.startswith("/")
            else posixpath.join(posixpath.dirname(path), link)
        )
        if protected_target(destination):
            errors.append(f"{path}: link targets a protected path")
        elif destination not in paths:
            errors.append(f"{path}: missing local target {link}")
    return errors


def review(root, base, head=None):
    """Return None for full scope or a list of editorial link findings."""
    try:
        old = resolve(root, base)
        new = resolve(root, head) if head else None
        if new:
            git(root, "merge-base", "--is-ancestor", old, new)
        comparison = [old, new] if new else ["--cached", old]
        paths = set(git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                        "--ignore-submodules=none", "--name-only", "-z", *comparison, "--").decode().split("\0")) - {""}
        if not paths or not paths <= EDITORIAL:
            return None
        before, after = inventory(root, old), inventory(root, new)
        if any(before.get(path) not in REGULAR or after.get(path) not in REGULAR for path in paths):
            return None

        destinations = {path for path in after if after[path] in {"100644", "100755"}}
        for path in tuple(destinations):
            parent = posixpath.dirname(path)
            while parent:
                destinations.add(parent)
                parent = posixpath.dirname(parent)
        destinations.add(".")
        errors = []
        for path in sorted(paths):
            previous = git(root, "show", f"{old}:{path}").decode("utf-8")
            source = git(root, "show", f"{new or ''}:{path}").decode("utf-8")
            if templated(previous) or templated(source):
                return None
            is_html = path.endswith(".html")
            original = parse_document(previous, is_html=is_html)
            current = parse_document(source, is_html=is_html)
            if original.behavior != current.behavior:
                return None
            errors.extend(broken_links(path, current.links, current.ids if is_html else None, destinations))
        return errors
    except (subprocess.CalledProcessError, UnicodeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--head", help="compare committed trees instead of the Git index")
    parser.add_argument("--ci", action="store_true", help="print docs or full for GitHub Actions")
    args = parser.parse_args()
    result = review(ROOT, args.base, args.head)
    if result is None:
        if args.ci:
            print("full")
            return 0
        print("Not an eligible staged editorial diff. Review the scope before running full verification.")
        return 2
    if result:
        for error in result:
            print(error)
        return 1
    print("docs" if args.ci else "PASS: editorial diff and local links verified without benchmark fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
