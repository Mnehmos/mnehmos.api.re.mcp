"""Infrastructure smoke test: the repo knows how to be helped.

Verifies the safety infrastructure Ch34 of the vibe coders bible requires
before any feature work, and keeps the documented evidence vocabulary in sync
with the canonical schemas — docs that lie are worse than no docs.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GOVERNANCE_FILES = [
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "PROJECT_CONTEXT.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE.txt",
    "pytest.ini",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".agent/handoff-template.md",
    "docs/architecture.md",
    "docs/security-model.md",
    "docs/evidence-model.md",
    "docs/tool-surface.md",
    "docs/roadmap.md",
    "docs/evaluation.md",
    "docs/decisions/000-adr-template.md",
    "docs/decisions/001-model-role-card.md",
    "docs/decisions/002-weights-specification-verdict.md",
    "docs/decisions/003-passive-only-by-construction.md",
    "docs/decisions/004-redaction-at-ingestion.md",
    "docs/decisions/005-action-enum-tool-surface.md",
    "docs/decisions/006-dual-target-benchmark.md",
    "docs/decisions/007-storage-layout.md",
]

EXPECTED_LEVELS = [
    "CONFIRMED",
    "OBSERVED",
    "STRONGLY_INFERRED",
    "INFERRED",
    "HYPOTHESIS",
    "UNKNOWN",
]


def test_governance_files_exist():
    missing = [f for f in GOVERNANCE_FILES if not (REPO / f).exists()]
    assert not missing, f"safety infrastructure missing: {missing}"


def test_gitignore_carries_secrets_block():
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi and "!.env.example" in gi, "TMRI secrets block missing"
    assert "apire_kb/" in gi and "installers/" in gi, "evidence-store ignores missing"


def test_schemas_are_valid_json():
    schemas = sorted((REPO / "schemas").glob("*.schema.json"))
    assert len(schemas) >= 5, "canonical schemas missing"
    for path in schemas:
        json.loads(path.read_text(encoding="utf-8"))  # raises on invalid


def test_evidence_vocabulary_is_consistent_between_schema_and_doc():
    link = json.loads((REPO / "schemas" / "evidence-link.schema.json").read_text(encoding="utf-8"))
    schema_levels = link["properties"]["level"]["enum"]
    assert schema_levels == EXPECTED_LEVELS

    doc = (REPO / "docs" / "evidence-model.md").read_text(encoding="utf-8")
    for level in EXPECTED_LEVELS:
        assert f"`{level}`" in doc, f"level {level} documented inconsistently"

    schema_classes = link["properties"]["provenance"]["items"]["properties"]["class"]["enum"]
    assert "llm_proposal" in schema_classes, "the zero-cap class must exist"
    for cls in schema_classes:
        assert f"`{cls}`" in doc, f"provenance class {cls} not documented in evidence-model.md"


def test_llm_proposal_has_zero_cap_in_docs():
    doc = (REPO / "docs" / "evidence-model.md").read_text(encoding="utf-8")
    row = [ln for ln in doc.splitlines() if ln.startswith("| `llm_proposal`")]
    assert row and "**0.00**" in row[0], "llm_proposal cap must stay pinned at 0.00"


def test_no_transmission_verbs_in_tool_surface():
    surface = (REPO / "docs" / "tool-surface.md").read_text(encoding="utf-8")
    forbidden = ["send", "replay", "execute", "invoke_endpoint", "request.call"]
    for verb in forbidden:
        assert f"`{verb}`" not in surface, f"transmission verb '{verb}' appeared in the tool surface"
