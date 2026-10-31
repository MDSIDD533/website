from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from app.script_parser import parse_script

PLANNER_VERSION = "blender3d-plan-v1"
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 24
QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    # Native 1920x1080 is kept at 100% scale.  The speed win comes from
    # adaptive sampling, a low sample ceiling, OIDN denoise and very small
    # light-path budgets instead of silently shrinking the render.
    "draft": {
        "samples": 2,
        "noise_threshold": 0.2,
        "denoiser": "OPENIMAGEDENOISE",
        "denoise_prefilter": "FAST",
        "denoise_quality": "FAST",
        "max_bounces": 1,
        "diffuse_bounces": 0,
        "glossy_bounces": 0,
        "encode_crf": 20,
    },
    "standard": {
        "samples": 3,
        "noise_threshold": 0.12,
        "denoiser": "OPENIMAGEDENOISE",
        "denoise_prefilter": "FAST",
        "denoise_quality": "FAST",
        "max_bounces": 1,
        "diffuse_bounces": 0,
        "glossy_bounces": 0,
        "encode_crf": 18,
    },
    "high": {
        "samples": 6,
        "noise_threshold": 0.06,
        "denoiser": "OPENIMAGEDENOISE",
        "denoise_prefilter": "ACCURATE",
        "denoise_quality": "HIGH",
        "max_bounces": 2,
        "diffuse_bounces": 1,
        "glossy_bounces": 1,
        "encode_crf": 16,
    },
}


@dataclass(frozen=True)
class ThemeInfo:
    id: str
    label: str
    environment: str
    description: str
    default_captions: tuple[str, ...]
    palette: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "environment": self.environment,
            "description": self.description,
            "default_captions": list(self.default_captions),
            "palette": dict(self.palette),
        }


THEMES: dict[str, ThemeInfo] = {
    "ww2_battlefield": ThemeInfo(
        id="ww2_battlefield",
        label="WWII Battlefield",
        environment="battlefield",
        description="Large procedural battlefield with tanks, soldiers, ships, aircraft and coastal defenses.",
        default_captions=("THE GLOBAL CONFLICT", "1939 · INVASION", "WAR DECLARED", "LAND · SEA · AIR"),
        palette={"sky": "#BAC9D4", "ground": "#5B6250", "accent": "#B8472F", "water": "#3E6F86"},
    ),
    "finance_city": ThemeInfo(
        id="finance_city",
        label="Finance City",
        environment="finance_city",
        description="Procedural towers, rolling coins, bank columns and animated growth bars.",
        default_captions=("FINANCE CITY", "MONEY IN MOTION", "GROWTH RISING"),
        palette={"sky": "#D8E7F2", "ground": "#48515A", "accent": "#E5B84C", "water": "#6FA8C9"},
    ),
    "space_voyage": ThemeInfo(
        id="space_voyage",
        label="Space Voyage",
        environment="space",
        description="Moon surface with a launching rocket, orbiting satellite, astronaut and Earth backdrop.",
        default_captions=("SPACE VOYAGE", "LAUNCH SEQUENCE", "INTO ORBIT"),
        palette={"sky": "#050914", "ground": "#8F97A3", "accent": "#F4F7FB", "water": "#2C6FB8"},
    ),
    "ocean_voyage": ThemeInfo(
        id="ocean_voyage",
        label="Ocean Voyage",
        environment="ocean",
        description="Animated ship, island, lighthouse and waving palm trees on a procedural sea.",
        default_captions=("OCEAN VOYAGE", "SAILING ONWARD", "THE LIGHTHOUSE"),
        palette={"sky": "#BFE2F2", "ground": "#E4C98A", "accent": "#C8503C", "water": "#2F78A8"},
    ),
    "tech_lab": ThemeInfo(
        id="tech_lab",
        label="Tech Lab",
        environment="tech_lab",
        description="Server towers, robot guide, orbiting data nodes and glowing circuit floor.",
        default_captions=("TECH LAB", "DATA ONLINE", "ROBOT ASSIST"),
        palette={"sky": "#071820", "ground": "#10222B", "accent": "#35D0D8", "water": "#1A5266"},
    ),
    "nature_valley": ThemeInfo(
        id="nature_valley",
        label="Nature Valley",
        environment="jungle",
        description="Green valley with river, trees, mountains, drifting clouds and simple wildlife forms.",
        default_captions=("NATURE VALLEY", "RIVER AND FOREST", "INTO THE MOUNTAINS"),
        palette={"sky": "#CDEAF8", "ground": "#5F9B55", "accent": "#E8C65A", "water": "#4BA3C8"},
    ),
    "history_fort": ThemeInfo(
        id="history_fort",
        label="History Fort",
        environment="fort",
        description="Procedural fort walls, watch towers, banners, guards and torch-lit gate.",
        default_captions=("HISTORY FORT", "THE OLD GATE", "GUARDS ON WATCH"),
        palette={"sky": "#E8DCC7", "ground": "#8A735A", "accent": "#A85B2A", "water": "#6B93A6"},
    ),
    "abstract_shapes": ThemeInfo(
        id="abstract_shapes",
        label="Abstract Shapes",
        environment="abstract",
        description="Colorful geometric objects, rings and platforms in a continuous camera move.",
        default_captions=("SHAPES IN MOTION", "FORM AND COLOR", "THE FINAL ORBIT"),
        palette={"sky": "#11182E", "ground": "#232D47", "accent": "#F2A93B", "water": "#4A7DFF"},
    ),
}
THEME_IDS = tuple(THEMES)


