"""Deterministic scene-to-template planning for local motion graphics.

The planner is deliberately rule-based and side-effect free.  It reuses the
existing script parser and validated template request objects, then returns
an ordered clip plan that a renderer can build one scene at a time.

Scene-led hybrid policy (v1), in priority order:

1. the final scene becomes **Outro** when it contains a closing cue;
2. a scene with extracted dialogue becomes **Quote**;
3. a scene with at least two numeric values becomes **Data** (labels are
   taken deterministically from explicit pairs or the nearest label/count
   noun around each number);
4. every other narrative/action scene becomes a **Title** scene-card.

No network, LLM, random choice, dialogue, or numeric value is invented.
Title/Outro copy is word-wrapped from the source sentence.  The parser does
not currently expose the raw sentence in its scene dict, so this module uses
``split_sentences`` from the same parser and aligns sentences to scenes by
index.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.motion_graphics.builder import (
    DataBuildRequest,
    OutroBuildRequest,
    quote_request_from_scene,
    title_request_from_scene,
)
from app.script_parser import parse_script, split_sentences

__all__ = [
    "AUTO_MAPPER_VERSION",
    "AUTO_POLICY",
    "AutoClipPlan",
    "AutoSequencePlan",
    "plan_auto_sequence",
]

AUTO_MAPPER_VERSION = "1.0"
AUTO_POLICY = "scene_led_hybrid_v1"
DEFAULT_MAX_AUTO_SCENES = 24

_ACTION_LABELS = {
    "walk": "Walk",
    "run": "Run",
    "light_torch": "Light torch",
    "fight": "Fight",
    "talk": "Talk",
}

_CLOSING_CUE_RE = re.compile(
    r"\b(?:the\s+end|khatam|khatm|aakhir|akhir|tamam|samapt|"
    r"conclusion|concluded|concludes|ended|ends|fin)\b",
    re.IGNORECASE,
)

_QUOTED_SPAN_RE = re.compile(
    r"'[^'\n]+'|\"[^\"\n]+\"|‘[^’]+’|“[^”]+”"
)

_EXPLICIT_NUMERIC_PAIR_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,30}?)\s*[:=]\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|percentage|"
    r"seconds?|secs?|minutes?|mins?|hours?|hrs?|mb|gb|kg|km|m|"
    r"usd|rs|\$)?(?=$|[\s,;:.)\]])",
    re.IGNORECASE,
)
_PERCENT_NUMERIC_PAIR_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,30}?)\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_KNOWN_UNIT_WORDS = {
    "%",
    "percent",
    "percentage",
    "second",
    "seconds",
    "sec",
    "secs",
    "minute",
    "minutes",
    "min",
    "mins",
    "hour",
    "hours",
    "hr",
    "hrs",
    "mb",
    "gb",
    "kg",
    "km",
    "m",
    "rs",
    "usd",
    "$",
}

_LABEL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "aur",
    "be",
    "been",
    "by",
    "for",
    "from",
    "had",
    "hai",
    "hain",
    "has",
    "have",
    "here",
    "in",
    "into",
    "is",
    "ka",
    "ke",
    "ki",
    "ko",
    "mein",
    "of",
    "par",
    "per",
    "se",
    "tha",
    "the",
    "then",
    "there",
    "thi",
    "to",
    "was",
    "were",
    "when",
    "where",
    "while",
    "with",
}


@dataclass(frozen=True)
class _NumericPoint:
    label: str
    value: float
    unit: str
    decimals: int


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(frozen=True)
class AutoClipPlan:
    """One validated template clip in an automatic sequence."""

    clip_id: str
    scene_id: int
    template: str
    sentence_text: str
    reason: str
    reason_codes: tuple[str, ...]
    request: dict[str, Any]
    scene_duration_sec: float
    duration_sec: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class AutoSequencePlan:
    """Complete deterministic plan for one script."""

    planner_version: str
    policy: str
    script_text: str
    scenes: tuple[dict[str, Any], ...]
    clips: tuple[AutoClipPlan, ...]

    @property
    def total_duration_sec(self) -> float:
        return round(sum(clip.duration_sec for clip in self.clips), 3)

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        for clip in self.clips:
            warnings.extend(f"{clip.clip_id}: {warning}" for warning in clip.warnings)
        return tuple(warnings)

    def to_dict(self) -> dict[str, Any]:
        payload = _json_safe(asdict(self))
        payload["scene_count"] = len(self.scenes)
        payload["clip_count"] = len(self.clips)
        payload["total_duration_sec"] = self.total_duration_sec
        payload["warnings"] = list(self.warnings)
        return payload


def _clean_text(text: Any) -> str:
    return " ".join(str(text or "").split()).strip()


def _strip_terminal_punctuation(text: str) -> str:
    return _clean_text(text).rstrip(" .!?:;").strip()


def _clamp(value: float, lower: float, upper: float) -> float:
    if not math.isfinite(value):
        return lower
    return max(lower, min(upper, float(value)))


def _scene_float(scene: Mapping[str, Any], key: str, default: float) -> float:
    try:
        value = float(scene.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _wrap_words(text: str, max_chars: int) -> list[str]:
    words: list[str] = []
    for word in _clean_text(text).split():
        if len(word) <= max_chars:
            words.append(word)
            continue
        # A deterministic hard split is preferable to rejecting an entire
        # script because one token is longer than a display line.
        words.extend(
            word[index : index + max_chars]
            for index in range(0, len(word), max_chars)
        )

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _fit_lines(
    text: str, *, max_chars: int, max_lines: int
) -> tuple[tuple[str, ...], bool]:
    lines = _wrap_words(text, max_chars)
    if len(lines) <= max_lines:
        return tuple(lines), False
    selected = lines[:max_lines]
    last = selected[-1][: max(1, max_chars - 1)].rstrip()
    selected[-1] = f"{last}…"
    return tuple(selected), True


def _scene_context(scene: Mapping[str, Any]) -> str:
    scene_id = int(scene.get("scene_id") or 0)
    location = _clean_text(scene.get("location") or "fort").upper()
    time_of_day = _clean_text(scene.get("time_of_day") or "day").upper()
    return f"SCENE {scene_id:02d} · {location} · {time_of_day}"


def _string_list(scene: Mapping[str, Any], key: str) -> list[str]:
    raw = scene.get(key)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _facts_subline(scene: Mapping[str, Any]) -> str:
    characters = _string_list(scene, "characters")
    actions = [
        _ACTION_LABELS.get(action, action.replace("_", " ").title())
        for action in _string_list(scene, "actions")
    ]
    facts: list[str] = []
    if characters:
        facts.append(" + ".join(characters))
    if actions:
        facts.append(" · ".join(actions))
    line = " · ".join(facts)
    if len(line) <= 48:
        return line
    wrapped = _wrap_words(line, 48)
    return wrapped[0] if wrapped else ""


def _title_request(
    scene: Mapping[str, Any], sentence_text: str
) -> tuple[Any, tuple[str, ...]]:
    warnings: list[str] = []
    clean = _strip_terminal_punctuation(sentence_text)
    wrapped = _wrap_words(clean, 18)

    if not wrapped:
        characters = _string_list(scene, "characters")
        fallback = " ".join(characters) or _clean_text(scene.get("location") or "Scene")
        wrapped = _wrap_words(fallback, 18) or ["SCENE"]

    title_lines = tuple(wrapped[:3])
    if len(wrapped) > 3:
        remainder = " ".join(wrapped[3:])
        sub_wrapped = _wrap_words(remainder, 48)
        sublines_list = sub_wrapped[:2]
        if len(sub_wrapped) > 2:
            sublines_list[-1] = f"{sublines_list[-1][:47].rstrip()}…"
            warnings.append(
                "Narrative sentence exceeded the Title template copy capacity; "
                "the final subline was truncated deterministically."
            )
        sublines = tuple(sublines_list)
    else:
        facts = _facts_subline(scene)
        sublines = (facts,) if facts else ()

    request = title_request_from_scene(
        scene,
        title_lines=title_lines,
        sublines=sublines,
        kicker=_scene_context(scene),
    )
    return request, tuple(warnings)


def _quote_request(
    scene: Mapping[str, Any],
) -> tuple[Any, tuple[str, ...]]:
    dialogue = scene.get("dialogue")
    dialogue_count = (
        len(dialogue)
        if isinstance(dialogue, Sequence) and not isinstance(dialogue, (str, bytes))
        else 0
    )
    warnings: list[str] = []
    if dialogue_count > 2:
        warnings.append(
            "Quote template shows the first dialogue line and first response; "
            f"{dialogue_count - 2} additional dialogue line(s) were not used."
        )
    request = quote_request_from_scene(
        scene,
        kicker=_scene_context(scene),
        context_line=_scene_context(scene),
    )
    return request, tuple(warnings)


def _normalize_unit(raw_unit: str | None) -> str:
    unit = _clean_text(raw_unit or "").lower().strip(".")
    return {
        "%": "%",
        "percent": "%",
        "percentage": "%",
        "second": "s",
        "seconds": "s",
        "sec": "s",
        "secs": "s",
        "minute": "min",
        "minutes": "min",
        "min": "min",
        "mins": "min",
        "hour": "hr",
        "hours": "hr",
        "hr": "hr",
        "hrs": "hr",
        "usd": "$",
    }.get(unit, unit[:5])


def _clean_data_label(raw_label: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", raw_label or "")
    while words and words[0].lower() in _LABEL_STOPWORDS:
        words.pop(0)
    if not words:
        return ""

    two_words = " ".join(words[-2:]).upper()
    if len(two_words) <= 12:
        return two_words
    return words[-1].upper()[:12]


def _extract_explicit_numeric_points(
    sentence_text: str,
) -> tuple[_NumericPoint, ...]:
    narrative = _QUOTED_SPAN_RE.sub(" ", sentence_text)
    points: list[_NumericPoint] = []
    seen_labels: set[str] = set()

    for segment in re.split(r"[;,]", narrative):
        match = _EXPLICIT_NUMERIC_PAIR_RE.search(segment) or (
            _PERCENT_NUMERIC_PAIR_RE.search(segment)
        )
        if not match:
            continue
        label = _clean_data_label(match.group("label"))
        if not label or label.casefold() in seen_labels:
            continue
        raw_value = match.group("value")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        unit = "%" if match.re is _PERCENT_NUMERIC_PAIR_RE else _normalize_unit(
            match.groupdict().get("unit")
        )
        seen_labels.add(label.casefold())
        points.append(
            _NumericPoint(
                label=label,
                value=value,
                unit=unit,
                decimals=len(raw_value.partition(".")[2])
                if "." in raw_value
                else 0,
            )
        )

    if len(points) < 2:
        return ()

    non_empty_units = {point.unit for point in points if point.unit}
    if len(non_empty_units) > 1:
        return ()
    if len(points) > 4:
        points = points[:4]
    return tuple(points)


def _extract_generic_numeric_points(
    sentence_text: str,
) -> tuple[_NumericPoint, ...]:
    """Extract points from any 2+ numbers in one narrative sentence.

    This implements the approved Step C rule literally—two or more numbers
    select Data—without inventing values.  Labels are sourced, in order,
    from words immediately before a number, otherwise from the counted noun
    immediately after it.  A stable ``VALUE n`` label is used only when a
    bare number has no nearby label at all.
    """

    narrative = _QUOTED_SPAN_RE.sub(" ", sentence_text)
    matches = list(_NUMBER_RE.finditer(narrative))
    if len(matches) < 2:
        return ()

    points: list[_NumericPoint] = []
    seen_labels: set[str] = set()

    for index, match in enumerate(matches):
        previous_end = matches[index - 1].end() if index else 0
        next_start = (
            matches[index + 1].start() if index + 1 < len(matches) else len(narrative)
        )
        before = narrative[previous_end : match.start()]
        after = narrative[match.end() : next_start]

        # Isolate the clause directly attached to this number.
        before_clause = re.split(r"[;,]", before)[-1]
        before_clause = re.split(
            r"\b(?:and|aur)\b", before_clause, flags=re.IGNORECASE
        )[-1]
        before_words = re.findall(r"[A-Za-z]+", before_clause)
        while before_words and before_words[-1].lower() in _LABEL_STOPWORDS:
            before_words.pop()
        before_label = _clean_data_label(" ".join(before_words))

        after_trimmed = after.lstrip()
        if after_trimmed[:1] in {",", ";"} or re.match(
            r"(?:and|aur)\b", after_trimmed, flags=re.IGNORECASE
        ):
            # The next word belongs to the next clause/number, not to this
            # value as a counted noun or unit.
            after_clean = ""
        else:
            after_clean = after_trimmed.lstrip(" \t\r\n:=")
        unit = ""
        following_label = ""
        if after_clean.startswith("%"):
            unit = "%"
        else:
            after_word_match = re.match(r"([A-Za-z]+)", after_clean)
            if after_word_match:
                after_word = after_word_match.group(1)
                after_lower = after_word.lower()
                if after_lower in _KNOWN_UNIT_WORDS:
                    unit = _normalize_unit(after_word)
                elif after_lower not in _LABEL_STOPWORDS:
                    following_label = _clean_data_label(after_word)
                    if before_label:
                        # With a subject/label before the value, the next
                        # word is the counted noun (for example ``qadam``).
                        unit = _normalize_unit(after_word)

        label = before_label or following_label or f"VALUE {index + 1}"
        if label.casefold() in seen_labels:
            if following_label and following_label.casefold() not in seen_labels:
                label = following_label
                unit = ""
            else:
                suffix = f" {index + 1}"
                label = f"{label[: 12 - len(suffix)].rstrip()}{suffix}"
        seen_labels.add(label.casefold())

        raw_value = match.group(0)
        points.append(
            _NumericPoint(
                label=label,
                value=float(raw_value),
                unit=unit,
                decimals=len(raw_value.partition(".")[2])
                if "." in raw_value
                else 0,
            )
        )
        if len(points) >= 4:
            break

    if len(points) < 2:
        return ()

    # The Data template has one shared unit.  If counted nouns differ, keep
    # the raw values and drop the unit rather than rejecting the Data rule.
    non_empty_units = {point.unit for point in points if point.unit}
    if len(non_empty_units) > 1:
        points = [
            _NumericPoint(
                label=point.label,
                value=point.value,
                unit="",
                decimals=point.decimals,
            )
            for point in points
        ]
    return tuple(points)


def _extract_numeric_points(sentence_text: str) -> tuple[_NumericPoint, ...]:
    explicit = _extract_explicit_numeric_points(sentence_text)
    if explicit:
        return explicit
    return _extract_generic_numeric_points(sentence_text)


def _format_auto_value(point: _NumericPoint, unit: str, decimals: int) -> str:
    return f"{point.value:,.{decimals}f}{unit}"


def _data_request(
    scene: Mapping[str, Any], points: Sequence[_NumericPoint]
) -> tuple[Any, tuple[str, ...]]:
    warnings: list[str] = []
    units = {point.unit for point in points if point.unit}
    unit = next(iter(units), "")
    decimals = max((point.decimals for point in points), default=0)
    decimals = max(0, min(3, decimals))

    sorted_points = sorted(points, key=lambda point: point.value, reverse=True)
    second = sorted_points[1] if len(sorted_points) > 1 else None
    comparison = (
        f"{second.label.title()} follows at "
        f"{_format_auto_value(second, unit, decimals)}."
        if second
        else ""
    )
    headline_text = f"{_clean_text(scene.get('location') or 'Scene')} data".upper()
    headline_lines, _ = _fit_lines(headline_text, max_chars=18, max_lines=2)

    request = DataBuildRequest(
        kicker=_scene_context(scene),
        headline_lines=headline_lines or ("SCENE DATA",),
        data_points=tuple((point.label, point.value) for point in points),
        unit=unit,
        value_decimals=decimals,
        hero_caption="is the largest value in this scene",
        comparison_line=comparison,
        closing_line="Values are taken directly from the script.",
        source_line=(
            f"Source: script scene {int(scene.get('scene_id') or 0)} "
            "(auto-extracted label/value pairs)"
        ),
        duration_sec=_clamp(_scene_float(scene, "duration_sec", 8.0), 6.0, 12.0),
    )
    return request, tuple(warnings)


def _outro_request(
    scene: Mapping[str, Any],
    sentence_text: str,
    *,
    brand_label: str,
) -> tuple[Any, tuple[str, ...]]:
    warnings: list[str] = []
    clean = _strip_terminal_punctuation(sentence_text)
    closing_lines, truncated = _fit_lines(
        clean.upper(), max_chars=24, max_lines=3
    )
    if truncated:
        warnings.append(
            "Closing sentence exceeded the Outro copy capacity and was "
            "truncated deterministically."
        )
    if not closing_lines:
        closing_lines = ("THE END",)

    credits: list[str] = []
    characters = _string_list(scene, "characters")
    actions = [
        _ACTION_LABELS.get(action, action.replace("_", " ").title()).upper()
        for action in _string_list(scene, "actions")
    ]
    credit_candidates = []
    if characters:
        credit_candidates.append(" + ".join(characters).upper())
    credit_candidates.extend(actions)
    credit_candidates.append(f"SCENE {int(scene.get('scene_id') or 0):02d}")
    for candidate in credit_candidates:
        if (
            candidate
            and len(candidate) <= 30
            and sum(len(item) for item in credits) + len(candidate) <= 78
        ):
            credits.append(candidate)
        if len(credits) >= 3:
            break

    location = _clean_text(scene.get("location") or "fort").title()
    time_of_day = _clean_text(scene.get("time_of_day") or "day").title()
    brand = _clean_text(brand_label) or "SIDD STUDIO"
    glyph = next((char.upper() for char in brand if char.isalnum()), "S")
    request = OutroBuildRequest(
        kicker=f"THE END · SCENE {int(scene.get('scene_id') or 0):02d}",
        closing_lines=closing_lines,
        tagline=f"{location} · {time_of_day}",
        brand_label=brand,
        glyph=glyph,
        credit_lines=tuple(credits),
        cta_label="",
        duration_sec=_clamp(_scene_float(scene, "duration_sec", 7.0), 5.0, 10.0),
    )
    return request, tuple(warnings)


def _request_dict(request: Any) -> dict[str, Any]:
    return _json_safe(asdict(request))


def plan_auto_sequence(
    script_text: str,
    *,
    brand_label: str = "SIDD STUDIO",
    max_scenes: int = DEFAULT_MAX_AUTO_SCENES,
) -> AutoSequencePlan:
    """Build a deterministic Title/Data/Quote/Outro plan for ``script_text``.

    Every parser scene produces exactly one clip in parser order in v1.
    The parser scene duration is the clip-duration source; the actual clip
    duration is that value clamped only where the selected template has a
    narrower valid range.  Long Quote/Data requests that fail their
    template validators fall back to a Title scene-card and record the
    reason in that clip's warnings.
    """

    script = str(script_text or "")
    if not script.strip():
        raise ValueError("script_text must not be empty")
    if isinstance(max_scenes, bool) or not isinstance(max_scenes, int):
        raise ValueError("max_scenes must be an integer")
    if not 1 <= max_scenes <= 100:
        raise ValueError("max_scenes must be between 1 and 100")

    scenes = parse_script(script)
    if not scenes:
        raise ValueError("script_text did not produce any parser scenes")
    if len(scenes) > max_scenes:
        raise ValueError(
            f"script produced {len(scenes)} scenes; auto-mapper v1 allows "
            f"at most {max_scenes}"
        )

    sentences = split_sentences(script)
    clips: list[AutoClipPlan] = []

    for index, scene in enumerate(scenes):
        sentence_text = sentences[index] if index < len(sentences) else ""
        scene_id = int(scene.get("scene_id") or index + 1)
        clip_id = f"clip-{index + 1:02d}"
        is_last = index == len(scenes) - 1
        warnings: tuple[str, ...] = ()

        if is_last and _CLOSING_CUE_RE.search(sentence_text):
            request, warnings = _outro_request(
                scene, sentence_text, brand_label=brand_label
            )
            template = "outro"
            reason = "Final scene contains a closing cue."
            reason_codes = ("last_scene", "closing_cue")
            if scene.get("dialogue"):
                warnings = (
                    *warnings,
                    "Closing-cue priority selected Outro; dialogue in this "
                    "final scene was not used as a Quote.",
                )
        elif scene.get("dialogue"):
            try:
                request, warnings = _quote_request(scene)
                template = "quote"
                reason = "Scene contains extracted dialogue."
                reason_codes = ("dialogue_present",)
            except ValueError as exc:
                request, title_warnings = _title_request(scene, sentence_text)
                template = "title"
                reason = (
                    "Scene contains dialogue, but it does not fit the Quote "
                    "template; deterministic Title fallback used."
                )
                reason_codes = ("dialogue_present", "quote_fallback_title")
                warnings = (*title_warnings, f"Quote fallback: {exc}")
        else:
            numeric_points = _extract_numeric_points(sentence_text)
            if numeric_points:
                try:
                    request, warnings = _data_request(scene, numeric_points)
                    template = "data"
                    reason = "Scene contains at least two numeric values."
                    reason_codes = ("two_or_more_numbers",)
                except ValueError as exc:
                    request, title_warnings = _title_request(scene, sentence_text)
                    template = "title"
                    reason = (
                        "Numeric values were detected, but they do not satisfy "
                        "the Data template; deterministic Title fallback used."
                    )
                    reason_codes = ("two_or_more_numbers", "data_fallback_title")
                    warnings = (*title_warnings, f"Data fallback: {exc}")
            else:
                request, warnings = _title_request(scene, sentence_text)
                template = "title"
                reason = (
                    "Narrative/action scene without dialogue or at least "
                    "two numeric values."
                )
                reason_codes = ("narrative_scene",)

        clips.append(
            AutoClipPlan(
                clip_id=clip_id,
                scene_id=scene_id,
                template=template,
                sentence_text=sentence_text,
                reason=reason,
                reason_codes=tuple(reason_codes),
                request=_request_dict(request),
                scene_duration_sec=_scene_float(scene, "duration_sec", 3.0),
                duration_sec=float(request.duration_sec),
                warnings=tuple(warnings),
            )
        )

    return AutoSequencePlan(
        planner_version=AUTO_MAPPER_VERSION,
        policy=AUTO_POLICY,
        script_text=script,
        scenes=tuple(dict(scene) for scene in scenes),
        clips=tuple(clips),
    )
