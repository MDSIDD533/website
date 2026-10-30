import html
import json
import re

import pytest

from app.motion_graphics.builder import (
    DEFAULT_LIBRARY_DIR,
    DataBuildRequest,
    DataPoint,
    build_data_project,
    main,
)


def _attribute_json(document: str, attribute: str, occurrence: int = 0):
    matches = re.findall(rf"{re.escape(attribute)}='(.*?)'", document, flags=re.S)
    assert len(matches) > occurrence
    return json.loads(html.unescape(matches[occurrence]))


def test_build_data_project_generates_self_contained_hyperframes_source(tmp_path):
    output = tmp_path / "data-job"
    request = DataBuildRequest(
        kicker="Builder's data preview",
        headline_lines=("SHARE OF", "TOTAL"),
        data_points=(
            {"label": "ALPHA", "value": 12.5},
            ("BETA", 40),
            DataPoint("GAMMA", 20),
            ("DELTA", 5),
        ),
        unit=" pts",
        value_decimals=1,
        hero_caption="points belong to the leading group",
        comparison_line="Alpha follows at 12.5 pts.",
        closing_line="Four bars fit in the same template.",
        source_line="Unit-test sample data",
        duration_sec=7.5,
    )

    result = build_data_project(request, output)

    expected_files = {
        "index.html",
        "variables.json",
        "package.json",
        "hyperframes.json",
        "meta.json",
        "motion-graphics-build.json",
        "compositions/data-stage.html",
        "compositions/data-text.html",
        "assets/lib/gsap.min.js",
        "assets/lib/three.min.js",
    }
    assert expected_files <= set(result.files)
    assert all((output / relative).is_file() for relative in expected_files)
    assert json.loads(result.variables_path.read_text(encoding="utf-8")) == result.variables

    index = result.index_path.read_text(encoding="utf-8")
    assert 'data-duration="7.5"' in index
    assert 'id="data-stage"' in index
    assert 'data-composition-src="compositions/data-stage.html"' in index
    assert 'id="data-text"' in index
    assert 'data-composition-src="compositions/data-text.html"' in index

    schema = _attribute_json(index, "data-composition-variables")
    assert {entry["id"] for entry in schema} == set(result.variables)

    stage_values = _attribute_json(index, "data-variable-values", occurrence=0)
    text_values = _attribute_json(index, "data-variable-values", occurrence=1)
    assert stage_values["point_4_label"] == "DELTA"
    assert stage_values["highlight_point"] == 2
    assert "headline_line_1" not in stage_values
    assert text_values["kicker"] == "Builder's data preview"
    assert text_values["point_1_value"] == 12.5
    assert text_values["source_line"] == "Unit-test sample data"

    generated_sources = "\n".join(
        (output / relative).read_text(encoding="utf-8")
        for relative in (
            "index.html",
            "compositions/data-stage.html",
            "compositions/data-text.html",
        )
    )
    assert "__DURATION__" not in generated_sources
    assert "__HERO_START__" not in generated_sources
    assert "__COMPARISON_DURATION__" not in generated_sources

    manifest = json.loads(
        (output / "motion-graphics-build.json").read_text(encoding="utf-8")
    )
    assert manifest["template"] == "data"
    assert manifest["request"]["data_points"][0] == {
        "label": "ALPHA",
        "value": 12.5,
    }

    for filename in ("gsap.min.js", "three.min.js"):
        assert (output / "assets/lib" / filename).stat().st_size == (
            DEFAULT_LIBRARY_DIR / filename
        ).stat().st_size


def test_data_request_defaults_highlight_to_maximum_and_formats_values():
    request = DataBuildRequest(
        data_points=(("LOW", 3), ("HIGH", 9.25)),
        unit="x",
        value_decimals=2,
    )

    assert request.highlight_point == 2
    assert request.highlighted_point.label == "HIGH"
    assert request.formatted_value(request.highlighted_point) == "9.25x"
    assert request.variables()["point_3_label"] == ""
    assert request.variables()["point_4_value"] == 0


def test_data_headline_sizes_shrink_for_long_lines():
    short = DataBuildRequest(headline_lines=("GO", "NOW"))
    long = DataBuildRequest(headline_lines=("EXTRAORDINARY", "TRANSFORMATION"))

    assert long.headline_font_sizes[0] < short.headline_font_sizes[0]
    assert long.headline_font_sizes[1] < short.headline_font_sizes[1]
    assert min(long.headline_font_sizes) >= 56


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headline_lines": ()},
        {"headline_lines": ("A", "B", "C")},
        {"data_points": (("ONLY", 1),)},
        {"data_points": tuple((f"P{i}", i) for i in range(5))},
        {"data_points": (("SAME", 1), ("same", 2))},
        {"data_points": (("A", 0), ("B", 0))},
        {"data_points": (("A", -1), ("B", 2))},
        {"data_points": (("A", 1), ("B", 2)), "highlight_point": 3},
        {"data_points": (("A", 1), ("B", 2)), "highlight_point": True},
        {"value_decimals": 4},
        {"duration_sec": 5.9},
        {"source_line": ""},
        {"muted_color": "grey"},
    ],
)
def test_data_request_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        DataBuildRequest(**kwargs)


def test_data_cli_builds_project_from_repeated_points(tmp_path, capsys):
    output = tmp_path / "cli-data"

    exit_code = main(
        [
            "--template",
            "data",
            "--output",
            str(output),
            "--data-point",
            "FIRST=10",
            "--data-point",
            "SECOND=30",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Built Data project" in captured.out
    variables = json.loads((output / "variables.json").read_text(encoding="utf-8"))
    assert variables["point_1_label"] == "FIRST"
    assert variables["point_2_value"] == 30.0
    assert variables["highlight_point"] == 2