def theme_infos() -> list[dict[str, Any]]:
    return [theme.to_dict() for theme in THEMES.values()]


def quality_profile(quality: str) -> dict[str, Any]:
    return dict(QUALITY_PROFILES[quality])


@dataclass(frozen=True)
class Blender3DRequest:
    theme: str = "auto"
    scene_label: str | None = None
    caption_lines: tuple[str, ...] = ()
    duration_sec: float = 18.0
    fps: int = DEFAULT_FPS
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    quality: str = "standard"
    camera_move: str = "cinematic"
    intensity: float = 1.0
    include_captions: bool = True
    seed: int = 1939

    def __post_init__(self) -> None:
        if self.theme not in {"auto", *THEME_IDS}:
            raise ValueError(f"Unsupported Blender theme: {self.theme}")
        if self.quality not in QUALITY_PROFILES:
            raise ValueError(f"Unsupported Blender quality profile: {self.quality}")
        if self.camera_move not in {"cinematic", "orbit", "tracking"}:
            raise ValueError(f"Unsupported camera move: {self.camera_move}")
        if not (3.0 <= float(self.duration_sec) <= 120.0):
            raise ValueError("duration_sec must be between 3 and 120 seconds")
        if int(self.fps) not in {12, 24, 30}:
            raise ValueError("fps must be one of 12, 24 or 30")
        if int(self.width) < 320 or int(self.height) < 180 or int(self.width) % 2 or int(self.height) % 2:
            raise ValueError("Blender resolution must use even dimensions of at least 320x180")
        if not (0.25 <= float(self.intensity) <= 2.0):
            raise ValueError("intensity must be between 0.25 and 2.0")
        if self.scene_label is not None and len(self.scene_label) > 64:
            raise ValueError("scene_label must be at most 64 characters")
        if len(self.caption_lines) > 6:
            raise ValueError("caption_lines supports at most 6 entries")
        for line in self.caption_lines:
            if len(str(line)) > 80:
                raise ValueError("caption lines must be at most 80 characters")

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "Blender3DRequest":
        raw = dict(payload or {})
        captions = raw.get("caption_lines") or ()
        if isinstance(captions, str):
            captions = (captions,)
        return cls(
            theme=str(raw.get("theme") or "auto"),
            scene_label=(str(raw["scene_label"]) if raw.get("scene_label") not in {None, ""} else None),
            caption_lines=tuple(str(item).strip() for item in captions if str(item).strip()),
            duration_sec=float(raw.get("duration_sec") or 18.0),
            fps=int(raw.get("fps") or DEFAULT_FPS),
            width=int(raw.get("width") or DEFAULT_WIDTH),
            height=int(raw.get("height") or DEFAULT_HEIGHT),
            quality=str(raw.get("quality") or "standard"),
            camera_move=str(raw.get("camera_move") or "cinematic"),
            intensity=float(raw.get("intensity") or 1.0),
            include_captions=bool(raw.get("include_captions", True)),
            seed=int(raw.get("seed") or 1939),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["caption_lines"] = list(self.caption_lines)
        data["render_profile"] = quality_profile(self.quality)
        data["frame_count"] = max(1, round(float(self.duration_sec) * int(self.fps)))
        return data


@dataclass(frozen=True)
class TopicDecision:
    theme: str
    label: str
    environment: str
    confidence: float
    matched_cues: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "label": self.label,
            "environment": self.environment,
            "confidence": self.confidence,
            "matched_cues": list(self.matched_cues),
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class Blender3DPlan:
    planner_version: str
    script_text: str
    scenes: list[dict[str, Any]]
    request: Blender3DRequest
    topic: TopicDecision
    title: str
    scene_label: str
    captions: list[str]
    caption_segments: list[dict[str, Any]]
    scene_beats: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planner_version": self.planner_version,
            "script_text": self.script_text,
            "scenes": self.scenes,
            "scene_count": len(self.scenes),
            "request": self.request.to_dict(),
            "topic": self.topic.to_dict(),
            "title": self.title,
            "scene_label": self.scene_label,
            "captions": list(self.captions),
            "caption_segments": list(self.caption_segments),
            "scene_beats": list(self.scene_beats),
            "warnings": list(self.warnings),
            "total_duration_sec": float(self.request.duration_sec),
            "total_frames": max(1, round(float(self.request.duration_sec) * int(self.request.fps))),
        }


