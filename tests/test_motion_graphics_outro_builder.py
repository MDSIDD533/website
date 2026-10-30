import html
import json
import re

import pytest

from app.motion_graphics.builder import (
    DEFAULT_LIBRARY_DIR,
    OutroBuildRequest,
    build_outro_project,
    main,
)


def _attribute_json(document: str, attribute: str, occurrence: int = 0):
    matches = re.findall(rf"{re.escape(attribute)}='(.*?)'", document, flags=re.S)
    assert len(matches) > occurrence
    return json.loads(html.unescape(matches[occurrence]))


def test_build_outro_project_generates_self_contained_hyperframes_source(tmp_path):
    output = tmp_path / "outro-job"
    request = OutroBuildRequest(
        kicker="Builder's closing preview",
        closing_lines=("FADE OUT",),
        accent_line=1,
        tagline="One last frame.",
        brand_label="TEST STUDIO",
        glyph="T",
        credit_lines=(),
        cta_label="",
        duration_sec=6.5,
    )

    result = build_outro_project(request, output)

    expected_files = {
        "index.html",
        "variables.json",
        "package.json",
        "hyperframes.json",
        "meta.json",
        "motion-graphics-build.json",
        "compositions/outro-stage.html",
        "compositions/outro-text.html",
        "assets/lib/gsap.min.js",
        "assets/lib/three.min.js",
    }
    assert expected_files <= set(result.files)
    assert all((output / relative).is_file() for relative in expected_files)
    assert json.loads(result.variables_path.read_text(encoding="utf-8")) == result.variables

    index = result.index_path.read_text(encoding="utf-8")
    assert 'data-duration="6.5"' in index
    assert 'id="outro-stage"' in index
    assert 'data-composition-src="compositions/outro-stage.html"' in index
    assert 'id="outro-text"' in index
    assert 'data-composition-src="compositions/outro-text.html"' in index

    schema = _attribute_json(index, "data-composition-variables")
    assert {entry["id"] for entry in schema} == set(result.variables)
    credit_schema = next(entry for entry in schema if entry["id"] == "credit_count")
    assert credit_schema == {
        "id": "credit_count",
        "type": "number",
        "label": "Credit count",
        "default": 0,
        "min": 0,
        "max": 3,
        "step": 1,
    }

    stage_values = _attribute_json(index, "data-variable-values", occurrence=0)
    text_values = _attribute_json(index, "data-variable-values", occurrence=1)
    assert "closing_line_1" not in stage_values
    assert "glyph" not in stage_values
    assert text_values["kicker"] == "Builder's closing preview"
    assert text_values["glyph"] == "T"
    assert text_values["credit_count"] == 0
    assert text_values["cta_label"] == ""

    generated_sources = "\n".join(
        (output / relative).read_text(encoding="utf-8")
        for relative in (
            "index.html",
            "compositions/outro-stage.html",
            "compositions/outro-text.html",
        )
    )
    assert "__DURATION__" not in generated_sources
    assert "__CREDITS_START__" not in generated_sources
    assert "__CTA_DURATION__" not in generated_sources

    manifest = json.loads(
        (output / "motion-graphics-build.json").read_text(encoding="utf-8")
    )
    assert manifest["template"] == "outro"
    assert manifest["request"]["brand_label"] == "TEST STUDIO"

    for filename in ("gsap.min.js", "three.min.js"):
        assert (output / "assets/lib" / filename).stat().st_size == (
            DEFAULT_LIBRARY_DIR / filename
        ).stat().st_size


def test_outro_request_defaults_and_font_sizes():
    request = OutroBuildRequest(closing_lines=("END", "A MUCH LONGER ENDING NOW"))

    assert request.accent_line == 2
    assert request.closing_font_sizes[1] < request.closing_font_sizes[0]
    assert request.variables()["closing_line_3"] == ""
    assert request.variables()["credit_count"] == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"closing_lines": ()},
        {"closing_lines": ("A", "B", "C", "D")},
        {"closing_lines": ("A",), "accent_line": 2},
        {"closing_lines": ("A",), "accent_line": True},
        {"closing_lines": ("A" * 25,)},
        {"brand_label": ""},
        {"glyph": ""},
        {"glyph": "AB"},
        {"credit_lines": ("A", "B", "C", "D")},
        {"credit_lines": ("A" * 27, "B" * 27, "C" * 27)},
        {"duration_sec": 4.9},
        {"duration_sec": 10.1},
        {"muted_color": "grey"},
    ],
)
def test_outro_request_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        OutroBuildRequest(**kwargs)


def test_outro_cli_builds_project(tmp_path, capsys):
    output = tmp_path / "cli-outro"

    exit_code = main(
        [
            "--template",
            "outro",
            "--output",
            str(output),
            "--outro-line",
            "CLI ENDING",
            "--tagline",
            "Built by CLI.",
            "--brand-label",
            "CLI STUDIO",
            "--glyph",
            "C",
            "--credit-line",
            "LOCAL",
            "--cta-label",
            "AGAIN",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Built Outro project" in captured.out
    variables = json.loads((output / "variables.json").read_text(encoding="utf-8"))
    assert variables["closing_line_1"] == "CLI ENDING"
    assert variables["glyph"] == "C"
    assert variables["credit_count"] == 1
    assert variables["cta_label"] == "AGAIN"
