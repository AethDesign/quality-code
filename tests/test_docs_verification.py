import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


docs = load("verify_docs")
quality = load("quality_code")
GALLERY = "docs/benchmarks/serviceflow-mvp-2026-10/index.html"
HTML = '<main><h1>Title</h1><p>Before</p><div></div><a href="../../RESEARCH.md">Research</a><script>const active = 1;</script></main>'


class EditorialVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        docs.git(self.repo, "init", "--quiet")
        docs.git(self.repo, "config", "user.name", "Fixture")
        docs.git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.write("README.md", "[Research](docs/RESEARCH.md)\n")
        self.write("docs/RESEARCH.md", "# Research\n")
        self.write(GALLERY, HTML)
        docs.git(self.repo, "add", "--", "README.md", "docs")
        docs.git(self.repo, "commit", "--quiet", "-m", "fixture")

    def write(self, relative, text):
        path = self.repo / relative
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(text)

    def stage(self, relative, text):
        self.write(relative, text)
        docs.git(self.repo, "add", "--", relative)

    def test_docs_copy_and_gallery_notice_in_local_and_committed_routes(self):
        self.stage("README.md", "Updated copy. [Research](docs/RESEARCH.md)\n")
        self.stage(GALLERY, HTML.replace("<p>Before</p>", "<p><strong>Notice.</strong> New copy.</p>"))
        self.assertEqual(docs.review(self.repo, "HEAD"), [])
        docs.git(self.repo, "commit", "--quiet", "-m", "editorial")
        self.assertEqual(docs.review(self.repo, "HEAD^", "HEAD"), [])

    def test_broken_doc_link_fails_and_does_not_select_full(self):
        self.stage("README.md", "[Missing](docs/missing.md)\n")
        result = docs.review(self.repo, "HEAD")
        self.assertEqual(result, ["README.md: missing local target docs/missing.md"])

    def test_reference_titled_and_multiline_links_are_checked(self):
        for source in (
            '[Missing link][reference]\n\n[reference]: docs/missing.md\n',
            '[Missing link](docs/missing.md "title")\n',
            '[Missing link](<./docs/missing.md>)\n',
            '[Missing link](\n  docs/missing.md)\n',
            '[Missing link][ref]\n\n[ref]:\n  docs/missing.md (title)\n',
        ):
            with self.subTest(source=source):
                self.stage("README.md", source)
                target = "./docs/missing.md" if "<./" in source else "docs/missing.md"
                self.assertEqual(docs.review(self.repo, "HEAD"), [
                    f"README.md: missing local target {target}",
                ])

    def test_ambiguous_angle_destination_in_raw_html_requires_full(self):
        source = '<div>\n[Label](<a class=old>)\n</div>\n'
        self.stage("README.md", source)
        docs.git(self.repo, "commit", "--quiet", "-m", "raw HTML control")
        self.stage("README.md", source.replace("class=old", "class=new"))
        self.assertIsNone(docs.review(self.repo, "HEAD"))

    def test_link_like_text_does_not_mask_raw_markup_changes(self):
        source = '<style>.note::after { content: "Example](/one)"; }</style>'
        self.stage("README.md", source)
        docs.git(self.repo, "commit", "--quiet", "-m", "raw HTML control")
        self.stage("README.md", source.replace("/one", "/two"))
        self.assertIsNone(docs.review(self.repo, "HEAD"))

    def test_dangerous_link_scheme_is_rejected(self):
        self.stage("README.md", "[Link](javascript://example.invalid/payload)\n")
        self.assertEqual(docs.review(self.repo, "HEAD"), ["README.md: unsupported link scheme"])

    def test_scope_expands_for_scripts_templates_links_and_benchmark_data(self):
        for relative, value in (
            (GALLERY, HTML.replace("active = 1", "active = 2")),
            (GALLERY, HTML.replace("<div></div>", "<div/>")),
            (GALLERY, HTML.replace("Before", "Before</strong>")),
            (GALLERY, HTML.replace("<p>Before</p>", "<p>Before")),
            (GALLERY, HTML.replace("<script>", "<p><script>").replace("</script>", "</script></p>")),
            (GALLERY, HTML.replace('href="../../RESEARCH.md"', 'href="#other"')),
            ("README.md", "---\nlayout: dynamic\n---\nChanged\n"),
            ("docs/RESEARCH.md", "--- \t\npermalink: /different-route/\n---\nChanged\n"),
            ("README.md", "{% include snippet.html %}\n"),
            ("docs/benchmarks/serviceflow-mvp-2026-10/results.json", "{}"),
            ("scripts/quality_code.py", "print('changed')\n"),
        ):
            with self.subTest(relative=relative, value=value):
                self.stage("docs/RESEARCH.md", "# Updated research\n")
                self.stage(relative, value)
                self.assertIsNone(docs.review(self.repo, "HEAD"))
                docs.git(self.repo, "reset", "--quiet", "HEAD", "--", relative)

    def test_missing_base_removes_editorial_eligibility(self):
        self.stage("README.md", "New copy.\n")
        self.assertIsNone(docs.review(self.repo, "missing-ref", "HEAD"))

    def test_symlink_rename_and_executable_mode_require_full(self):
        path = self.repo / "README.md"
        path.unlink()
        path.symlink_to("docs/RESEARCH.md")
        docs.git(self.repo, "add", "--", "README.md")
        self.assertIsNone(docs.review(self.repo, "HEAD"))
        docs.git(self.repo, "restore", "--staged", "--worktree", "--", "README.md")
        docs.git(self.repo, "update-index", "--chmod=+x", "README.md")
        self.assertIsNone(docs.review(self.repo, "HEAD"))
        docs.git(self.repo, "restore", "--staged", "--", "README.md")
        docs.git(self.repo, "mv", "README.md", "renamed.md")
        self.assertIsNone(docs.review(self.repo, "HEAD"))

    def test_protected_path_metadata_fails_before_reading_any_blobs(self):
        with patch.object(docs, "git", side_effect=[
            b"f" * 40, b"README.md\0benchmarks/example/.env.example\0"
        ]) as command:
            self.assertIsNone(docs.review(self.repo, "HEAD"))
        self.assertEqual(command.call_count, 2)

    def test_default_benchmark_route_remains_high(self):
        areas = quality.configured_areas(quality.load_config(ROOT))
        self.assertEqual(quality.highest_risk(quality.matching_areas([GALLERY], areas)), "high")
        self.assertEqual(quality.highest_risk(quality.matching_areas(
            [GALLERY, "docs/benchmarks/serviceflow-mvp-2026-10/results.json"], areas)), "high")
        self.assertEqual(quality.highest_risk(quality.matching_areas(
            [GALLERY, ".github/workflows/verify.yml"], areas)), "critical")


if __name__ == "__main__":
    unittest.main()