_CUE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "ww2_specific": (
        ("world war ii", r"\bworld\s+war\s+(?:ii|2)\b"),
        ("wwii", r"\bww\s?ii\b|\bww2\b"),
        ("second world war", r"\bsecond\s+world\s+war\b"),
        ("1939", r"\b1939\b"),
        ("Germany", r"\bgermany\b|\bgerman\b"),
        ("Poland", r"\bpoland\b|\bpolish\b"),
        ("invaded", r"\binvad(?:e|ed|es|ing)\b|\binvasion\b"),
        ("Normandy", r"\bnormandy\b"),
        ("Nazi", r"\bnazi(?:s)?\b"),
        ("Hitler", r"\bhitler\b"),
        ("Allies", r"\ballies\b|\ballied\b"),
    ),
    "war_general": (
        ("war", r"\bwars?\b|\bjang\b"),
        ("battlefield", r"\bbattlefield(?:s)?\b|\bbattle(?:s)?\b|\bmaidan[-\s]?e[-\s]?jang\b"),
        ("soldiers", r"\bsoldier(?:s)?\b|\btroops?\b|\barmy\b|\barmies\b|\bfauj\b|\bsipahi\b|\bsipahiyon\b"),
        ("tank", r"\btank(?:s)?\b"),
        ("artillery", r"\bartillery\b|\bcannon(?:s)?\b"),
        ("fighter planes", r"\bfighter\s+(?:plane|aircraft)s?\b|\bbomber(?:s)?\b"),
        ("warships", r"\bwarship(?:s)?\b|\bbattleship(?:s)?\b"),
    ),
    "finance": (
        ("dollar", r"\bdollar(?:s)?\b|\busd\b"),
        ("money", r"\bmoney\b|\bcurrency\b|\bcurrencies\b|\bpais(?:a|ay)\b|\bdaulat\b"),
        ("bank", r"\bbank(?:s|ing)?\b"),
        ("market", r"\bmarket(?:s)?\b|\bstock(?:s)?\b|\bshares?\b|\bbazaar\b"),
        ("economy", r"\beconom(?:y|ic|ies)\b|\bfinance\b|\bfinancial\b"),
        ("gold", r"\bgold\b|\breserve(?:s)?\b"),
        ("investment", r"\binvest(?:ment|ing|ors?)?\b|\bprofit(?:s)?\b"),
    ),
    "space": (
        ("space", r"\bspace\b|\bouter\s+space\b"),
        ("rocket", r"\brocket(?:s)?\b|\bspaceship(?:s)?\b"),
        ("NASA", r"\bnasa\b"),
        ("moon", r"\bmoon\b|\blunar\b|\bchaand\b"),
        ("planet", r"\bplanet(?:s)?\b|\bmars\b|\bjupiter\b|\bsaturn\b|\bsayyar(?:a|ay)\b"),
        ("satellite", r"\bsatellite(?:s)?\b|\borbit(?:al)?\b"),
        ("astronaut", r"\bastronaut(?:s)?\b|\bcosmonaut(?:s)?\b"),
    ),
    "ocean": (
        ("ocean", r"\bocean(?:s)?\b|\bsea\b|\bsamandar\b"),
        ("ship", r"\bship(?:s)?\b|\bsailing\b|\bsailboat(?:s)?\b|\bboat(?:s)?\b|\bkashti\b|\bbehri\s+jahaz\b"),
        ("island", r"\bisland(?:s)?\b|\bjazeera\b"),
        ("lighthouse", r"\blighthouse(?:s)?\b"),
        ("voyage", r"\bvoyage(?:s)?\b|\bsailor(?:s)?\b"),
        ("waves", r"\bwave(?:s)?\b|\bcoast(?:al|line)?\b"),
    ),
    "tech": (
        ("robot", r"\brobot(?:s|ic|ics)?\b"),
        ("computer", r"\bcomputer(?:s)?\b|\bsoftware\b|\bhardware\b"),
        ("AI", r"\bartificial\s+intelligence\b|\bai\b"),
        ("data", r"\bdata\b|\bserver(?:s)?\b|\bcloud\s+computing\b"),
        ("technology", r"\btechnolog(?:y|ies|ical)\b|\bdigital\b"),
        ("lab", r"\blaboratory\b|\blab\b|\bscientist(?:s)?\b"),
    ),
    "nature": (
        ("forest", r"\bforest(?:s)?\b|\bjungle(?:s)?\b|\btrees?\b|\bdarakht\b"),
        ("river", r"\briver(?:s)?\b|\bwaterfall(?:s)?\b|\blake(?:s)?\b|\bdarya\b"),
        ("mountain", r"\bmountain(?:s)?\b|\bvalley(?:s)?\b|\bhill(?:s)?\b|\bpahar\b|\bpahari\b"),
        ("nature", r"\bnature\b|\bwilderness\b|\bwildlife\b"),
        ("animals", r"\banimal(?:s)?\b|\bdeer\b|\bbird(?:s)?\b"),
        ("rain", r"\brain\b|\bmonsoon\b|\bseason(?:s)?\b"),
    ),
    "history_fort": (
        ("fort", r"\bfort(?:s|ress|resses)?\b|\bqil(?:a|e|ay)\b|\bcastle(?:s)?\b"),
        ("king", r"\bking(?:s)?\b|\bqueen(?:s)?\b|\bemperor(?:s)?\b|\bbadshah\b|\bsultan\b"),
        ("ancient", r"\bancient\b|\bmedieval\b|\bempire(?:s)?\b|\bsaltanat\b"),
        ("history", r"\bhistory\b|\bhistorical\b|\btareekh\b"),
        ("palace", r"\bpalace(?:s)?\b|\broyal\b"),
    ),
}


