"""Build local HyperFrames projects from reusable motion-graphics templates.

Step (iii) implements the first template: a 1080p Title scene.  The builder
only generates source files; it does not invoke HyperFrames, Chromium, FFmpeg,
or any network service.  That separation keeps project generation cheap and
unit-testable, while the caller can run the pinned local HyperFrames CLI when
it is ready to render.

Content is passed to the template through HyperFrames variables:

* the generated root ``index.html`` declares the variables and their defaults;
* each composition host receives its own ``data-variable-values`` subset;
* ``variables.json`` is the canonical machine-readable payload for a future
  worker or a manual variable override.

Pinned HyperFrames 0.8.220 currently has a broken ``--variables-file`` reader
(its JSON flag helper receives ``readFile: undefined``), so the generated
project does not depend on that flag for a normal render: the same values are
already present as schema defaults and host overrides.  A caller that needs a
CLI override on 0.8.220 can pass the JSON inline with ``--variables``.

Timing still belongs to the Python builder because HyperFrames variables do
not change the root composition duration.  Duration tokens in the template
files are therefore replaced when the project is generated.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

TEMPLATE_ROOT = Path(__file__).with_name("templates")
TITLE_TEMPLATE_DIR = TEMPLATE_ROOT / "title"
DATA_TEMPLATE_DIR = TEMPLATE_ROOT / "data"
SHAPE_TEMPLATE_DIR = TEMPLATE_ROOT / "shape"
QUOTE_TEMPLATE_DIR = TEMPLATE_ROOT / "quote"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_DIR = REPO_ROOT / "dollar-reserve-currency" / "assets" / "lib"

MANIFEST_NAME = "motion-graphics-build.json"
HYPERFRAMES_VERSION = "0.8.220"
GSAP_VERSION = "3.14.2"
THREE_VERSION = "0.160.0"

TEXT_VARIABLE_IDS = (
    "kicker",
    "title_line_1",
    "title_line_2",
    "title_line_3",
    "accent_line",
    "title_line_1_size",
    "title_line_2_size",
    "title_line_3_size",
    "subline_1",
    "subline_2",
    "glyph",
    "ink_color",
    "accent_color",
    "secondary_color",
)
STAGE_VARIABLE_IDS = (
    "glyph",
    "coin_label",
    "ground_color",
    "accent_color",
    "secondary_color",
)
DATA_STAGE_VARIABLE_IDS = (
    "point_count",
    "point_1_label",
    "point_1_value",
    "point_2_label",
    "point_2_value",
    "point_3_label",
    "point_3_value",
    "point_4_label",
    "point_4_value",
    "highlight_point",
    "unit",
    "value_decimals",
    "ground_color",
    "accent_color",
    "secondary_color",
    "muted_color",
)
DATA_TEXT_VARIABLE_IDS = (
    "kicker",
    "headline_line_1",
    "headline_line_2",
    "headline_line_1_size",
    "headline_line_2_size",
    "point_count",
    "point_1_label",
    "point_1_value",
    "point_2_label",
    "point_2_value",
    "point_3_label",
    "point_3_value",
    "point_4_label",
    "point_4_value",
    "highlight_point",
    "unit",
    "value_decimals",
    "hero_caption",
    "comparison_line",
    "closing_line",
    "source_line",
    "ink_color",
    "accent_color",
    "secondary_color",
)
SHAPE_KINDS = ("orb", "cube", "pyramid", "ring")
SHAPE_STAGE_VARIABLE_IDS = (
    "shape_kind",
    "node_count",
    "node_label_1",
    "node_label_2",
    "node_label_3",
    "ground_color",
    "accent_color",
    "secondary_color",
    "muted_color",
)
SHAPE_TEXT_VARIABLE_IDS = (
    "kicker",
    "headline_line_1",
    "headline_line_2",
    "accent_line",
    "headline_line_1_size",
    "headline_line_2_size",
    "statement_line",
    "feature_line_1",
    "feature_line_2",
    "feature_line_3",
    "ink_color",
    "accent_color",
    "secondary_color",
)
QUOTE_STAGE_VARIABLE_IDS = (
    "has_response",
    "ground_color",
    "accent_color",
    "secondary_color",
    "muted_color",
)
QUOTE_TEXT_VARIABLE_IDS = (
    "kicker",
    "quote_line_1",
    "quote_line_2",
    "quote_line_3",
    "accent_line",
    "quote_line_1_size",
    "quote_line_2_size",
    "quote_line_3_size",
    "speaker_name",
    "speaker_role",
    "has_response",
    "response_speaker",
    "response_line",
    "context_line",
    "ink_color",
    "accent_color",
    "secondary_color",
)

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _as_text_lines(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _clean_line(value: Any, field: str, max_length: int) -> str:
    text = str(value).strip()
    if _CONTROL_RE.search(text):
        raise ValueError(f"{field} must be a single line without control characters")
    if len(text) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return text


def _clean_color(value: Any, field: str) -> str:
    text = str(value).strip().lower()
    if not _COLOR_RE.fullmatch(text):
        raise ValueError(f"{field} must be a #RRGGBB color")
    return text


def _format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _json_attr(value: Any) -> str:
    """Return a JSON value safe to place in a single-quoted HTML attribute."""

    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return html.escape(raw, quote=False).replace("'", "&#39;")


def _project_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "motion-graphics-template"


def _format_data_value(value: float, decimals: int, unit: str) -> str:
    return f"{value:,.{decimals}f}{unit}"


@dataclass(frozen=True)
class DataPoint:
    """One validated bar in the Data template."""

    label: str
    value: float

    def __post_init__(self) -> None:
        label = _clean_line(self.label, "data point label", 12)
        if not label:
            raise ValueError("data point label must not be empty")
        if isinstance(self.value, bool):
            raise ValueError("data point value must be a finite non-negative number")
        try:
            value = float(self.value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "data point value must be a finite non-negative number"
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError("data point value must be a finite non-negative number")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "value", value)


def _as_data_points(
    value: Sequence[DataPoint | Mapping[str, Any] | Sequence[Any]] | None,
) -> tuple[DataPoint, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise ValueError("data_points must be a sequence of labelled values")

    points: list[DataPoint] = []
    for item in value:
        if isinstance(item, DataPoint):
            points.append(item)
        elif isinstance(item, Mapping):
            points.append(DataPoint(label=item.get("label", ""), value=item.get("value")))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            if len(item) != 2:
                raise ValueError("each data point sequence must be (label, value)")
            points.append(DataPoint(label=item[0], value=item[1]))
        else:
            raise ValueError("each data point must be a DataPoint, mapping, or pair")
    return tuple(points)


def _scene_dialogue_entries(scene: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Normalize parser dialogue entries to ``(speaker, line)`` pairs.

    The committed parser emits ``{"speaker": ..., "line": ...}``.  The
    ``character`` / ``text`` aliases are accepted for older hand-written
    fixtures, but new code should use the parser's actual schema.
    """

    raw_dialogue = scene.get("dialogue")
    if not isinstance(raw_dialogue, Sequence) or isinstance(raw_dialogue, (str, bytes)):
        return []

    entries: list[tuple[str, str]] = []
    for entry in raw_dialogue:
        if not isinstance(entry, Mapping):
            continue
        line = str(entry.get("line", entry.get("text", ""))).strip()
        if not line:
            continue
        speaker = str(entry.get("speaker", entry.get("character", ""))).strip()
        entries.append((speaker, line))
    return entries


def _wrap_quote_lines(
    text: str, *, max_chars: int = 30, max_lines: int = 3
) -> tuple[str, ...]:
    words = str(text).split()
    if not words:
        return ()

    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            raise ValueError("a quote word is too long for the Quote template")
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError("dialogue line does not fit in the Quote template")
    return tuple(lines)


