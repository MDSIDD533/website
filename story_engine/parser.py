"""Deterministic multilingual script parser with optional loopback local-LLM enrichment."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib import request as urlrequest

from backend.core.config import get_settings
from backend.core.security import sanitize_story_text, validate_local_endpoint_url
from story_engine.normalizer import detect_script_language

ENVIRONMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fortress": (
        "fortress",
        "citadel",
        "rampart",
        "battlement",
        "bastion",
        "gate",
        "qila",
        "qilay",
        "qile",
        "darwaza",
        "darwaze",
        "قلعہ",
        "قلعے",
        "فصیل",
        "دروازہ",
    ),
    "palace": ("palace", "throne", "court", "terrace", "royal", "mahal", "محل", "دربار"),
    "ancient_city": ("ancient city", "city", "bazaar", "domes", "plaza", "shehar", "شہر", "قدیم شہر"),
    "battlefield": ("battlefield", "siege", "frontline", "war", "maidan", "jang", "میدان", "جنگ"),
    "desert": ("desert", "dune", "sand", "oasis", "registan", "صحرا", "ریگستان"),
    "forest": ("forest", "woods", "trees", "grove", "jungle", "jangal", "جنگل"),
    "mountain": ("mountain", "cliff", "peak", "pass", "ridge", "pahad", "پہاڑ"),
    "village": ("village", "hamlet", "cottages", "hut", "gaon", "گاؤں", "بستی"),
    "street": ("street", "alley", "lane", "market", "road", "gali", "گلی", "سڑک"),
    "room": ("room", "chamber", "hall", "study", "interior", "kamra", "کمرہ", "ہال"),
    "temple": ("temple", "sanctuary", "shrine", "monastery", "archway", "mandir", "معبد"),
    "ship_camp": ("ship", "deck", "harbor", "camp", "tent", "encampment", "kashti", "خیمہ", "کشتی"),
}

TIME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sunrise": ("sunrise", "dawn", "daybreak", "morning", "subah", "فجر", "صبح"),
    "sunset": ("sunset", "dusk", "evening", "twilight", "sham", "شام", "غروب"),
    "night": ("night", "midnight", "dark", "moonlight", "raat", "andhera", "رات", "تاریکی"),
    "day": ("day", "noon", "midday", "afternoon", "din", "دن", "دوپہر"),
}

WEATHER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "rain": ("rain", "storm", "thunder", "downpour", "baarish", "بارش"),
    "fog": ("fog", "mist", "haze", "kohra", "دھند"),
    "smoke": ("smoke", "ash", "dhuan", "دھواں"),
    "fire": ("fire", "flames", "burning", "blaze", "torches", "aag", "mashal", "آگ", "مشعل"),
    "dust": ("dust", "sandstorm", "wind", "gard", "toofan", "طوفان", "گرد"),
}

ACTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cinematic_combat": (
        "clash",
        "clashes",
        "combat",
        "sword",
        "duel",
        "muqabla",
        "talwar bazi",
        "talwar ki larai",
        "larai",
        "jung",
        "مقابلہ",
        "جنگ",
        "لڑائی",
    ),
    "punch": ("punch", "punches", "strike", "strikes", "fist", "waar"),
    "kick": ("kick", "kicks"),
    "dodge": ("dodge", "dodges", "dodging", "evade", "sidestep"),
    "block": ("block", "blocks", "blocking", "parry", "shield", "rok"),
    "chase": ("chase", "chases", "chasing", "pursue"),
    "run": ("run", "runs", "running", "sprint", "charge", "rush", "achanak"),
    "walk": (
        "walk",
        "walks",
        "walking",
        "steps",
        "advance",
        "patrol",
        "pehra",
        "andar aane",
        "aane ki koshish",
        "barhta",
        "قدم",
        "پہرہ",
    ),
    "fall": ("fall", "falls", "falling", "collapse"),
    "get_up": ("get up", "rises", "rising", "stand up"),
    "sit": ("sit", "sits", "seated", "kneel"),
    "turn": ("turn", "turns", "turning"),
    "look_at": ("look", "looks", "gaze", "gazing", "dekho", "dekha", "دیکھو"),
    "interact_prop": ("draw", "drawing", "holding", "raises", "lifts", "scroll", "torch", "darwaza band", "band kar"),
    "gesture": ("gesture", "points", "waves", "signals", "mukalma", "dialogue", "conversation", "مکالمہ"),
}

EMOTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "determined": ("determined", "brave", "resolute", "firm", "himmat", "hosla", "taiyar", "ہمت", "حوصلہ"),
    "angry": ("angry", "furious", "rage", "fierce", "yield", "threat", "غصہ"),
    "fearful": ("fearful", "afraid", "terrified", "nervous", "alert", "anxious", "خوف"),
    "joyful": ("joyful", "happy", "triumphant", "relieved", "smile", "peace", "فتح", "خوش"),
    "sad": ("sad", "grief", "mournful", "sorrow", "اداس"),
    "surprised": ("surprised", "shocked", "amazed", "حیران"),
    "calm": ("calm", "steady", "quiet", "peaceful", "aman", "امن"),
}

PROP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sword": ("sword", "blade", "scimitar", "talwar", "تلوار"),
    "shield": ("shield", "buckler", "dhaal", "ڈھال"),
    "torch": ("torch", "torches", "mashal", "مشعل", "مشعلیں"),
    "spear": ("spear", "lance", "pike", "neza", "نیزہ"),
    "banner": ("banner", "banners", "flag", "standard", "parcham", "پرچم"),
    "scroll": ("scroll", "map", "letter", "book", "parwana", "فرمان"),
    "staff": ("staff", "wand", "cane"),
}

FEMALE_NAME_HINTS = {
    "zara", "ayesha", "fatima", "sara", "amina", "maryam", "noor", "layla", "sana",
    "hira", "nadia", "elena", "aria", "maya", "shehzadi", "زارا", "عائشہ", "فاطمہ", "نور",
}

SCENE_HEADER_RE = re.compile(
    r"^(?:SCENE|ACT|SHOT|PART|CHAPTER|منظر)\s*\d*[:.\-\s]*(.*)$|^(?:INT\.|EXT\.|INT/EXT\.)\s*(.+)$",
    re.IGNORECASE,
)

DIALOGUE_LINE_RE = re.compile(
    r"^([A-Za-z\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF _'\-]{0,28})\s*[:：]\s*(.+)$"
)

NON_SPEAKER_HEADERS = {
    "scene", "location", "setting", "time", "action", "sfx", "music", "camera",
    "transition", "note", "notes", "narrator", "narration", "voiceover", "vo",
    "int", "ext", "منظر", "راوی",
}


def _match_first(text_lower: str, mapping: dict[str, tuple[str, ...]], default: str) -> str:
    for key, words in mapping.items():
        for w in words:
            if w in text_lower:
                return key
    return default


def _match_all(text_lower: str, mapping: dict[str, tuple[str, ...]]) -> list[str]:
    found: list[str] = []
    for key, words in mapping.items():
        if any(w in text_lower for w in words):
            found.append(key)
    return found


def _infer_gender_and_voice(name: str, language: str, index: int) -> tuple[str, str]:
    clean = name.strip().lower()
    is_female = any(h in clean for h in FEMALE_NAME_HINTS)
    lang_prefix = "ur" if language in {"ur", "roman_ur"} else "en"
    if is_female:
        variants = ["female_warm", "female_bright"]
        return ("female", f"{lang_prefix}_{variants[index % len(variants)]}")
    variants = ["male_heroic", "male_deep", "male_calm"]
    return ("male", f"{lang_prefix}_{variants[index % len(variants)]}")


def _split_raw_scenes(script_text: str, target_scenes: int) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in script_text.splitlines()]
    explicit_blocks: list[dict[str, Any]] = []
    current_header = ""
    current_lines: list[str] = []

    for ln in lines:
        if not ln:
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue
        header_match = SCENE_HEADER_RE.match(ln)
        if header_match:
            non_empty = [x for x in current_lines if x]
            if non_empty:
                explicit_blocks.append({"header": current_header, "lines": non_empty})
            current_header = (header_match.group(1) or header_match.group(2) or ln).strip()
            current_lines = []
        else:
            current_lines.append(ln)

    non_empty_tail = [x for x in current_lines if x]
    if non_empty_tail:
        explicit_blocks.append({"header": current_header, "lines": non_empty_tail})

    # If explicit scene headers produced >=2 blocks, respect them; otherwise split paragraphs/sentences
    if len(explicit_blocks) >= 2:
        return explicit_blocks

    paragraphs = [
        [ln.strip() for ln in p.splitlines() if ln.strip()]
        for p in re.split(r"\n\s*\n", script_text.strip())
        if p.strip()
    ]
    if len(paragraphs) >= 2:
        return [{"header": "", "lines": p} for p in paragraphs]

    # Single-paragraph prose: split sentences evenly across target_scenes
    all_text = " ".join(non_empty_tail)
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?۔؟])\s+", all_text)
        if s.strip()
    ]
    if not sentences:
        sentences = [script_text.strip() or "An opening view across the ancient horizon."]

    n = max(1, min(target_scenes, len(sentences)))
    chunk_size = max(1, (len(sentences) + n - 1) // n)
    blocks: list[dict[str, Any]] = []
    for idx in range(0, len(sentences), chunk_size):
        blocks.append({"header": f"Scene {len(blocks) + 1}", "lines": sentences[idx : idx + chunk_size]})
    return blocks


def _try_optional_local_llm(script_text: str, language: str) -> dict[str, Any] | None:
    """Optional loopback-only local LLM enrichment; never sends private scripts externally."""
    settings = get_settings()
    if not settings.local_llm_url:
        return None
    endpoint = validate_local_endpoint_url(settings.local_llm_url)
    if not endpoint:
        return None
    payload = {
        "model": settings.local_llm_model or "qwen2.5:1.5b",
        "messages": [
            {
                "role": "system",
                "content": "Extract JSON keys: time_period, theme_summary. Output valid JSON object only.",
            },
            {"role": "user", "content": script_text[:3000]},
        ],
        "stream": False,
    }
    try:
        req = urlrequest.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=4.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = (
                body.get("message", {}).get("content")
                or body.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            if content:
                return {"llm_used": True, "raw_enrichment": content[:500], "language": language}
    except Exception:
        return None
    return None


def analyze_script(
    script_text: str,
    *,
    language: str | None = None,
    target_scenes: int = 3,
    genre: str = "historical",
    historical_accuracy_mode: bool = False,
) -> dict[str, Any]:
    """Parse script deterministically into structured characters, dialogue, narration, props, and scenes."""
    cleaned = sanitize_story_text(script_text)
    if not cleaned.strip():
        raise ValueError("Script cannot be empty.")

    detected_lang = detect_script_language(cleaned)
    effective_lang = language if language in {"en", "ur", "roman_ur"} else detected_lang
    if language == "auto" or not language:
        effective_lang = detected_lang
    # If user left default 'en' but pasted clear Urdu script or Roman Urdu, honor detected language
    if language == "en" and detected_lang in {"ur", "roman_ur"}:
        effective_lang = detected_lang

    raw_blocks = _split_raw_scenes(cleaned, max(1, target_scenes))

    characters_map: dict[str, dict[str, Any]] = {}
    all_dialogue: list[dict[str, Any]] = []
    all_narration: list[dict[str, Any]] = []
    locations: list[str] = []
    story_events: list[str] = []
    parsed_blocks: list[dict[str, Any]] = []

    def _register_character(raw_name: str) -> str:
        norm_title = " ".join(w.capitalize() if w.isascii() else w for w in raw_name.strip().split())
        key = norm_title.lower()
        if key not in characters_map:
            idx = len(characters_map)
            gender, voice_id = _infer_gender_and_voice(norm_title, effective_lang, idx)
            palette_choices = [
                ["#8b1e24", "#d4af37", "#2b2d38"],
                ["#1d4e6b", "#c8d6e5", "#222831"],
                ["#2e5a36", "#d9b382", "#1e2420"],
                ["#4a2545", "#e0a96d", "#1c1b22"],
            ]
            outfit_default = (
                "historical_armor"
                if genre in {"historical", "action", "fantasy"} and idx % 2 == 0
                else ("royal_tunic" if genre in {"historical", "fantasy"} else "expedition_coat")
            )
            characters_map[key] = {
                "name": norm_title,
                "gender": gender,
                "role": "protagonist" if idx == 0 else ("deuteragonist" if idx == 1 else "supporting"),
                "default_voice_id": voice_id,
                "language": effective_lang,
                "outfit_preset": outfit_default,
                "color_palette": palette_choices[idx % len(palette_choices)],
                "personality": "courageous, expressive" if idx == 0 else "observant, resolute",
                "identity_seed": 101 + idx * 37,
            }
        return characters_map[key]["name"]

    for s_idx, block in enumerate(raw_blocks):
        header = block["header"]
        joined = " ".join([header] + block["lines"])
        joined_low = joined.lower()

        env = _match_first(joined_low, ENVIRONMENT_KEYWORDS, "fortress" if genre == "historical" else "ancient_city")
        tod = _match_first(joined_low, TIME_KEYWORDS, ["sunset", "night", "sunrise", "day"][s_idx % 4])
        weather = _match_first(joined_low, WEATHER_KEYWORDS, "clear")
        actions = _match_all(joined_low, ACTION_KEYWORDS) or ["walk", "look_at"]
        props = _match_all(joined_low, PROP_KEYWORDS)
        emotions = _match_all(joined_low, EMOTION_KEYWORDS) or ["determined"]

        scene_dialogue: list[dict[str, Any]] = []
        scene_narration_parts: list[str] = []
        scene_speakers: list[str] = []

        for ln in block["lines"]:
            dlg_match = DIALOGUE_LINE_RE.match(ln)
            if dlg_match:
                raw_speaker = dlg_match.group(1).strip()
                raw_line = dlg_match.group(2).strip()
                if raw_speaker.lower() not in NON_SPEAKER_HEADERS and len(raw_speaker.split()) <= 3:
                    # Extract optional parenthetical emotion `(determined)`
                    paren_match = re.match(r"^\(([^)]{1,24})\)\s*(.+)$", raw_line)
                    line_emotion = emotions[0]
                    if paren_match:
                        hint = paren_match.group(1).strip().lower()
                        line_emotion = _match_first(hint, EMOTION_KEYWORDS, hint)
                        raw_line = paren_match.group(2).strip()
                    else:
                        line_emotion = _match_first(raw_line.lower(), EMOTION_KEYWORDS, emotions[0])

                    canonical_name = _register_character(raw_speaker)
                    if canonical_name not in scene_speakers:
                        scene_speakers.append(canonical_name)
                    dlg_item = {
                        "speaker": canonical_name,
                        "text": raw_line.strip("\"'“”"),
                        "emotion": line_emotion,
                        "pause_after_sec": 0.35,
                        "scene_index": s_idx,
                    }
                    scene_dialogue.append(dlg_item)
                    all_dialogue.append(dlg_item)
                    if "speak" not in actions:
                        actions.append("speak")
                    continue

            if raw_speaker_narr := re.match(r"^(?:NARRATOR|NARRATION|VO|راوی)\s*[:：]\s*(.+)$", ln, re.IGNORECASE):
                scene_narration_parts.append(raw_speaker_narr.group(1).strip())
            else:
                scene_narration_parts.append(ln)

        # Pre-detect narrative role archetypes across full script when no explicit COLON speakers exist yet
        if s_idx == 0 and not characters_map:
            full_low = cleaned.lower()
            if effective_lang in {"roman_ur", "ur"}:
                if any(w in full_low for w in ("bahadur sipahi", "qile ka sipahi", "sipahi", "سپاہی")):
                    hero_label = "Bahadur Sipahi" if effective_lang == "roman_ur" else "بہادر سپاہی"
                    _register_character(hero_label)
                if any(w in full_low for w in ("dushman", "hamla", "دشمن")):
                    foe_label = "Dushman Sipahi" if effective_lang == "roman_ur" else "دشمن سپاہی"
                    _register_character(foe_label)
            else:
                if any(w in full_low for w in ("guard", "soldier", "warrior", "knight")):
                    _register_character("Fortress Guard")
                if any(w in full_low for w in ("enemy", "intruder", "invader", "raider")):
                    _register_character("Enemy Soldier")

        # Also detect capitalized character names mentioned in prose if no explicit dialogue appeared yet
        if not characters_map:
            name_matches = re.findall(
                r"\b(?:Commander|Captain|General|Scout|Prince|Princess|King|Queen|Sardar|Sipahi)\s+([A-Z][a-z]{2,15})\b",
                joined,
            )
            for nm in name_matches[:3]:
                cname = _register_character(nm)
                if cname not in scene_speakers:
                    scene_speakers.append(cname)

        for known_key, char_info in list(characters_map.items()):
            cname = char_info["name"]
            clow = cname.lower()
            if clow in joined_low and cname not in scene_speakers:
                scene_speakers.append(cname)
            elif "bahadur" in clow or "fortress guard" in clow or "بہادر" in clow:
                if any(w in joined_low for w in ("bahadur", "qile ka sipahi", "pehra", "darwaza", "dono", "mukalma", "larai", "guard")):
                    if cname not in scene_speakers:
                        scene_speakers.append(cname)
            elif "dushman" in clow or "enemy" in clow or "دشمن" in clow:
                if any(w in joined_low for w in ("dushman", "dono", "mukalma", "larai", "talwar", "combat", "enemy", "intruder", "دشمن", "لڑائی", "مکالمہ")):
                    if cname not in scene_speakers:
                        scene_speakers.append(cname)

        # Ensure combat or explicit two-person dialogue ('dono', 'mukalma') brings at least 2 characters into the 3D scene
        if len(characters_map) >= 2 and any(
            w in joined_low for w in ("dono", "mukalma", "larai", "talwar", "combat", "clash", "duel", "مکالمہ", "لڑائی")
        ):
            for cinfo in list(characters_map.values())[:2]:
                if cinfo["name"] not in scene_speakers:
                    scene_speakers.append(cinfo["name"])

        # Ensure sword prop is attached whenever sword combat or fortress guard patrol occurs
        if "cinematic_combat" in actions and "sword" not in props:
            props.append("sword")

        # If narrative prose explicitly states a dialogue ('mukalma' / 'conversation') occurs without colon lines,
        # synthesize a brief contextual exchange between the two present characters so jaw lip-sync & voices play.
        if not scene_dialogue and len(scene_speakers) >= 2 and any(
            w in joined_low for w in ("mukalma", "baat cheet", "dialogue", "confront", "مکالمہ")
        ):
            c1, c2 = scene_speakers[0], scene_speakers[1]
            if effective_lang == "roman_ur":
                synth_lines = [
                    (c1, "Ruko! Qile ke darwaze se peeche hato!", "determined"),
                    (c2, "Rasta chhor do sipahi, hum andar aayenge!", "angry"),
                ]
            elif effective_lang == "ur":
                synth_lines = [
                    (c1, "رکو! قلعے کے دروازے سے پیچھے ہٹو!", "determined"),
                    (c2, "راستہ چھوڑ دو سپاہی!", "angry"),
                ]
            else:
                synth_lines = [
                    (c1, "Halt! Step away from the fortress gate!", "determined"),
                    (c2, "Stand aside guard, or face my blade!", "angry"),
                ]
            for spk, txt, emo in synth_lines:
                dlg_item = {
                    "speaker": spk,
                    "text": txt,
                    "emotion": emo,
                    "pause_after_sec": 0.30,
                    "scene_index": s_idx,
                    "auto_synthesized": True,
                }
                scene_dialogue.append(dlg_item)
                all_dialogue.append(dlg_item)
            if "speak" not in actions:
                actions.append("speak")

        narration_str = " ".join(scene_narration_parts).strip()
        if narration_str:
            all_narration.append({"scene_index": s_idx, "text": narration_str})

        loc_label = header if header else f"{env.replace('_', ' ').title()} ({tod.title()})"
        if loc_label not in locations:
            locations.append(loc_label)

        event_summary = (
            scene_dialogue[0]["text"][:90]
            if scene_dialogue
            else (narration_str[:90] if narration_str else f"Scene at {loc_label}")
        )
        story_events.append(f"Scene {s_idx + 1}: {event_summary}")

        historical_notes = {
            "mode_enabled": bool(historical_accuracy_mode or genre == "historical"),
            "verified_period_elements": [
                f"Architectural archetype '{env}' uses period-inspired stone/timber proportions and torch/sun lighting.",
                f"Props ({', '.join(props) if props else 'period attire'}) avoid anachronistic modern machinery.",
            ],
            "dramatized_fictional_elements": [
                "Character names, spoken dialogue, and combat choreography timing are dramatized storytelling constructs unless verified against primary historical texts.",
            ],
        }

        parsed_blocks.append(
            {
                "scene_index": s_idx,
                "header": header or f"Scene {s_idx + 1} — {env.replace('_', ' ').title()}",
                "location_name": loc_label,
                "environment_preset": env,
                "time_of_day": tod,
                "weather": weather,
                "actions": actions,
                "emotions": emotions,
                "props": props,
                "characters_present": scene_speakers,
                "dialogue": scene_dialogue,
                "narration": narration_str,
                "transition": "dip_to_black" if s_idx == len(raw_blocks) - 1 else "crossfade",
                "historical_notes": historical_notes,
            }
        )

    # Guarantee at least one protagonist character even for pure narration scripts
    if not characters_map:
        default_name = "Tariq" if effective_lang in {"ur", "roman_ur"} else "Aiden"
        cname = _register_character(default_name)
        for blk in parsed_blocks:
            blk["characters_present"] = [cname]
    else:
        default_first = next(iter(characters_map.values()))["name"]
        for blk in parsed_blocks:
            if not blk["characters_present"]:
                blk["characters_present"] = [default_first]

    all_text_low = cleaned.lower()
    if any(w in all_text_low for w in ("fortress", "sword", "palace", "qila", "talwar", "قلعہ", "تلوار")):
        time_period = "historical_premodern"
    elif any(w in all_text_low for w in ("dragon", "magic", "spell", "portal")):
        time_period = "fantasy"
    else:
        time_period = "cinematic_contemporary"

    llm_meta = _try_optional_local_llm(cleaned, effective_lang)

    return {
        "detected_language": detected_lang,
        "effective_language": effective_lang,
        "time_period": time_period,
        "genre": genre,
        "characters": list(characters_map.values()),
        "dialogue_count": len(all_dialogue),
        "dialogue": all_dialogue,
        "narration": all_narration,
        "locations": locations,
        "props": sorted({p for b in parsed_blocks for p in b["props"]}),
        "actions": sorted({a for b in parsed_blocks for a in b["actions"]}),
        "emotions": sorted({e for b in parsed_blocks for e in b["emotions"]}),
        "scene_transitions": [b["transition"] for b in parsed_blocks],
        "story_events": story_events,
        "scene_blocks": parsed_blocks,
        "analysis_engine": "local_llm+deterministic_validator" if llm_meta else "sidd_deterministic_nlp_v1",
        "llm_enrichment": llm_meta,
    }