def _cue_matches(text_lower: str, group: str) -> list[str]:
    return [label for label, pattern in _CUE_PATTERNS[group] if re.search(pattern, text_lower)]


def _decision(theme: str, cues: list[str], reasons: list[str], confidence: float) -> TopicDecision:
    info = THEMES[theme]
    return TopicDecision(
        theme=theme,
        label=info.label,
        environment=info.environment,
        confidence=round(max(0.0, min(1.0, confidence)), 2),
        matched_cues=tuple(dict.fromkeys(cues)),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def classify_script_topic(script_text: str, scenes: list[dict[str, Any]] | None = None) -> TopicDecision:
    """Classify a script into one Blender theme.

    Specific Second World War evidence intentionally wins over broad ocean,
    city or fort words.  This matters for scripts that mention Pacific fleets,
    destroyed cities and rebuilding in the same story.
    """
    text = (script_text or "").lower()
    scene_list = scenes or []
    ww2 = _cue_matches(text, "ww2_specific")
    war = _cue_matches(text, "war_general")
    parser_locations = {
        str(scene.get("environment") or scene.get("location") or "")
        for scene in scene_list
        if isinstance(scene, dict)
    }
    parser_actions: set[str] = set()
    for scene in scene_list:
        if not isinstance(scene, dict):
            continue
        parser_actions.update(str(action) for action in scene.get("actions", []) or [])
        # Support both the current parser (`characters: ["Bilal"]`) and older
        # normalized scene dictionaries (`characters: [{"actions": [...]}]`).
        for character in scene.get("characters", []) or []:
            if isinstance(character, dict):
                parser_actions.update(str(action) for action in character.get("actions", []) or [])
    reasons: list[str] = []
    if "battlefield" in parser_locations:
        reasons.append("parser_location_battlefield")
    if "fight" in parser_actions:
        reasons.append("parser_action_fight")

    strong_ww2_phrase = any(cue in ww2 for cue in ("world war ii", "wwii", "second world war", "Normandy", "Nazi", "Hitler"))
    historical_cluster = len(set(ww2) & {"1939", "Germany", "Poland", "invaded", "Allies"}) >= 2
    if strong_ww2_phrase or (historical_cluster and war) or (len(ww2) >= 2 and len(war) >= 2):
        reasons.extend(["ww2_specific_cues", "ww2_precedence_over_generic_topics"])
        return _decision("ww2_battlefield", ww2 + war, reasons, 0.98 if strong_ww2_phrase else 0.92)
    if (len(war) >= 2 and ("battlefield" in parser_locations or "fight" in parser_actions)) or len(war) >= 3:
        reasons.append("battlefield_cues")
        return _decision("ww2_battlefield", ww2 + war, reasons, 0.78)

    candidates = [
        ("space_voyage", _cue_matches(text, "space"), "space_cues"),
        ("finance_city", _cue_matches(text, "finance"), "finance_cues"),
        ("tech_lab", _cue_matches(text, "tech"), "technology_cues"),
        ("ocean_voyage", _cue_matches(text, "ocean"), "ocean_cues"),
        ("nature_valley", _cue_matches(text, "nature"), "nature_cues"),
        ("history_fort", _cue_matches(text, "history_fort"), "history_fort_cues"),
    ]
    if "jungle" in parser_locations:
        candidates[4][1].append("parser:jungle")
    if "fort" in parser_locations and candidates[5][1]:
        candidates[5][1].append("parser:fort")
    candidates.sort(key=lambda item: len(item[1]), reverse=True)
    best_theme, best_cues, reason = candidates[0]
    if best_cues:
        return _decision(best_theme, best_cues, [reason], min(0.95, 0.62 + 0.08 * len(best_cues)))
    return _decision("abstract_shapes", [], ["no_strong_topic_cues"], 0.35)


def _clean_caption(value: str, *, limit: int = 48) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n\"'“”‘’")
    cleaned = cleaned.rstrip(".!?")
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cleaned.upper()


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "of", "on", "or",
    "that", "the", "their", "they", "this", "to", "was", "were", "when", "with",
}


