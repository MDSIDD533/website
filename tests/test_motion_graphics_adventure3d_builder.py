import html
import json
import re

import pytest

from app.motion_graphics.builder import (
    DEFAULT_LIBRARY_DIR,
    Adventure3DBuildRequest,
    adventure3d_request_from_text,
    build_adventure3d_project,
    main,
)


def _attribute_json(document: str, attribute: str, occurrence: int = 0):
    matches = re.findall(rf"{re.escape(attribute)}='(.*?)'", document, flags=re.S)
    assert len(matches) > occurrence
    return json.loads(html.unescape(matches[occurrence]))


def test_build_adventure3d_project_generates_self_contained_hyperframes_source(
    tmp_path,
):
    output = tmp_path / "adventure-job"
    request = Adventure3DBuildRequest(
        scene_label="WWII · NORMANDY TEST",
        caption_lines=("THE GLOBAL CONFLICT", "NORMANDY"),
        environment="montage",
        camera_move="cinematic",
        intensity=1.25,
        duration_sec=18.235,
    )

    result = build_adventure3d_project(request, output)

    expected_files = {
        "index.html",
        "variables.json",
        "package.json",
        "hyperframes.json",
        "meta.json",
        "motion-graphics-build.json",
        "compositions/adventure-stage.html",
        "compositions/adventure-overlay.html",
        "assets/lib/gsap.min.js",
        "assets/lib/three.min.js",
    }
    assert expected_files <= set(result.files)
    assert all((output / relative).is_file() for relative in expected_files)
    assert (
        json.loads(result.variables_path.read_text(encoding="utf-8"))
        == result.variables
    )

    index = result.index_path.read_text(encoding="utf-8")
    assert 'data-duration="18.235"' in index
    assert 'id="adventure-stage"' in index
    assert 'data-composition-src="compositions/adventure-stage.html"' in index
    assert 'id="adventure-overlay"' in index
    assert 'data-composition-src="compositions/adventure-overlay.html"' in index

    schema = _attribute_json(index, "data-composition-variables")
    assert {entry["id"] for entry in schema} == set(result.variables)
    environment_schema = next(
        entry for entry in schema if entry["id"] == "environment"
    )
    assert environment_schema["type"] == "enum"
    assert environment_schema["default"] == "montage"
    assert {option["value"] for option in environment_schema["options"]} == {
        "battlefield",
        "invasion",
        "coastal",
        "montage",
    }

    stage_values = _attribute_json(index, "data-variable-values", occurrence=0)
    overlay_values = _attribute_json(
        index, "data-variable-values", occurrence=1
    )
    assert stage_values["environment"] == "montage"
    assert stage_values["camera_move"] == "cinematic"
    assert stage_values["intensity"] == 1.25
    assert "caption_1" not in stage_values
    assert overlay_values["scene_label"] == "WWII · NORMANDY TEST"
    assert overlay_values["caption_count"] == 2
    assert overlay_values["caption_2"] == "NORMANDY"
    assert overlay_values["caption_4"] == ""

    generated_sources = "\n".join(
        (output / relative).read_text(encoding="utf-8")
        for relative in (
            "index.html",
            "compositions/adventure-stage.html",
            "compositions/adventure-overlay.html",
        )
    )
    assert "__DURATION__" not in generated_sources
    assert "http://" not in generated_sources
    assert "https://" not in generated_sources
    assert "makeTank" in generated_sources
    assert "makeSoldier" in generated_sources
    assert "CatmullRomCurve3" in generated_sources
    assert "window.__timelines[\"adventure-stage\"]" in generated_sources

    manifest = json.loads(
        (output / "motion-graphics-build.json").read_text(encoding="utf-8")
    )
    assert manifest["template"] == "adventure3d"
    assert manifest["request"]["environment"] == "montage"
    assert manifest["request"]["caption_lines"] == [
        "THE GLOBAL CONFLICT",
        "NORMANDY",
    ]

    for filename in ("gsap.min.js", "three.min.js"):
        assert (output / "assets/lib" / filename).stat().st_size == (
            DEFAULT_LIBRARY_DIR / filename
        ).stat().st_size


def test_adventure3d_adapter_uses_explicit_script_cues():
    montage = adventure3d_request_from_text(
        "World War II began in 1939 when Germany invaded Poland. "
        "Great Britain and France declared war. Battles reached Normandy "
        "and the Pacific islands."
    )
    coastal = adventure3d_request_from_text(
        "Landing craft crossed the sea toward the Normandy beaches."
    )
    invasion = adventure3d_request_from_text(
        "A convoy crossed the border during the invasion."
    )

    assert montage.environment == "montage"
    assert montage.caption_lines == (
        "THE GLOBAL CONFLICT",
        "1939 · INVASION",
        "WAR DECLARED",
        "NORMANDY",
    )
    assert coastal.environment == "coastal"
    assert invasion.environment == "invasion"


def test_adventure3d_request_normalizes_enums_and_rounds_intensity():
    request = Adventure3DBuildRequest(
        environment=" COASTAL ",
        camera_move=" AERIAL ",
        intensity=1.23456,
        caption_lines=("NORMANDY",),
    )

    assert request.environment == "coastal"
    assert request.camera_move == "aerial"
    assert request.intensity == 1.235
    assert request.variables()["caption_count"] == 1
    assert request.variables()["caption_4"] == ""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"caption_lines": ("A", "B", "C", "D", "E")},
        {"environment": "desert"},
        {"camera_move": "orbit"},
        {"intensity": 0.2},
        {"intensity": 2.1},
        {"duration_sec": 7.9},
        {"duration_sec": 30.1},
        {"show_caption": "yes"},
        {"sky_color": "blue"},
    ],
)
def test_adventure3d_request_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        Adventure3DBuildRequest(**kwargs)


def test_adventure3d_cli_builds_project(tmp_path, capsys):
    output = tmp_path / "cli-adventure"

    exit_code = main(
        [
            "--template",
            "adventure3d",
            "--output",
            str(output),
            "--environment",
            "coastal",
            "--camera-move",
            "tracking",
            "--caption-line",
            "NORMANDY",
            "--duration",
            "18.5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Built Adventure3D project" in captured.out
    variables = json.loads(
        (output / "variables.json").read_text(encoding="utf-8")
    )
    assert variables["environment"] == "coastal"
    assert variables["camera_move"] == "tracking"
    assert variables["caption_count"] == 1
    assert variables["caption_1"] == "NORMANDY"