@dataclass(frozen=True)
class TitleBuildRequest:
    """Validated inputs for the reusable Title template.

    The default copy deliberately differs from the earlier Dollar film.  It
    exists only so the template can be rendered and inspected without first
    requiring a job payload.
    """

    kicker: str = "SCRIPT TO MOTION · TEMPLATE 01"
    title_lines: tuple[str, ...] | Sequence[str] | str = ("WORDS", "BECOME", "MOTION")
    accent_line: int | None = None
    sublines: tuple[str, ...] | Sequence[str] | str = (
        "Typed words. Pure typography.",
        "Rendered locally with HyperFrames.",
    )
    glyph: str = "M"
    coin_label: str = "MOTION"
    duration_sec: float = 5.0
    ground_color: str = "#0a0a0f"
    ink_color: str = "#ffffff"
    accent_color: str = "#d4af37"
    secondary_color: str = "#4a90d9"
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        title_lines = tuple(
            _clean_line(line, "title line", 18)
            for line in _as_text_lines(self.title_lines)
        )
        sublines = tuple(
            _clean_line(line, "subline", 48)
            for line in _as_text_lines(self.sublines)
        )

        if not 1 <= len(title_lines) <= 3:
            raise ValueError("title_lines must contain 1 to 3 non-empty lines")
        if len(sublines) > 2:
            raise ValueError("sublines must contain at most 2 lines")
        accent_line = (
            len(title_lines) if self.accent_line is None else self.accent_line
        )
        if isinstance(accent_line, bool) or not isinstance(accent_line, int):
            raise ValueError("accent_line must be an integer")
        if not 1 <= accent_line <= len(title_lines):
            raise ValueError("accent_line must point to an existing title line")
        object.__setattr__(self, "accent_line", accent_line)
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("Title template v1 supports 1920x1080 only")

        duration = float(self.duration_sec)
        if not math.isfinite(duration) or not 3.0 <= duration <= 8.0:
            raise ValueError("duration_sec must be between 3 and 8 seconds")

        object.__setattr__(
            self, "kicker", _clean_line(self.kicker, "kicker", 60)
        )
        object.__setattr__(self, "title_lines", title_lines)
        object.__setattr__(self, "sublines", sublines)
        object.__setattr__(self, "glyph", _clean_line(self.glyph, "glyph", 2))
        object.__setattr__(
            self, "coin_label", _clean_line(self.coin_label, "coin_label", 12)
        )
        object.__setattr__(self, "duration_sec", duration)
        object.__setattr__(
            self, "ground_color", _clean_color(self.ground_color, "ground_color")
        )
        object.__setattr__(self, "ink_color", _clean_color(self.ink_color, "ink_color"))
        object.__setattr__(
            self, "accent_color", _clean_color(self.accent_color, "accent_color")
        )
        object.__setattr__(
            self,
            "secondary_color",
            _clean_color(self.secondary_color, "secondary_color"),
        )

        if not self.kicker:
            raise ValueError("kicker must not be empty")
        if not self.glyph:
            raise ValueError("glyph must not be empty")
        if not self.coin_label:
            raise ValueError("coin_label must not be empty")

    @property
    def title_font_sizes(self) -> tuple[int, int, int]:
        """Conservative per-line font sizes for the 1050 px title column."""

        if len(self.title_lines) == 1:
            caps = (196,)
        elif len(self.title_lines) == 2:
            caps = (150, 186)
        else:
            caps = (108, 196, 164)

        sizes: list[int] = []
        for index in range(3):
            if index >= len(self.title_lines):
                sizes.append(64)
                continue
            length = max(1, len(self.title_lines[index]))
            fitted = math.floor(1040 / (0.68 * length))
            sizes.append(max(64, min(caps[index], fitted)))
        return tuple(sizes)  # type: ignore[return-value]

    def variables(self) -> dict[str, Any]:
        """Return the complete HyperFrames variable payload."""

        lines = list(self.title_lines) + ["", "", ""]
        sublines = list(self.sublines) + ["", ""]
        sizes = self.title_font_sizes
        return {
            "kicker": self.kicker,
            "title_line_1": lines[0],
            "title_line_2": lines[1],
            "title_line_3": lines[2],
            "accent_line": self.accent_line,
            "title_line_1_size": sizes[0],
            "title_line_2_size": sizes[1],
            "title_line_3_size": sizes[2],
            "subline_1": sublines[0],
            "subline_2": sublines[1],
            "glyph": self.glyph,
            "coin_label": self.coin_label,
            "ground_color": self.ground_color,
            "ink_color": self.ink_color,
            "accent_color": self.accent_color,
            "secondary_color": self.secondary_color,
        }

    def variable_schema(self) -> list[dict[str, Any]]:
        """Return the HyperFrames variable declarations for this build."""

        values = self.variables()

        def string_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "string",
                "label": label,
                "default": values[var_id],
            }

        def number_var(var_id: str, label: str, minimum: int, maximum: int) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "number",
                "label": label,
                "default": values[var_id],
                "min": minimum,
                "max": maximum,
                "step": 1,
            }

        def color_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "color",
                "label": label,
                "default": values[var_id],
            }

        return [
            string_var("kicker", "Kicker"),
            string_var("title_line_1", "Title line 1"),
            string_var("title_line_2", "Title line 2"),
            string_var("title_line_3", "Title line 3"),
            number_var("accent_line", "Accent line", 1, 3),
            number_var("title_line_1_size", "Title line 1 size", 64, 220),
            number_var("title_line_2_size", "Title line 2 size", 64, 220),
            number_var("title_line_3_size", "Title line 3 size", 64, 220),
            string_var("subline_1", "Subline 1"),
            string_var("subline_2", "Subline 2"),
            string_var("glyph", "3D coin glyph"),
            string_var("coin_label", "3D coin label"),
            color_var("ground_color", "Ground color"),
            color_var("ink_color", "Ink color"),
            color_var("accent_color", "Accent color"),
            color_var("secondary_color", "Secondary color"),
        ]