def _sentence_caption(sentence: str) -> str:
    text = re.sub(r"^[^:]+\s+(?:says|asks|replies)\s*:\s*", "", sentence.strip(), flags=re.I)
    text = re.sub(r"^[A-Za-z ]+:\s*", "", text)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text)
    useful = [word for word in words if word.lower() not in _STOPWORDS]
    return _clean_caption(" ".join((useful or words)[:5]), limit=42)


def extract_title_and_sentences(script_text: str) -> tuple[str, list[str]]:
    raw = script_text or ""
    title = ""
    title_match = re.search(r"(?im)^\s*title\s*:\s*(.+?)\s*$", raw)
    body = raw
    if title_match:
        title = title_match.group(1).strip()
        body = (raw[: title_match.start()] + " " + raw[title_match.end() :]).strip()
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", body) if item.strip()]
    if not title and sentences and len(sentences[0].split()) <= 6 and not re.search(r"[.!?]$", sentences[0]):
        title = sentences.pop(0)
    return title, sentences


def derive_captions(script_text: str, theme: str, title: str, sentences: list[str]) -> list[str]:
    if theme == "ww2_battlefield":
        text = script_text.lower()
        captions = [_clean_caption(title or "The Global Conflict")]
        if "1939" in text and any(word in text for word in ("invad", "poland", "germany")):
            captions.append("1939 · INVASION")
        if "declared war" in text or "declare war" in text:
            captions.append("WAR DECLARED")
        if any(phrase in text for phrase in ("europe and the pacific", "land, sea", "land · sea", "land sea and air")):
            captions.append("LAND · SEA · AIR")
        for fallback in THEMES[theme].default_captions:
            if fallback not in captions:
                captions.append(fallback)
            if len(captions) >= 4:
                break
        return captions[:4]

    captions: list[str] = []
    if title:
        captions.append(_clean_caption(title))
    for sentence in sentences:
        caption = _sentence_caption(sentence)
        if caption and caption not in captions:
            captions.append(caption)
        if len(captions) >= 4:
            break
    for fallback in THEMES[theme].default_captions:
        if len(captions) >= 3:
            break
        if fallback not in captions:
            captions.append(fallback)
    return [caption for caption in captions if caption][:4]


