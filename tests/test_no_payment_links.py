"""No payment or donation links anywhere in the repository.

The fork owner's decision, and an easy one to undo by accident: upstream's
banner sat in twelve archived RELEASE_NOTES files as well as the README, and
.github/FUNDING.yml is what puts a "Sponsor" button on the repository page
without appearing in any rendered document at all. A merge from upstream would
bring all of it back silently.

Checked here rather than remembered.
"""

from pathlib import Path
import subprocess

import pytest

REPO = Path(__file__).parents[1]

PLATFORMS = (
    "buymeacoffee",
    "buy_me_a_coffee",
    "paypal.me",
    "patreon",
    "ko-fi",
    "liberapay",
    "opencollective",
    "tidelift",
    "issuehunt",
    "github_sponsors",
)

# Binary files nobody reads a link out of.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".woff", ".woff2", ".ico"}


def _tracked_text_files() -> list[Path]:
    """Every file git tracks.

    Asking git rather than walking the tree is what makes this stable: a walk
    also picks up .pytest_cache, which stores the node ids of this very
    module's parametrised cases and so contains the name of every platform
    below.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    here = Path(__file__).resolve()
    files = []
    for name in listing.split("\0"):
        if not name:
            continue
        path = REPO / name
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        if path.resolve() == here:
            continue  # this file names every platform it looks for
        files.append(path)
    return files


FILES = _tracked_text_files()


def test_the_sweep_actually_reads_the_repository():
    """Guards the walk: a broken glob must not pass by finding nothing."""
    assert len(FILES) > 50


@pytest.mark.parametrize("platform", PLATFORMS)
def test_no_file_carries_a_payment_link(platform):
    offenders = []
    for path in FILES:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if platform in text.lower():
            offenders.append(str(path.relative_to(REPO)))

    assert not offenders, f"{platform!r} appears in: {offenders}"


def test_there_is_no_funding_file():
    """It renders nowhere, so it is the one that comes back unnoticed."""
    assert not (REPO / ".github" / "FUNDING.yml").exists()
    assert not (REPO / ".github" / "FUNDING.yaml").exists()
