import html
import json
import re

import pytest

from app.motion_graphics.builder import (
    DEFAULT_LIBRARY_DIR,
    QuoteBuildRequest,
    build_quote_project,
    main,
    quote_request_from_scene,
    title_request_from_scene,
)
from app.script_parser import parse_script


def _attribute_json(document: str, attribute: str, occurrence: int = 0):
    matches = re.findall(rf"{re.escape(attribute)}='(.*?)'", document, flags=re.S)
    assert len(matches) > occurrence
    return json.loads(html.unescape(matches[occurrence]))


def test_build_quote_project_generates_self_contained_hyperframes_source(tmp_path):
    output = tmp_path / "quote-job"
    request = QuoteBuildRequest(
        kicker="Builder's quote preview",
        quote_lines=("Words first.", "Pictures follow."),
        accent_line=1,
        speaker_name="Noor",
        speaker_role="DIRECTOR",
        response_speaker="",
        response_line="",
        context_line="UNIT TEST · NO RESPONSE",
        duration_sec=7.5,
    )

    result = build_quote_project(request, output)

    expected_files = {
        "index.html",
        "variables.json",
        "package.json",
        "hyperframes.json",
        "meta.json",
        "motion-graphics-build.json",
        "compositions/quote-stage.html",
        "compositions/quote-text.html",
        "assets/lib/gsap.min.js",
        "assets/lib/three.min.js",
    }
    assert expected_files <= set(result.files)
    assert all((output / relative).is_file() for relative in expected_files)
    assert json.loads(result.variables_path.read_text(encoding="utf-8")) == result.variables

    index = result.index_path.read_text(encoding="utf-8")
    assert 'data-duration="7.5"' in index
    assert 'id="quote-stage"' in index
    assert 'data-composition-src="compositions/quote-stage.html"' in index
    assert 'id="quote-text"' in index
    assert 'data-composition-src="compositions/quote-text.html"' in index

    schema = _attribute_json(index, "data-composition-variables")
    assert {entry["id"] for entry in schema} == set(result.variables)
    response_schema = next(entry for entry in schema if entry["id"] == "has_response")
    assert response_schema == {
        "id": "has_response",
        "type": "boolean",
        "label": "Has response",
        "default": False,
    }

    stage_values = _attribute_json(index, "data-variable-values", occurrence=0)
    text_values = _attribute_json(index, "data-variable-values", occurrence=1)
    assert stage_values["has_response"] is False
    assert "quote_line_1" not in stage_values
    assert text_values["kicker"] == "Builder's quote preview"
    assert text_values["speaker_name"] == "Noor"
    assert text_values["response_line"] == ""

    generated_sources = "\n".join(
        (output / relative).read_text(encoding="utf-8")
        for relative in (
            "index.html",
            "compositions/quote-stage.html",
            "compositions/quote-text.html",
        )
    )
    assert "__DURATION__" not in generated_sources
    assert "__RESPONSE_START__" not in generated_sources
    assert "__CONTEXT_DURATION__" not in generated_sources

    manifest = json.loads(
        (output / "motion-graphics-build.json").read_text(encoding="utf-8")
    )
    assert manifest["template"] == "quote"
    assert manifest["request"]["speaker_name"] == "Noor"

    for filename in ("gsap.min.js", "three.min.js"):
        assert (output / "assets/lib" / filename).stat().st_size == (
            DEFAULT_LIBRARY_DIR / filename
        ).stat().st_size


def test_quote_request_defaults_and_font_sizes():
    request = QuoteBuildRequest(quote_lines=("SHORT", "A MUCH LONGER QUOTE LINE"))

    assert request.accent_line == 2
    assert request.has_response is True
    assert request.quote_font_sizes[1] < request.quote_font_sizes[0]
    assert request.variables()["quote_line_3"] == ""


def test_scene_adapters_use_actual_parser_dialogue_schema():
    scene = parse_script(
        "Bilal says: 'Can words move?' Zara replies: 'Yes, locally.'"
    )[0]

    quote = quote_request_from_scene(scene)
    title = title_request_from_scene(scene, title_lines=("WORDS", "MOVE"))

    assert quote.speaker_name == "Bilal"
    assert quote.quote_lines == ("Can words move?",)
    assert quote.response_speaker == "Zara"
    assert quote.response_line == "Yes, locally."
    assert quote.duration_sec == 6.0
    assert title.sublines == ("Can words move?",)


def test_quote_request_from_scene_wraps_long_dialogue_and_can_skip_response():
    scene = {
        "location": "fort",
        "time_of_day": "night",
        "duration_sec": 20,
        "characters": ["Bilal", "Zara"],
        "dialogue": [
            {
                "speaker": "Bilal",
                "line": "A single line can become a moving scene when timing is clear",
            },
            {"speaker": "Zara", "line": "Then let it move."},
        ],
    }

    request = quote_request_from_scene(scene, include_response=False)

    assert request.duration_sec == 12.0
    assert len(request.quote_lines) == 3
    assert all(len(line) <= 30 for line in request.quote_lines)
    assert request.has_response is False
    assert request.kicker == "FORT · NIGHT"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quote_lines": ()},
        {"quote_lines": ("A", "B", "C", "D")},
        {"quote_lines": ("A",), "accent_line": 2},
        {"quote_lines": ("A",), "accent_line": True},
        {"quote_lines": ("A" * 31,)},
        {"speaker_name": ""},
        {"response_speaker": "Zara", "response_line": ""},
        {"response_speaker": "", "response_line": "Hello"},
        {"duration_sec": 5.9},
        {"muted_color": "grey"},
    ],
)
def test_quote_request_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        QuoteBuildRequest(**kwargs)


def test_quote_cli_builds_project(tmp_path, capsys):
    output = tmp_path / "cli-quote"

    exit_code = main(
        [
            "--template",
            "quote",
            "--output",
            str(output),
            "--quote-line",
            "CLI WORDS",
            "--speaker-name",
            "Tester",
            "--response-speaker",
            "",
            "--response-line",
            "",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Built Quote project" in captured.out
    variables = json.loads((output / "variables.json").read_text(encoding="utf-8"))
    assert variables["quote_line_1"] == "CLI WORDS"
    assert variables["speaker_name"] == "Tester"
    assert variables["has_response"] is False