@dataclass(frozen=True)
class DataBuildRequest:
    """Validated inputs for the reusable Data-viz template.

    The default payload is explicitly illustrative.  It demonstrates the
    counter, 3D bars, comparison lines, and mandatory source slot without
    presenting an unmeasured quantity as a real-world fact.
    """

    kicker: str = "LOCAL PIPELINE · TEMPLATE 02"
    headline_lines: tuple[str, ...] | Sequence[str] | str = ("WHERE THE", "TIME GOES")
    data_points: (
        tuple[DataPoint | Mapping[str, Any] | Sequence[Any], ...]
        | Sequence[DataPoint | Mapping[str, Any] | Sequence[Any]]
    ) = (
        ("CAPTURE", 62),
        ("ENCODE", 24),
        ("SETUP", 14),
    )
    highlight_point: int | None = None
    unit: str = "%"
    value_decimals: int = 0
    hero_caption: str = "of this illustrative workload is capture"
    comparison_line: str = "Encoding follows at 24%."
    closing_line: str = "Setup stays small after warm-up."
    source_line: str = "Illustrative sample data — replace with your measured job data"
    duration_sec: float = 8.0
    ground_color: str = "#0a0a0f"
    ink_color: str = "#ffffff"
    accent_color: str = "#d4af37"
    secondary_color: str = "#4a90d9"
    muted_color: str = "#8b98a8"
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        headline_lines = tuple(
            _clean_line(line, "headline line", 18)
            for line in _as_text_lines(self.headline_lines)
        )
        data_points = _as_data_points(self.data_points)

        if not 1 <= len(headline_lines) <= 2:
            raise ValueError("headline_lines must contain 1 or 2 non-empty lines")
        if not 2 <= len(data_points) <= 4:
            raise ValueError("data_points must contain 2 to 4 points")
        labels = [point.label.casefold() for point in data_points]
        if len(set(labels)) != len(labels):
            raise ValueError("data point labels must be unique")
        if max(point.value for point in data_points) <= 0:
            raise ValueError("at least one data point value must be greater than zero")

        if self.highlight_point is None:
            highlight_point = max(
                range(len(data_points)), key=lambda index: data_points[index].value
            ) + 1
        else:
            highlight_point = self.highlight_point
        if isinstance(highlight_point, bool) or not isinstance(highlight_point, int):
            raise ValueError("highlight_point must be an integer")
        if not 1 <= highlight_point <= len(data_points):
            raise ValueError("highlight_point must point to an existing data point")

        if isinstance(self.value_decimals, bool) or not isinstance(
            self.value_decimals, int
        ):
            raise ValueError("value_decimals must be an integer")
        if not 0 <= self.value_decimals <= 3:
            raise ValueError("value_decimals must be between 0 and 3")
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("Data template v1 supports 1920x1080 only")

        duration = float(self.duration_sec)
        if not math.isfinite(duration) or not 6.0 <= duration <= 12.0:
            raise ValueError("duration_sec must be between 6 and 12 seconds")

        object.__setattr__(self, "kicker", _clean_line(self.kicker, "kicker", 60))
        object.__setattr__(self, "headline_lines", headline_lines)
        object.__setattr__(self, "data_points", data_points)
        object.__setattr__(self, "highlight_point", highlight_point)
        object.__setattr__(self, "unit", _clean_line(self.unit, "unit", 5))
        object.__setattr__(
            self, "hero_caption", _clean_line(self.hero_caption, "hero_caption", 64)
        )
        object.__setattr__(
            self,
            "comparison_line",
            _clean_line(self.comparison_line, "comparison_line", 72),
        )
        object.__setattr__(
            self, "closing_line", _clean_line(self.closing_line, "closing_line", 80)
        )
        object.__setattr__(
            self, "source_line", _clean_line(self.source_line, "source_line", 96)
        )
        object.__setattr__(self, "duration_sec", duration)
        object.__setattr__(
            self, "ground_color", _clean_color(self.ground_color, "ground_color")
        )
        object.__setattr__(self, "ink_color", _clean_color(self.ink_color, "ink_color"))
        object.__setattr__(
            self, "accent_color", _clean_color(self.accent_color, "accent_color")
        )
        object.__setattr__(
            self,
            "secondary_color",
            _clean_color(self.secondary_color, "secondary_color"),
        )
        object.__setattr__(
            self, "muted_color", _clean_color(self.muted_color, "muted_color")
        )

        if not self.kicker:
            raise ValueError("kicker must not be empty")
        if not self.hero_caption:
            raise ValueError("hero_caption must not be empty")
        if not self.source_line:
            raise ValueError("source_line must not be empty")

    @property
    def headline_font_sizes(self) -> tuple[int, int]:
        """Conservative headline sizes for the 800 px copy column."""

        sizes: list[int] = []
        for index in range(2):
            if index >= len(self.headline_lines):
                sizes.append(56)
                continue
            length = max(1, len(self.headline_lines[index]))
            fitted = math.floor(790 / (0.68 * length))
            sizes.append(max(56, min(92, fitted)))
        return tuple(sizes)  # type: ignore[return-value]

    @property
    def highlighted_point(self) -> DataPoint:
        return self.data_points[int(self.highlight_point) - 1]

    def formatted_value(self, point: DataPoint) -> str:
        return _format_data_value(point.value, self.value_decimals, self.unit)

    def variables(self) -> dict[str, Any]:
        """Return the complete HyperFrames variable payload."""

        headlines = list(self.headline_lines) + [""]
        sizes = self.headline_font_sizes
        values: dict[str, Any] = {
            "kicker": self.kicker,
            "headline_line_1": headlines[0],
            "headline_line_2": headlines[1],
            "headline_line_1_size": sizes[0],
            "headline_line_2_size": sizes[1],
            "point_count": len(self.data_points),
            "highlight_point": int(self.highlight_point),
            "unit": self.unit,
            "value_decimals": self.value_decimals,
            "hero_caption": self.hero_caption,
            "comparison_line": self.comparison_line,
            "closing_line": self.closing_line,
            "source_line": self.source_line,
            "ground_color": self.ground_color,
            "ink_color": self.ink_color,
            "accent_color": self.accent_color,
            "secondary_color": self.secondary_color,
            "muted_color": self.muted_color,
        }
        for index in range(4):
            point = self.data_points[index] if index < len(self.data_points) else None
            values[f"point_{index + 1}_label"] = point.label if point else ""
            values[f"point_{index + 1}_value"] = point.value if point else 0
        return values

    def variable_schema(self) -> list[dict[str, Any]]:
        """Return the HyperFrames variable declarations for this build."""

        values = self.variables()
        max_value = max(point.value for point in self.data_points)
        value_max = max(100.0, max_value * 2)

        def string_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "string",
                "label": label,
                "default": values[var_id],
            }

        def number_var(
            var_id: str,
            label: str,
            minimum: float,
            maximum: float,
            step: float,
        ) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "number",
                "label": label,
                "default": values[var_id],
                "min": minimum,
                "max": maximum,
                "step": step,
            }

        def color_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "color",
                "label": label,
                "default": values[var_id],
            }

        schema: list[dict[str, Any]] = [
            string_var("kicker", "Kicker"),
            string_var("headline_line_1", "Headline line 1"),
            string_var("headline_line_2", "Headline line 2"),
            number_var("headline_line_1_size", "Headline line 1 size", 56, 120, 1),
            number_var("headline_line_2_size", "Headline line 2 size", 56, 120, 1),
            number_var("point_count", "Point count", 2, 4, 1),
        ]
        for index in range(1, 5):
            schema.append(string_var(f"point_{index}_label", f"Point {index} label"))
            schema.append(
                number_var(
                    f"point_{index}_value",
                    f"Point {index} value",
                    0,
                    value_max,
                    1 if self.value_decimals == 0 else 10**-self.value_decimals,
                )
            )
        schema.extend(
            [
                number_var("highlight_point", "Highlight point", 1, 4, 1),
                string_var("unit", "Value unit"),
                number_var("value_decimals", "Value decimals", 0, 3, 1),
                string_var("hero_caption", "Hero caption"),
                string_var("comparison_line", "Comparison line"),
                string_var("closing_line", "Closing line"),
                string_var("source_line", "Source line"),
                color_var("ground_color", "Ground color"),
                color_var("ink_color", "Ink color"),
                color_var("accent_color", "Accent color"),
                color_var("secondary_color", "Secondary color"),
                color_var("muted_color", "Muted color"),
            ]
        )
        return schema