def _scene_beats(scenes: list[dict[str, Any]], duration_sec: float) -> list[dict[str, Any]]:
    if not scenes:
        return [{"scene_id": "scene_001", "start_sec": 0.0, "end_sec": duration_sec, "environment": "abstract", "beat": "procedural scene"}]
    weights = [max(0.5, float(scene.get("duration_sec") or 4.0)) for scene in scenes]
    total_weight = sum(weights)
    cursor = 0.0
    beats: list[dict[str, Any]] = []
    for index, (scene, weight) in enumerate(zip(scenes, weights)):
        end = duration_sec if index == len(scenes) - 1 else cursor + duration_sec * weight / total_weight
        dialogue = scene.get("dialogue") or []
        first_dialogue = ""
        if dialogue:
            first = dialogue[0]
            first_dialogue = str(first.get("line") or first.get("text") or "") if isinstance(first, dict) else str(first)
        actions = ", ".join(str(action) for action in scene.get("actions", []) or [])
        beats.append(
            {
                "scene_id": str(scene.get("scene_id") or f"scene_{index + 1:03d}"),
                "start_sec": round(cursor, 3),
                "end_sec": round(end, 3),
                "environment": scene.get("environment") or scene.get("location") or "fort",
                "time_of_day": scene.get("time_of_day") or "day",
                "beat": scene.get("scene_description") or scene.get("original_text") or first_dialogue or actions or "procedural scene",
            }
        )
        cursor = end
    return beats


def _caption_segments(captions: list[str], duration_sec: float) -> list[dict[str, Any]]:
    if not captions:
        return []
    width = duration_sec / len(captions)
    return [
        {
            "index": index + 1,
            "text": caption,
            "start_sec": round(index * width, 3),
            "end_sec": round(duration_sec if index == len(captions) - 1 else (index + 1) * width, 3),
        }
        for index, caption in enumerate(captions)
    ]


def plan_blender_3d(
    script_text: str,
    request_payload: dict[str, Any] | Blender3DRequest | None = None,
) -> Blender3DPlan:
    script = script_text or ""
    requested = request_payload if isinstance(request_payload, Blender3DRequest) else Blender3DRequest.from_dict(request_payload)
    scenes = parse_script(script) if script.strip() else []
    auto_topic = classify_script_topic(script, scenes)
    if requested.theme == "auto":
        topic = auto_topic
        resolved = replace(requested, theme=topic.theme)
    else:
        info = THEMES[requested.theme]
        topic = TopicDecision(
            theme=info.id,
            label=info.label,
            environment=info.environment,
            confidence=1.0,
            matched_cues=auto_topic.matched_cues,
            reason_codes=("explicit_theme_override", *auto_topic.reason_codes),
        )
        resolved = requested

    title, sentences = extract_title_and_sentences(script)
    if not title:
        title = THEMES[topic.theme].label
    captions = list(resolved.caption_lines)
    if not captions:
        captions = derive_captions(script, topic.theme, title, sentences)
    captions = [_clean_caption(caption) for caption in captions if _clean_caption(caption)][:4]
    if not resolved.include_captions:
        captions = []
    scene_label = resolved.scene_label or f"{THEMES[topic.theme].label.upper()} · BLENDER 3D"
    resolved = replace(resolved, scene_label=scene_label, caption_lines=tuple(captions))
    warnings: list[str] = []
    if not script.strip():
        warnings.append("Script is empty; the selected/default procedural theme will be rendered without script beats.")
    if topic.theme == "ww2_battlefield" and requested.theme == "auto":
        warnings.append("WWII cues were detected, so the large Blender battlefield scene was selected.")
    return Blender3DPlan(
        planner_version=PLANNER_VERSION,
        script_text=script,
        scenes=scenes,
        request=resolved,
        topic=topic,
        title=title,
        scene_label=scene_label,
        captions=captions,
        caption_segments=_caption_segments(captions, float(resolved.duration_sec)),
        scene_beats=_scene_beats(scenes, float(resolved.duration_sec)),
        warnings=warnings,
    )
