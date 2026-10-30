import html
import json
import re

import pytest

from app.motion_graphics.builder import (
    DEFAULT_LIBRARY_DIR,
    ShapeBuildRequest,
    build_shape_project,
    main,
)


def _attribute_json(document: str, attribute: str, occurrence: int = 0):
    matches = re.findall(rf"{re.escape(attribute)}='(.*?)'", document, flags=re.S)
    assert len(matches) > occurrence
    return json.loads(html.unescape(matches[occurrence]))


def test_build_shape_project_generates_self_contained_hyperframes_source(tmp_path):
    output = tmp_path / "shape-job"
    request = ShapeBuildRequest(
        kicker="Builder's shape preview",
        headline_lines=("SYSTEM", "IN FORM"),
        accent_line=1,
        statement_line="A cube can stand for a modular system.",
        feature_lines=("Stable base", "Swappable parts"),
        shape_kind="cube",
        node_labels=("BASE", "MODULE"),
        duration_sec=7.5,
    )

    result = build_shape_project(request, output)

    expected_files = {
        "index.html",
        "variables.json",
        "package.json",
        "hyperframes.json",
        "meta.json",
        "motion-graphics-build.json",
        "compositions/shape-stage.html",
        "compositions/shape-text.html",
        "assets/lib/gsap.min.js",
        "assets/lib/three.min.js",
    }
    assert expected_files <= set(result.files)
    assert all((output / relative).is_file() for relative in expected_files)
    assert json.loads(result.variables_path.read_text(encoding="utf-8")) == result.variables

    index = result.index_path.read_text(encoding="utf-8")
    assert 'data-duration="7.5"' in index
    assert 'id="shape-stage"' in index
    assert 'data-composition-src="compositions/shape-stage.html"' in index
    assert 'id="shape-text"' in index
    assert 'data-composition-src="compositions/shape-text.html"' in index

    schema = _attribute_json(index, "data-composition-variables")
    assert {entry["id"] for entry in schema} == set(result.variables)
    shape_schema = next(entry for entry in schema if entry["id"] == "shape_kind")
    assert shape_schema["type"] == "enum"
    assert shape_schema["default"] == "cube"
    assert {option["value"] for option in shape_schema["options"]} == {
        "orb",
        "cube",
        "pyramid",
        "ring",
    }

    stage_values = _attribute_json(index, "data-variable-values", occurrence=0)
    text_values = _attribute_json(index, "data-variable-values", occurrence=1)
    assert stage_values["shape_kind"] == "cube"
    assert stage_values["node_count"] == 2
    assert stage_values["node_label_2"] == "MODULE"
    assert "headline_line_1" not in stage_values
    assert text_values["kicker"] == "Builder's shape preview"
    assert text_values["accent_line"] == 1
    assert text_values["feature_line_3"] == ""

    generated_sources = "\n".join(
        (output / relative).read_text(encoding="utf-8")
        for relative in (
            "index.html",
            "compositions/shape-stage.html",
            "compositions/shape-text.html",
        )
    )
    assert "__DURATION__" not in generated_sources
    assert "__STATEMENT_START__" not in generated_sources
    assert "__FEATURES_DURATION__" not in generated_sources

    manifest = json.loads(
        (output / "motion-graphics-build.json").read_text(encoding="utf-8")
    )
    assert manifest["template"] == "shape"
    assert manifest["request"]["shape_kind"] == "cube"
    assert manifest["request"]["node_labels"] == ["BASE", "MODULE"]

    for filename in ("gsap.min.js", "three.min.js"):
        assert (output / "assets/lib" / filename).stat().st_size == (
            DEFAULT_LIBRARY_DIR / filename
        ).stat().st_size


def test_shape_request_normalizes_kind_and_defaults_accent_to_last_line():
    request = ShapeBuildRequest(
        headline_lines=("FORM",),
        shape_kind=" PYRAMID ",
        feature_lines=(),
        node_labels=(),
    )

    assert request.shape_kind == "pyramid"
    assert request.accent_line == 1
    assert request.variables()["node_count"] == 0
    assert request.variables()["feature_line_1"] == ""


def test_shape_headline_sizes_shrink_for_long_lines():
    short = ShapeBuildRequest(headline_lines=("GO", "NOW"))
    long = ShapeBuildRequest(headline_lines=("EXTRAORDINARY", "TRANSFORMATION"))

    assert long.headline_font_sizes[0] < short.headline_font_sizes[0]
    assert long.headline_font_sizes[1] < short.headline_font_sizes[1]
    assert min(long.headline_font_sizes) >= 56


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headline_lines": ()},
        {"headline_lines": ("A", "B", "C")},
        {"headline_lines": ("A",), "accent_line": 2},
        {"headline_lines": ("A",), "accent_line": True},
        {"feature_lines": ("A", "B", "C", "D")},
        {"node_labels": ("A", "B", "C", "D")},
        {"node_labels": ("SAME", "same")},
        {"shape_kind": "sphere"},
        {"statement_line": ""},
        {"duration_sec": 5.9},
        {"muted_color": "grey"},
    ],
)
def test_shape_request_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        ShapeBuildRequest(**kwargs)


def test_shape_cli_builds_project(tmp_path, capsys):
    output = tmp_path / "cli-shape"

    exit_code = main(
        [
            "--template",
            "shape",
            "--output",
            str(output),
            "--shape-kind",
            "ring",
            "--node-label",
            "LOOP",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Built Shape project" in captured.out
    variables = json.loads((output / "variables.json").read_text(encoding="utf-8"))
    assert variables["shape_kind"] == "ring"
    assert variables["node_count"] == 1
    assert variables["node_label_1"] == "LOOP"