@dataclass(frozen=True)
class ShapeBuildRequest:
    """Validated inputs for the reusable 3D shape/stage template.

    One faceted hero form sits inside two orbital rings.  Optional node
    labels ride the outer orbit, making the template suitable for abstract
    systems and objects without pretending to be a specific 3D model.
    """

    kicker: str = "3D SHAPE · TEMPLATE 03"
    headline_lines: tuple[str, ...] | Sequence[str] | str = ("ONE CORE", "MANY PARTS")
    accent_line: int | None = None
    statement_line: str = "A single form can carry a whole system."
    feature_lines: tuple[str, ...] | Sequence[str] | str = (
        "A clear center",
        "Moving parts in orbit",
        "Labels that stay readable",
    )
    shape_kind: str = "orb"
    node_labels: tuple[str, ...] | Sequence[str] | str = ("CORE", "INPUT", "OUTPUT")
    duration_sec: float = 8.0
    ground_color: str = "#0a0a0f"
    ink_color: str = "#ffffff"
    accent_color: str = "#d4af37"
    secondary_color: str = "#4a90d9"
    muted_color: str = "#8b98a8"
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        headline_lines = tuple(
            _clean_line(line, "headline line", 18)
            for line in _as_text_lines(self.headline_lines)
        )
        feature_lines = tuple(
            _clean_line(line, "feature line", 48)
            for line in _as_text_lines(self.feature_lines)
        )
        node_labels = tuple(
            _clean_line(label, "node label", 12)
            for label in _as_text_lines(self.node_labels)
        )

        if not 1 <= len(headline_lines) <= 2:
            raise ValueError("headline_lines must contain 1 or 2 non-empty lines")
        if len(feature_lines) > 3:
            raise ValueError("feature_lines must contain at most 3 lines")
        if len(node_labels) > 3:
            raise ValueError("node_labels must contain at most 3 labels")
        labels = [label.casefold() for label in node_labels]
        if len(set(labels)) != len(labels):
            raise ValueError("node labels must be unique")

        accent_line = len(headline_lines) if self.accent_line is None else self.accent_line
        if isinstance(accent_line, bool) or not isinstance(accent_line, int):
            raise ValueError("accent_line must be an integer")
        if not 1 <= accent_line <= len(headline_lines):
            raise ValueError("accent_line must point to an existing headline line")

        shape_kind = str(self.shape_kind).strip().lower()
        if shape_kind not in SHAPE_KINDS:
            raise ValueError(f"shape_kind must be one of {SHAPE_KINDS}")
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("Shape template v1 supports 1920x1080 only")

        duration = float(self.duration_sec)
        if not math.isfinite(duration) or not 6.0 <= duration <= 12.0:
            raise ValueError("duration_sec must be between 6 and 12 seconds")

        object.__setattr__(self, "kicker", _clean_line(self.kicker, "kicker", 60))
        object.__setattr__(self, "headline_lines", headline_lines)
        object.__setattr__(self, "accent_line", accent_line)
        object.__setattr__(
            self, "statement_line", _clean_line(self.statement_line, "statement_line", 80)
        )
        object.__setattr__(self, "feature_lines", feature_lines)
        object.__setattr__(self, "shape_kind", shape_kind)
        object.__setattr__(self, "node_labels", node_labels)
        object.__setattr__(self, "duration_sec", duration)
        object.__setattr__(
            self, "ground_color", _clean_color(self.ground_color, "ground_color")
        )
        object.__setattr__(self, "ink_color", _clean_color(self.ink_color, "ink_color"))
        object.__setattr__(
            self, "accent_color", _clean_color(self.accent_color, "accent_color")
        )
        object.__setattr__(
            self,
            "secondary_color",
            _clean_color(self.secondary_color, "secondary_color"),
        )
        object.__setattr__(
            self, "muted_color", _clean_color(self.muted_color, "muted_color")
        )

        if not self.kicker:
            raise ValueError("kicker must not be empty")
        if not self.statement_line:
            raise ValueError("statement_line must not be empty")

    @property
    def headline_font_sizes(self) -> tuple[int, int]:
        """Conservative headline sizes for the 800 px copy column."""

        sizes: list[int] = []
        for index in range(2):
            if index >= len(self.headline_lines):
                sizes.append(56)
                continue
            length = max(1, len(self.headline_lines[index]))
            fitted = math.floor(790 / (0.68 * length))
            sizes.append(max(56, min(92, fitted)))
        return tuple(sizes)  # type: ignore[return-value]

    def variables(self) -> dict[str, Any]:
        """Return the complete HyperFrames variable payload."""

        headlines = list(self.headline_lines) + [""]
        features = list(self.feature_lines) + ["", "", ""]
        labels = list(self.node_labels) + ["", "", ""]
        sizes = self.headline_font_sizes
        return {
            "kicker": self.kicker,
            "headline_line_1": headlines[0],
            "headline_line_2": headlines[1],
            "accent_line": int(self.accent_line),
            "headline_line_1_size": sizes[0],
            "headline_line_2_size": sizes[1],
            "statement_line": self.statement_line,
            "feature_line_1": features[0],
            "feature_line_2": features[1],
            "feature_line_3": features[2],
            "shape_kind": self.shape_kind,
            "node_count": len(self.node_labels),
            "node_label_1": labels[0],
            "node_label_2": labels[1],
            "node_label_3": labels[2],
            "ground_color": self.ground_color,
            "ink_color": self.ink_color,
            "accent_color": self.accent_color,
            "secondary_color": self.secondary_color,
            "muted_color": self.muted_color,
        }

    def variable_schema(self) -> list[dict[str, Any]]:
        """Return the HyperFrames variable declarations for this build."""

        values = self.variables()

        def string_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "string",
                "label": label,
                "default": values[var_id],
            }

        def number_var(var_id: str, label: str, minimum: int, maximum: int) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "number",
                "label": label,
                "default": values[var_id],
                "min": minimum,
                "max": maximum,
                "step": 1,
            }

        def color_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "color",
                "label": label,
                "default": values[var_id],
            }

        return [
            string_var("kicker", "Kicker"),
            string_var("headline_line_1", "Headline line 1"),
            string_var("headline_line_2", "Headline line 2"),
            number_var("accent_line", "Accent line", 1, 2),
            number_var("headline_line_1_size", "Headline line 1 size", 56, 120),
            number_var("headline_line_2_size", "Headline line 2 size", 56, 120),
            string_var("statement_line", "Statement line"),
            string_var("feature_line_1", "Feature line 1"),
            string_var("feature_line_2", "Feature line 2"),
            string_var("feature_line_3", "Feature line 3"),
            {
                "id": "shape_kind",
                "type": "enum",
                "label": "3D shape",
                "default": values["shape_kind"],
                "options": [
                    {"value": "orb", "label": "Orb"},
                    {"value": "cube", "label": "Cube"},
                    {"value": "pyramid", "label": "Pyramid"},
                    {"value": "ring", "label": "Ring"},
                ],
            },
            number_var("node_count", "Node count", 0, 3),
            string_var("node_label_1", "Node label 1"),
            string_var("node_label_2", "Node label 2"),
            string_var("node_label_3", "Node label 3"),
            color_var("ground_color", "Ground color"),
            color_var("ink_color", "Ink color"),
            color_var("accent_color", "Accent color"),
            color_var("secondary_color", "Secondary color"),
            color_var("muted_color", "Muted color"),
        ]


@dataclass(frozen=True)
class QuoteBuildRequest:
    """Validated inputs for the reusable Quote/Dialogue template.

    ``quote_lines`` are explicit display lines rather than an automatically
    wrapped paragraph, so line breaks and emphasis stay editorially
    controlled.  A response is optional, but its speaker and line must be
    supplied together.
    """

    kicker: str = "DIALOGUE · TEMPLATE 04"
    quote_lines: tuple[str, ...] | Sequence[str] | str = (
        "Can a script become",
        "a film without a camera?",
    )
    accent_line: int | None = None
    speaker_name: str = "Bilal"
    speaker_role: str = "THE SKEPTIC"
    response_speaker: str = "Zara"
    response_line: str = "If every word knows where to move."
    context_line: str = "ORIGINAL SAMPLE DIALOGUE · TEMPLATE 04"
    duration_sec: float = 8.0
    ground_color: str = "#0a0a0f"
    ink_color: str = "#ffffff"
    accent_color: str = "#d4af37"
    secondary_color: str = "#4a90d9"
    muted_color: str = "#8b98a8"
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        quote_lines = tuple(
            _clean_line(line, "quote line", 30)
            for line in _as_text_lines(self.quote_lines)
        )
        if not 1 <= len(quote_lines) <= 3:
            raise ValueError("quote_lines must contain 1 to 3 non-empty lines")

        accent_line = len(quote_lines) if self.accent_line is None else self.accent_line
        if isinstance(accent_line, bool) or not isinstance(accent_line, int):
            raise ValueError("accent_line must be an integer")
        if not 1 <= accent_line <= len(quote_lines):
            raise ValueError("accent_line must point to an existing quote line")

        response_speaker = _clean_line(
            self.response_speaker, "response_speaker", 28
        )
        response_line = _clean_line(self.response_line, "response_line", 64)
        if bool(response_speaker) != bool(response_line):
            raise ValueError(
                "response_speaker and response_line must be supplied together"
            )
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("Quote template v1 supports 1920x1080 only")

        duration = float(self.duration_sec)
        if not math.isfinite(duration) or not 6.0 <= duration <= 12.0:
            raise ValueError("duration_sec must be between 6 and 12 seconds")

        object.__setattr__(self, "kicker", _clean_line(self.kicker, "kicker", 60))
        object.__setattr__(self, "quote_lines", quote_lines)
        object.__setattr__(self, "accent_line", accent_line)
        object.__setattr__(
            self, "speaker_name", _clean_line(self.speaker_name, "speaker_name", 28)
        )
        object.__setattr__(
            self, "speaker_role", _clean_line(self.speaker_role, "speaker_role", 42)
        )
        object.__setattr__(self, "response_speaker", response_speaker)
        object.__setattr__(self, "response_line", response_line)
        object.__setattr__(
            self, "context_line", _clean_line(self.context_line, "context_line", 96)
        )
        object.__setattr__(self, "duration_sec", duration)
        object.__setattr__(
            self, "ground_color", _clean_color(self.ground_color, "ground_color")
        )
        object.__setattr__(self, "ink_color", _clean_color(self.ink_color, "ink_color"))
        object.__setattr__(
            self, "accent_color", _clean_color(self.accent_color, "accent_color")
        )
        object.__setattr__(
            self,
            "secondary_color",
            _clean_color(self.secondary_color, "secondary_color"),
        )
        object.__setattr__(
            self, "muted_color", _clean_color(self.muted_color, "muted_color")
        )

        if not self.kicker:
            raise ValueError("kicker must not be empty")
        if not self.speaker_name:
            raise ValueError("speaker_name must not be empty")

    @property
    def has_response(self) -> bool:
        return bool(self.response_line)

    @property
    def quote_font_sizes(self) -> tuple[int, int, int]:
        """Conservative per-line sizes for the centered 1500 px quote block."""

        cap = 112 if len(self.quote_lines) == 1 else 104 if len(self.quote_lines) == 2 else 88
        sizes: list[int] = []
        for index in range(3):
            if index >= len(self.quote_lines):
                sizes.append(56)
                continue
            length = max(1, len(self.quote_lines[index]))
            fitted = math.floor(1480 / (0.62 * length))
            sizes.append(max(56, min(cap, fitted)))
        return tuple(sizes)  # type: ignore[return-value]

    def variables(self) -> dict[str, Any]:
        """Return the complete HyperFrames variable payload."""

        lines = list(self.quote_lines) + ["", "", ""]
        sizes = self.quote_font_sizes
        return {
            "kicker": self.kicker,
            "quote_line_1": lines[0],
            "quote_line_2": lines[1],
            "quote_line_3": lines[2],
            "accent_line": int(self.accent_line),
            "quote_line_1_size": sizes[0],
            "quote_line_2_size": sizes[1],
            "quote_line_3_size": sizes[2],
            "speaker_name": self.speaker_name,
            "speaker_role": self.speaker_role,
            "has_response": self.has_response,
            "response_speaker": self.response_speaker,
            "response_line": self.response_line,
            "context_line": self.context_line,
            "ground_color": self.ground_color,
            "ink_color": self.ink_color,
            "accent_color": self.accent_color,
            "secondary_color": self.secondary_color,
            "muted_color": self.muted_color,
        }

    def variable_schema(self) -> list[dict[str, Any]]:
        """Return the HyperFrames variable declarations for this build."""

        values = self.variables()

        def string_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "string",
                "label": label,
                "default": values[var_id],
            }

        def number_var(var_id: str, label: str, minimum: int, maximum: int) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "number",
                "label": label,
                "default": values[var_id],
                "min": minimum,
                "max": maximum,
                "step": 1,
            }

        def color_var(var_id: str, label: str) -> dict[str, Any]:
            return {
                "id": var_id,
                "type": "color",
                "label": label,
                "default": values[var_id],
            }

        return [
            string_var("kicker", "Kicker"),
            string_var("quote_line_1", "Quote line 1"),
            string_var("quote_line_2", "Quote line 2"),
            string_var("quote_line_3", "Quote line 3"),
            number_var("accent_line", "Accent line", 1, 3),
            number_var("quote_line_1_size", "Quote line 1 size", 56, 130),
            number_var("quote_line_2_size", "Quote line 2 size", 56, 130),
            number_var("quote_line_3_size", "Quote line 3 size", 56, 130),
            string_var("speaker_name", "Speaker name"),
            string_var("speaker_role", "Speaker role"),
            {
                "id": "has_response",
                "type": "boolean",
                "label": "Has response",
                "default": values["has_response"],
            },
            string_var("response_speaker", "Response speaker"),
            string_var("response_line", "Response line"),
            string_var("context_line", "Context line"),
            color_var("ground_color", "Ground color"),
            color_var("ink_color", "Ink color"),
            color_var("accent_color", "Accent color"),
            color_var("secondary_color", "Secondary color"),
            color_var("muted_color", "Muted color"),
        ]


