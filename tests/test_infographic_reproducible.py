"""The infographic must be reproducible from the repository alone.

``docs/assets/infographic.svg`` is a committed artefact that CI regenerates and
byte-compares. A generator that reads anything outside the repository - a live
database, the clock, the machine's fonts - produces different bytes in CI than
the ones in the repository, and the check fails for a reason that has nothing
to do with the content.

These tests cover the two ways that used to break it:

1. the data-quality score was read from whichever warehouse happened to exist,
2. the raster exports were rewritten on every run, so the working tree was
   never clean.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_infographic.py"
FACTS = ROOT / "docs" / "assets" / "infographic-facts.json"
SVGS = (
    ROOT / "docs" / "assets" / "infographic.svg",
    ROOT / "docs" / "assets" / "infographic-dark.svg",
)


def _load():
    spec = importlib.util.spec_from_file_location("make_infographic", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_infographic"] = module
    spec.loader.exec_module(module)
    return module


generator = _load()


def test_the_committed_slide_is_current():
    """`--check` must pass against the committed artefacts."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_slide_does_not_depend_on_a_database():
    """The render must be identical with and without a usable warehouse."""
    unusable = "sqlite:////nonexistent-directory-for-this-test/x.sqlite3"
    env = {**os.environ, "DATABASE_URL": unusable, "ACTIVE_DATABASE": "sqlite"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_dq_score_comes_from_the_committed_facts():
    """The score is read from a committed file, not from a live run."""
    assert FACTS.exists(), "the slide facts file must be committed"
    import json

    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    assert isinstance(facts.get("dq_score"), (int, float))
    assert generator._measured_dq_score() == f"{float(facts['dq_score']):.2f} measured"


def test_the_slide_quotes_the_committed_score():
    """The rendered slide carries the committed number."""
    svg = generator.build_svg("light")
    import json

    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    assert f"{float(facts['dq_score']):.2f} measured" in svg


@pytest.mark.parametrize("svg_path", SVGS, ids=lambda p: p.name)
def test_regenerating_the_slide_leaves_the_binary_artefacts_alone(svg_path):
    """A regeneration that changes nothing must not rewrite the exports.

    The raster and PDF exports carry a document identifier that changes on
    every export, so rewriting them unconditionally left a modified binary in
    the working tree after every run.
    """
    before = {path: path.read_bytes() for path in SVGS if path.exists()}
    raster = ROOT / "docs" / "assets" / "infographic.png"
    raster_before = raster.read_bytes() if raster.exists() else None

    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

    for path, payload in before.items():
        assert path.read_bytes() == payload, f"{path.name} changed without a content change"
    if raster_before is not None and raster.exists():
        assert raster.read_bytes() == raster_before, "the PNG was rewritten without a content change"