def quote_request_from_scene(
    scene: Mapping[str, Any],
    *,
    quote_lines: Sequence[str] | str | None = None,
    speaker_name: str | None = None,
    speaker_role: str = "",
    response_speaker: str | None = None,
    response_line: str | None = None,
    include_response: bool = True,
    accent_line: int | None = None,
    kicker: str | None = None,
    context_line: str | None = None,
) -> QuoteBuildRequest:
    """Create a Quote request from a parser scene's dialogue.

    The first dialogue entry becomes the primary quote and the second, when
    present, becomes the response.  Explicit ``quote_lines`` win over the
    automatic word wrap; no new dialogue is invented here.
    """

    if not isinstance(scene, Mapping):
        raise TypeError("scene must be a parser scene mapping")

    entries = _scene_dialogue_entries(scene)
    if not entries and (quote_lines is None or speaker_name is None):
        raise ValueError("scene contains no dialogue for the Quote template")

    location = _clean_line(scene.get("location", "fort"), "scene location", 24)
    time_of_day = _clean_line(scene.get("time_of_day", "day"), "scene time", 16)
    try:
        scene_duration = float(scene.get("duration_sec", 8.0))
    except (TypeError, ValueError):
        scene_duration = 8.0
    if not math.isfinite(scene_duration):
        scene_duration = 8.0
    duration = max(6.0, min(12.0, scene_duration))

    characters = scene.get("characters")
    first_character = ""
    if isinstance(characters, Sequence) and not isinstance(characters, (str, bytes)):
        first_character = str(characters[0]).strip() if characters else ""

    resolved_speaker = (
        speaker_name
        or (entries[0][0] if entries else "")
        or first_character
    )
    resolved_quote_lines = (
        _as_text_lines(quote_lines)
        if quote_lines is not None
        else _wrap_quote_lines(entries[0][1])
    )

    if include_response and response_speaker is None and response_line is None:
        if len(entries) > 1:
            response_speaker, response_line = entries[1]
        else:
            response_speaker, response_line = "", ""
    elif not include_response:
        response_speaker, response_line = "", ""

    return QuoteBuildRequest(
        kicker=kicker or f"{location.upper()} · {time_of_day.upper()}",
        quote_lines=resolved_quote_lines,
        accent_line=accent_line,
        speaker_name=resolved_speaker,
        speaker_role=speaker_role,
        response_speaker=response_speaker or "",
        response_line=response_line or "",
        context_line=(
            context_line
            if context_line is not None
            else f"{location.upper()} · {time_of_day.upper()}"
        ),
        duration_sec=duration,
    )


@dataclass(frozen=True)
class BuiltProject:
    """Paths and variables for a generated HyperFrames project."""

    output_dir: Path
    index_path: Path
    variables_path: Path
    files: tuple[str, ...]
    variables: dict[str, Any]


def title_request_from_scene(
    scene: Mapping[str, Any],
    *,
    title_lines: Sequence[str] | str,
    sublines: Sequence[str] | str | None = None,
    accent_line: int | None = None,
    kicker: str | None = None,
    glyph: str | None = None,
    coin_label: str | None = None,
) -> TitleBuildRequest:
    """Create a Title request using parser timing/setting context.

    ``app.script_parser.parse_script`` deliberately does not invent marketing
    copy, so headline lines remain an explicit caller input.  The scene does
    supply a bounded duration, the default setting kicker, and the first
    dialogue line as an optional subline.
    """

    if not isinstance(scene, Mapping):
        raise TypeError("scene must be a parser scene mapping")

    location = _clean_line(scene.get("location", "fort"), "scene location", 24)
    time_of_day = _clean_line(scene.get("time_of_day", "day"), "scene time", 16)

    try:
        scene_duration = float(scene.get("duration_sec", 5.0))
    except (TypeError, ValueError):
        scene_duration = 5.0
    if not math.isfinite(scene_duration):
        scene_duration = 5.0
    duration = max(3.0, min(8.0, scene_duration))

    resolved_title_lines = _as_text_lines(title_lines)
    if accent_line is None:
        accent_line = len(resolved_title_lines) or 1

    if glyph is None:
        first_line = resolved_title_lines[0] if resolved_title_lines else ""
        glyph = next((char.upper() for char in first_line if char.isalnum()), "S")

    if sublines is None:
        derived_subline = next(
            (
                line
                for _speaker, line in _scene_dialogue_entries(scene)
                if len(line) <= 48
            ),
            "",
        )
        sublines = (derived_subline,) if derived_subline else ()

    return TitleBuildRequest(
        kicker=kicker or f"{location.upper()} · {time_of_day.upper()}",
        title_lines=resolved_title_lines,
        accent_line=accent_line,
        sublines=sublines,
        glyph=glyph,
        coin_label=coin_label or location.upper()[:12],
        duration_sec=duration,
    )


def _render_index_html(request: TitleBuildRequest, project_title: str) -> str:
    duration = _format_seconds(request.duration_sec)
    values = request.variables()
    stage_values = {key: values[key] for key in STAGE_VARIABLE_IDS}
    text_values = {key: values[key] for key in TEXT_VARIABLE_IDS}
    schema_attr = _json_attr(request.variable_schema())
    stage_attr = _json_attr(stage_values)
    text_attr = _json_attr(text_values)
    escaped_title = html.escape(project_title, quote=True)

    return f"""<!doctype html>
<html lang="en" data-composition-variables='{schema_attr}'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{escaped_title}</title>
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      body {{ font-family: Inter, Arial, sans-serif; }}
      #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      [data-composition-id="title-stage"], [data-composition-id="title-text"] {{ position: absolute; inset: 0; }}
      [data-composition-id="title-stage"] {{ z-index: 1; }}
      [data-composition-id="title-text"] {{ z-index: 2; }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{duration}"
      data-width="1920"
      data-height="1080"
    >
      <div
        id="title-stage"
        data-composition-id="title-stage"
        data-composition-src="compositions/title-stage.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="0"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{stage_attr}'
      ></div>
      <div
        id="title-text"
        data-composition-id="title-text"
        data-composition-src="compositions/title-text.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="1"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{text_attr}'
      ></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def _render_data_index_html(request: DataBuildRequest, project_title: str) -> str:
    duration = _format_seconds(request.duration_sec)
    values = request.variables()
    stage_values = {key: values[key] for key in DATA_STAGE_VARIABLE_IDS}
    text_values = {key: values[key] for key in DATA_TEXT_VARIABLE_IDS}
    schema_attr = _json_attr(request.variable_schema())
    stage_attr = _json_attr(stage_values)
    text_attr = _json_attr(text_values)
    escaped_title = html.escape(project_title, quote=True)

    return f"""<!doctype html>
<html lang="en" data-composition-variables='{schema_attr}'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{escaped_title}</title>
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      body {{ font-family: Inter, Arial, sans-serif; }}
      #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      [data-composition-id="data-stage"], [data-composition-id="data-text"] {{ position: absolute; inset: 0; }}
      [data-composition-id="data-stage"] {{ z-index: 1; }}
      [data-composition-id="data-text"] {{ z-index: 2; }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{duration}"
      data-width="1920"
      data-height="1080"
    >
      <div
        id="data-stage"
        data-composition-id="data-stage"
        data-composition-src="compositions/data-stage.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="0"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{stage_attr}'
      ></div>
      <div
        id="data-text"
        data-composition-id="data-text"
        data-composition-src="compositions/data-text.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="1"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{text_attr}'
      ></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def _render_shape_index_html(request: ShapeBuildRequest, project_title: str) -> str:
    duration = _format_seconds(request.duration_sec)
    values = request.variables()
    stage_values = {key: values[key] for key in SHAPE_STAGE_VARIABLE_IDS}
    text_values = {key: values[key] for key in SHAPE_TEXT_VARIABLE_IDS}
    schema_attr = _json_attr(request.variable_schema())
    stage_attr = _json_attr(stage_values)
    text_attr = _json_attr(text_values)
    escaped_title = html.escape(project_title, quote=True)

    return f"""<!doctype html>
<html lang="en" data-composition-variables='{schema_attr}'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{escaped_title}</title>
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      body {{ font-family: Inter, Arial, sans-serif; }}
      #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      [data-composition-id="shape-stage"], [data-composition-id="shape-text"] {{ position: absolute; inset: 0; }}
      [data-composition-id="shape-stage"] {{ z-index: 1; }}
      [data-composition-id="shape-text"] {{ z-index: 2; }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{duration}"
      data-width="1920"
      data-height="1080"
    >
      <div
        id="shape-stage"
        data-composition-id="shape-stage"
        data-composition-src="compositions/shape-stage.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="0"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{stage_attr}'
      ></div>
      <div
        id="shape-text"
        data-composition-id="shape-text"
        data-composition-src="compositions/shape-text.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="1"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{text_attr}'
      ></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def _render_quote_index_html(request: QuoteBuildRequest, project_title: str) -> str:
    duration = _format_seconds(request.duration_sec)
    values = request.variables()
    stage_values = {key: values[key] for key in QUOTE_STAGE_VARIABLE_IDS}
    text_values = {key: values[key] for key in QUOTE_TEXT_VARIABLE_IDS}
    schema_attr = _json_attr(request.variable_schema())
    stage_attr = _json_attr(stage_values)
    text_attr = _json_attr(text_values)
    escaped_title = html.escape(project_title, quote=True)

    return f"""<!doctype html>
<html lang="en" data-composition-variables='{schema_attr}'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{escaped_title}</title>
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      body {{ font-family: Inter, Arial, sans-serif; }}
      #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: {request.ground_color}; }}
      [data-composition-id="quote-stage"], [data-composition-id="quote-text"] {{ position: absolute; inset: 0; }}
      [data-composition-id="quote-stage"] {{ z-index: 1; }}
      [data-composition-id="quote-text"] {{ z-index: 2; }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{duration}"
      data-width="1920"
      data-height="1080"
    >
      <div
        id="quote-stage"
        data-composition-id="quote-stage"
        data-composition-src="compositions/quote-stage.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="0"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{stage_attr}'
      ></div>
      <div
        id="quote-text"
        data-composition-id="quote-text"
        data-composition-src="compositions/quote-text.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="1"
        data-track-kind="graphics"
        data-width="1920"
        data-height="1080"
        data-variable-values='{text_attr}'
      ></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def _template_timing_values(request: TitleBuildRequest) -> dict[str, str]:
    duration = request.duration_sec
    return {
        "__DURATION__": _format_seconds(duration),
        "__GLYPH_DURATION__": _format_seconds(duration * 0.48),
        "__RULE_START__": _format_seconds(duration * 0.4),
        "__RULE_DURATION__": _format_seconds(duration * 0.6),
        "__SUB_START__": _format_seconds(duration * 0.44),
        "__SUB_DURATION__": _format_seconds(duration * 0.56),
    }


def _data_template_timing_values(request: DataBuildRequest) -> dict[str, str]:
    duration = request.duration_sec
    return {
        "__DURATION__": _format_seconds(duration),
        "__HERO_START__": _format_seconds(duration * 0.105),
        "__HERO_DURATION__": _format_seconds(duration * 0.895),
        "__COMPARISON_START__": _format_seconds(duration * 0.42),
        "__COMPARISON_DURATION__": _format_seconds(duration * 0.58),
        "__CLOSING_START__": _format_seconds(duration * 0.6),
        "__CLOSING_DURATION__": _format_seconds(duration * 0.4),
    }


def _shape_template_timing_values(request: ShapeBuildRequest) -> dict[str, str]:
    duration = request.duration_sec
    return {
        "__DURATION__": _format_seconds(duration),
        "__STATEMENT_START__": _format_seconds(duration * 0.2),
        "__STATEMENT_DURATION__": _format_seconds(duration * 0.8),
        "__FEATURES_START__": _format_seconds(duration * 0.42),
        "__FEATURES_DURATION__": _format_seconds(duration * 0.58),
    }


def _quote_template_timing_values(request: QuoteBuildRequest) -> dict[str, str]:
    duration = request.duration_sec
    return {
        "__DURATION__": _format_seconds(duration),
        "__RESPONSE_START__": _format_seconds(duration * 0.52),
        "__RESPONSE_DURATION__": _format_seconds(duration * 0.48),
        "__CONTEXT_START__": _format_seconds(duration * 0.24),
        "__CONTEXT_DURATION__": _format_seconds(duration * 0.76),
    }


def _render_template_with_tokens(
    template_path: Path, tokens: Mapping[str, str]
) -> str:
    rendered = template_path.read_text(encoding="utf-8")
    for token, value in tokens.items():
        rendered = rendered.replace(token, value)
    leftovers = sorted(set(re.findall(r"__[A-Z_]+__", rendered)))
    if leftovers:
        raise ValueError(
            f"unreplaced template tokens in {template_path.name}: {leftovers}"
        )
    return rendered


def _render_template(template_path: Path, request: TitleBuildRequest) -> str:
    return _render_template_with_tokens(
        template_path, _template_timing_values(request)
    )


def _prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise FileExistsError(f"output path exists and is not a directory: {output_dir}")
        entries = list(output_dir.iterdir())
        if entries:
            if not overwrite:
                raise FileExistsError(
                    f"output directory is not empty (pass overwrite=True): {output_dir}"
                )
            manifest = output_dir / MANIFEST_NAME
            if not manifest.is_file():
                raise FileExistsError(
                    "refusing to overwrite a directory without a motion-graphics build manifest"
                )
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise FileExistsError(
                    "refusing to overwrite a directory with an unreadable build manifest"
                ) from exc
            if payload.get("builder") != "app.motion_graphics.builder":
                raise FileExistsError(
                    "refusing to overwrite a directory from a different builder"
                )
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _build_project_from_parts(
    *,
    output_dir: str | Path,
    library_dir: str | Path | None,
    overwrite: bool,
    project_title: str,
    index_html: str,
    rendered_files: Sequence[tuple[str, str]],
    variables: Mapping[str, Any],
    template_name: str,
    request_payload: Mapping[str, Any],
    variable_groups: Mapping[str, Sequence[str]],
) -> BuiltProject:
    """Write a rendered two-scene template as a self-contained project."""

    output_path = Path(output_dir).expanduser().resolve()
    libs_path = (
        Path(library_dir).expanduser().resolve() if library_dir else DEFAULT_LIBRARY_DIR
    )
    missing_libraries = [
        str(libs_path / filename)
        for filename in ("gsap.min.js", "three.min.js")
        if not (libs_path / filename).is_file()
    ]
    if missing_libraries:
        raise FileNotFoundError(
            "missing local JavaScript libraries: " + ", ".join(missing_libraries)
        )

    _prepare_output_dir(output_path, overwrite)
    (output_path / "compositions").mkdir(parents=True)
    (output_path / "assets" / "lib").mkdir(parents=True)

    project_slug = _project_slug(output_path.name)
    files: list[str] = []

    def write_text(relative: str, content: str) -> None:
        path = output_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files.append(relative)

    def write_json(relative: str, payload: Any) -> None:
        write_text(relative, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    write_text("index.html", index_html)
    for relative, content in rendered_files:
        write_text(relative, content)
    write_json("variables.json", dict(variables))
    write_json(
        "package.json",
        {
            "name": project_slug,
            "private": True,
            "type": "module",
            "scripts": {
                "dev": f"npx -y hyperframes@{HYPERFRAMES_VERSION} preview",
                "check": f"npx -y hyperframes@{HYPERFRAMES_VERSION} check",
                "render": f"npx -y hyperframes@{HYPERFRAMES_VERSION} render",
            },
            "dependencies": {
                "gsap": GSAP_VERSION,
                "hyperframes": HYPERFRAMES_VERSION,
                "three": THREE_VERSION,
            },
        },
    )
    write_json(
        "hyperframes.json",
        {
            "paths": {
                "components": "compositions",
                "assets": "assets",
            },
            "media": {
                "autoProxy": False,
            },
        },
    )
    write_json(
        "meta.json",
        {
            "id": project_slug,
            "name": project_title,
            "createdBy": "app.motion_graphics.builder",
        },
    )

    for filename in ("gsap.min.js", "three.min.js"):
        relative = f"assets/lib/{filename}"
        shutil.copyfile(libs_path / filename, output_path / relative)
        files.append(relative)

    write_json(
        MANIFEST_NAME,
        {
            "builder": "app.motion_graphics.builder",
            "builder_version": 1,
            "template": template_name,
            "template_version": 1,
            "hyperframes": HYPERFRAMES_VERSION,
            "request": dict(request_payload),
            "variable_groups": {
                name: list(ids) for name, ids in variable_groups.items()
            },
            "files": sorted(files + [MANIFEST_NAME]),
        },
    )

    return BuiltProject(
        output_dir=output_path,
        index_path=output_path / "index.html",
        variables_path=output_path / "variables.json",
        files=tuple(sorted(files)),
        variables=dict(variables),
    )


def build_title_project(
    request: TitleBuildRequest | Mapping[str, Any] | None,
    output_dir: str | Path,
    *,
    library_dir: str | Path | None = None,
    overwrite: bool = False,
) -> BuiltProject:
    """Generate a self-contained HyperFrames Title project.

    ``request`` may be a :class:`TitleBuildRequest` or a mapping with the same
    fields.  Existing non-empty output directories are not touched unless
    ``overwrite=True`` and they carry this builder's manifest.
    """

    if request is None:
        build_request = TitleBuildRequest()
    elif isinstance(request, TitleBuildRequest):
        build_request = request
    elif isinstance(request, Mapping):
        build_request = TitleBuildRequest(**dict(request))
    else:
        raise TypeError("request must be TitleBuildRequest, a mapping, or None")

    output_path = Path(output_dir).expanduser().resolve()
    libs_path = Path(library_dir).expanduser().resolve() if library_dir else DEFAULT_LIBRARY_DIR

    stage_template = TITLE_TEMPLATE_DIR / "compositions" / "title-stage.html.tmpl"
    text_template = TITLE_TEMPLATE_DIR / "compositions" / "title-text.html.tmpl"
    required = (
        stage_template,
        text_template,
        libs_path / "gsap.min.js",
        libs_path / "three.min.js",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing Title template assets: " + ", ".join(missing))

    _prepare_output_dir(output_path, overwrite)
    (output_path / "compositions").mkdir(parents=True)
    (output_path / "assets" / "lib").mkdir(parents=True)

    project_slug = _project_slug(output_path.name)
    project_title = " ".join(build_request.title_lines)
    variables = build_request.variables()
    files: list[str] = []

    def write_text(relative: str, content: str) -> None:
        path = output_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files.append(relative)

    def write_json(relative: str, payload: Any) -> None:
        write_text(relative, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    write_text("index.html", _render_index_html(build_request, project_title))
    write_text(
        "compositions/title-stage.html",
        _render_template(stage_template, build_request),
    )
    write_text(
        "compositions/title-text.html",
        _render_template(text_template, build_request),
    )
    write_json("variables.json", variables)

    write_json(
        "package.json",
        {
            "name": project_slug,
            "private": True,
            "type": "module",
            "scripts": {
                "dev": f"npx -y hyperframes@{HYPERFRAMES_VERSION} preview",
                "check": f"npx -y hyperframes@{HYPERFRAMES_VERSION} check",
                "render": f"npx -y hyperframes@{HYPERFRAMES_VERSION} render",
            },
            "dependencies": {
                "gsap": GSAP_VERSION,
                "hyperframes": HYPERFRAMES_VERSION,
                "three": THREE_VERSION,
            },
        },
    )
    write_json(
        "hyperframes.json",
        {
            "paths": {
                "components": "compositions",
                "assets": "assets",
            },
            "media": {
                "autoProxy": False,
            },
        },
    )
    write_json(
        "meta.json",
        {
            "id": project_slug,
            "name": project_title,
            "createdBy": "app.motion_graphics.builder",
        },
    )

    for filename in ("gsap.min.js", "three.min.js"):
        relative = f"assets/lib/{filename}"
        shutil.copyfile(libs_path / filename, output_path / relative)
        files.append(relative)

    write_json(
        MANIFEST_NAME,
        {
            "builder": "app.motion_graphics.builder",
            "builder_version": 1,
            "template": "title",
            "template_version": 1,
            "hyperframes": HYPERFRAMES_VERSION,
            "request": asdict(build_request),
            "stage_variable_ids": list(STAGE_VARIABLE_IDS),
            "text_variable_ids": list(TEXT_VARIABLE_IDS),
            "files": sorted(files + [MANIFEST_NAME]),
        },
    )

    return BuiltProject(
        output_dir=output_path,
        index_path=output_path / "index.html",
        variables_path=output_path / "variables.json",
        files=tuple(sorted(files)),
        variables=variables,
    )


def build_data_project(
    request: DataBuildRequest | Mapping[str, Any] | None,
    output_dir: str | Path,
    *,
    library_dir: str | Path | None = None,
    overwrite: bool = False,
) -> BuiltProject:
    """Generate a self-contained HyperFrames Data-viz project."""

    if request is None:
        build_request = DataBuildRequest()
    elif isinstance(request, DataBuildRequest):
        build_request = request
    elif isinstance(request, Mapping):
        build_request = DataBuildRequest(**dict(request))
    else:
        raise TypeError("request must be DataBuildRequest, a mapping, or None")

    stage_template = DATA_TEMPLATE_DIR / "compositions" / "data-stage.html.tmpl"
    text_template = DATA_TEMPLATE_DIR / "compositions" / "data-text.html.tmpl"
    missing = [
        str(path) for path in (stage_template, text_template) if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError("missing Data template assets: " + ", ".join(missing))

    tokens = _data_template_timing_values(build_request)
    project_title = " ".join(build_request.headline_lines)
    return _build_project_from_parts(
        output_dir=output_dir,
        library_dir=library_dir,
        overwrite=overwrite,
        project_title=project_title,
        index_html=_render_data_index_html(build_request, project_title),
        rendered_files=(
            (
                "compositions/data-stage.html",
                _render_template_with_tokens(stage_template, tokens),
            ),
            (
                "compositions/data-text.html",
                _render_template_with_tokens(text_template, tokens),
            ),
        ),
        variables=build_request.variables(),
        template_name="data",
        request_payload=asdict(build_request),
        variable_groups={
            "stage": DATA_STAGE_VARIABLE_IDS,
            "text": DATA_TEXT_VARIABLE_IDS,
        },
    )


def build_shape_project(
    request: ShapeBuildRequest | Mapping[str, Any] | None,
    output_dir: str | Path,
    *,
    library_dir: str | Path | None = None,
    overwrite: bool = False,
) -> BuiltProject:
    """Generate a self-contained HyperFrames 3D shape/stage project."""

    if request is None:
        build_request = ShapeBuildRequest()
    elif isinstance(request, ShapeBuildRequest):
        build_request = request
    elif isinstance(request, Mapping):
        build_request = ShapeBuildRequest(**dict(request))
    else:
        raise TypeError("request must be ShapeBuildRequest, a mapping, or None")

    stage_template = SHAPE_TEMPLATE_DIR / "compositions" / "shape-stage.html.tmpl"
    text_template = SHAPE_TEMPLATE_DIR / "compositions" / "shape-text.html.tmpl"
    missing = [
        str(path) for path in (stage_template, text_template) if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError("missing Shape template assets: " + ", ".join(missing))

    tokens = _shape_template_timing_values(build_request)
    project_title = " ".join(build_request.headline_lines)
    return _build_project_from_parts(
        output_dir=output_dir,
        library_dir=library_dir,
        overwrite=overwrite,
        project_title=project_title,
        index_html=_render_shape_index_html(build_request, project_title),
        rendered_files=(
            (
                "compositions/shape-stage.html",
                _render_template_with_tokens(stage_template, tokens),
            ),
            (
                "compositions/shape-text.html",
                _render_template_with_tokens(text_template, tokens),
            ),
        ),
        variables=build_request.variables(),
        template_name="shape",
        request_payload=asdict(build_request),
        variable_groups={
            "stage": SHAPE_STAGE_VARIABLE_IDS,
            "text": SHAPE_TEXT_VARIABLE_IDS,
        },
    )


def build_quote_project(
    request: QuoteBuildRequest | Mapping[str, Any] | None,
    output_dir: str | Path,
    *,
    library_dir: str | Path | None = None,
    overwrite: bool = False,
) -> BuiltProject:
    """Generate a self-contained HyperFrames Quote/Dialogue project."""

    if request is None:
        build_request = QuoteBuildRequest()
    elif isinstance(request, QuoteBuildRequest):
        build_request = request
    elif isinstance(request, Mapping):
        build_request = QuoteBuildRequest(**dict(request))
    else:
        raise TypeError("request must be QuoteBuildRequest, a mapping, or None")

    stage_template = QUOTE_TEMPLATE_DIR / "compositions" / "quote-stage.html.tmpl"
    text_template = QUOTE_TEMPLATE_DIR / "compositions" / "quote-text.html.tmpl"
    missing = [
        str(path) for path in (stage_template, text_template) if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError("missing Quote template assets: " + ", ".join(missing))

    tokens = _quote_template_timing_values(build_request)
    project_title = " ".join(build_request.quote_lines)
    return _build_project_from_parts(
        output_dir=output_dir,
        library_dir=library_dir,
        overwrite=overwrite,
        project_title=project_title,
        index_html=_render_quote_index_html(build_request, project_title),
        rendered_files=(
            (
                "compositions/quote-stage.html",
                _render_template_with_tokens(stage_template, tokens),
            ),
            (
                "compositions/quote-text.html",
                _render_template_with_tokens(text_template, tokens),
            ),
        ),
        variables=build_request.variables(),
        template_name="quote",
        request_payload=asdict(build_request),
        variable_groups={
            "stage": QUOTE_STAGE_VARIABLE_IDS,
            "text": QUOTE_TEXT_VARIABLE_IDS,
        },
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local HyperFrames motion-graphics template project."
    )
    parser.add_argument("--output", required=True, help="Generated project directory")
    parser.add_argument(
        "--template",
        choices=("title", "data", "shape", "quote"),
        default="title",
        help="Template to build (default: title, for backward compatibility)",
    )
    parser.add_argument("--request-json", help="Optional template request JSON file")
    parser.add_argument("--kicker")
    parser.add_argument("--duration", type=float, dest="duration_sec")
    parser.add_argument("--library-dir")
    parser.add_argument("--overwrite", action="store_true")

    title_group = parser.add_argument_group("Title template")
    title_group.add_argument("--title-line", action="append", dest="title_lines")
    title_group.add_argument("--accent-line", type=int)
    title_group.add_argument("--subline", action="append", dest="sublines")
    title_group.add_argument("--glyph")
    title_group.add_argument("--coin-label")

    data_group = parser.add_argument_group("Data template")
    data_group.add_argument("--headline-line", action="append", dest="headline_lines")
    data_group.add_argument(
        "--data-point",
        action="append",
        dest="data_points_raw",
        metavar="LABEL=VALUE",
        help="Repeat for each bar, for example --data-point USD=57",
    )
    data_group.add_argument("--highlight-point", type=int)
    data_group.add_argument("--unit")
    data_group.add_argument("--value-decimals", type=int)
    data_group.add_argument("--hero-caption")
    data_group.add_argument("--comparison-line")
    data_group.add_argument("--closing-line")
    data_group.add_argument("--source-line")

    shape_group = parser.add_argument_group("Shape template")
    shape_group.add_argument("--shape-kind", choices=SHAPE_KINDS)
    shape_group.add_argument("--statement-line")
    shape_group.add_argument("--feature-line", action="append", dest="feature_lines")
    shape_group.add_argument("--node-label", action="append", dest="node_labels")

    quote_group = parser.add_argument_group("Quote template")
    quote_group.add_argument("--quote-line", action="append", dest="quote_lines")
    quote_group.add_argument("--speaker-name")
    quote_group.add_argument("--speaker-role")
    quote_group.add_argument("--response-speaker")
    quote_group.add_argument("--response-line")
    quote_group.add_argument("--context-line")
    return parser.parse_args(argv)


def _parse_cli_data_point(raw: str) -> tuple[str, float]:
    label, separator, value = raw.partition("=")
    if not separator:
        raise ValueError(f"data point must use LABEL=VALUE syntax: {raw!r}")
    return label.strip(), float(value)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload: dict[str, Any] = {}
    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))

    for field in ("kicker", "duration_sec"):
        value = getattr(args, field)
        if value is not None:
            payload[field] = value

    if args.template == "data":
        for field in (
            "headline_lines",
            "highlight_point",
            "unit",
            "value_decimals",
            "hero_caption",
            "comparison_line",
            "closing_line",
            "source_line",
        ):
            value = getattr(args, field)
            if value is not None:
                payload[field] = value
        if args.data_points_raw:
            payload["data_points"] = [
                _parse_cli_data_point(raw) for raw in args.data_points_raw
            ]

        result = build_data_project(
            payload,
            args.output,
            library_dir=args.library_dir,
            overwrite=args.overwrite,
        )
        print(f"Built Data project: {result.output_dir}")
    elif args.template == "shape":
        for field in (
            "headline_lines",
            "accent_line",
            "statement_line",
            "feature_lines",
            "shape_kind",
            "node_labels",
        ):
            value = getattr(args, field)
            if value is not None:
                payload[field] = value

        result = build_shape_project(
            payload,
            args.output,
            library_dir=args.library_dir,
            overwrite=args.overwrite,
        )
        print(f"Built Shape project: {result.output_dir}")
    elif args.template == "quote":
        for field in (
            "quote_lines",
            "accent_line",
            "speaker_name",
            "speaker_role",
            "response_speaker",
            "response_line",
            "context_line",
        ):
            value = getattr(args, field)
            if value is not None:
                payload[field] = value

        result = build_quote_project(
            payload,
            args.output,
            library_dir=args.library_dir,
            overwrite=args.overwrite,
        )
        print(f"Built Quote project: {result.output_dir}")
    else:
        for field in (
            "title_lines",
            "accent_line",
            "sublines",
            "glyph",
            "coin_label",
        ):
            value = getattr(args, field)
            if value is not None:
                payload[field] = value

        result = build_title_project(
            payload,
            args.output,
            library_dir=args.library_dir,
            overwrite=args.overwrite,
        )
        print(f"Built Title project: {result.output_dir}")

    print(f"Index: {result.index_path}")
    print(f"Variables: {result.variables_path}")
    print(f"Files: {len(result.files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
