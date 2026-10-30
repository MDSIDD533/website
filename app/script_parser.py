"""Rule-based script parser for the local script-to-video pipeline.

`parse_script(text)` turns a Roman Urdu / English mixed script into a
list of scene dicts, one per sentence. No LLM, no external services —
plain keyword rules only.

Scene shape::

    {
        "scene_id": int,            # 1-based
        "location": str,            # "fort" | "battlefield" | "jungle"
        "time_of_day": str,         # "sunset" | "night" | "day"
        "characters": list[str],    # e.g. ["Bilal", "Zara"]
        "actions": list[str],       # e.g. ["walk", "light_torch", "talk"]
        "dialogue": list[dict],     # [{"speaker": "Bilal", "line": "..."}]
        "duration_sec": float,      # heuristic, capped at 8.0
    }

Rules (see Phase 2 spec, sub-step 3.1):
  * Sentences split on ``.`` ``!`` ``?`` and newlines, but never inside
    quotes (so ``'Guard your left flank!'`` stays one scene). A
    word-internal apostrophe (``mash'al``) is not treated as a quote.
  * Keyword scans (location / time / characters / actions) run on the
    narrative part of the sentence — quoted dialogue text is removed
    first so words spoken in dialogue cannot trigger false actions.
  * Location and time are independent per scene: if a sentence names no
    location or time, that scene gets its own default (``fort`` / ``day``).
    The sole cross-scene exception is the pronoun ``dono`` ("both"), which
    may resolve to the last two distinct known characters.
  * Duration: 3.0s base + 1.0s per dialogue line + 0.5s per action
    beyond the first, capped at 8.0s.
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = ["parse_script"]

# ---------------------------------------------------------------------------
# Keyword tables (all matched case-insensitively)
# ---------------------------------------------------------------------------

_LOCATION_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("fort", re.compile(r"\bqil\w*|\bfort\w*", re.IGNORECASE)),
    ("battlefield", re.compile(r"\bbattlefield\b|\bmaidan\w*|\bjang\b", re.IGNORECASE)),
    ("jungle", re.compile(r"\bjungle\w*|\bjangal\w*", re.IGNORECASE)),
]

_TIME_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("sunset", re.compile(r"\b(?:sunset|shaam|dhoop)\b", re.IGNORECASE)),
    ("night", re.compile(r"\b(?:night|raat)\b", re.IGNORECASE)),
]

_CHARACTER_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("Bilal", re.compile(r"\bbilal\b", re.IGNORECASE)),
    ("Zara", re.compile(r"\bzara\b", re.IGNORECASE)),
]

_DONO_RE = re.compile(r"\bdono\b", re.IGNORECASE)

_ACTION_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    (
        "walk",
        re.compile(r"\bchal\w*|\bwalk\w*|\baat(?:a|i|e)\b", re.IGNORECASE),
    ),
    ("run", re.compile(r"\bdaud\w*|\brun(?:s|ning)?\b", re.IGNORECASE)),
    ("light_torch", re.compile(r"mash['’]?al|\btorch\w*", re.IGNORECASE)),
    ("fight", re.compile(r"\b(?:larta|larti|larte|larna|larai|fight|fights|fighting)\b", re.IGNORECASE)),
    ("talk", re.compile(r"\bbaat\w*|\b(?:kehta|kehti|kehte|says|say)\b", re.IGNORECASE)),
]

# Quoted spans: '...', "...", ‘...’, “...”
_QUOTE_RE = re.compile(r"'([^'\n]+)'|\"([^\"]+)\"|‘([^’]+)’|“([^”]+)”")

# Unquoted dialogue after a speech verb + colon, e.g. "Bilal kehta hai: ..."
_COLON_DIALOGUE_RE = re.compile(r"(?:kehta hai|kehti hai|says)\s*:\s*(.+)$", re.IGNORECASE)

_OPENERS = {"'": "'", '"': '"', "‘": "’", "“": "”"}


# ---------------------------------------------------------------------------
# Sentence splitting (quote aware)
# ---------------------------------------------------------------------------

def _is_apostrophe(text: str, i: int) -> bool:
    """True if ``text[i]`` is a word-internal apostrophe, e.g. ``mash'al``."""
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    return prev.isalnum() and nxt.isalnum()


def split_sentences(text: str) -> list[str]:
    """Split on ``. ! ?`` and newlines without splitting inside quotes."""
    sentences: list[str] = []
    buf: list[str] = []
    closer: Optional[str] = None
    i = 0
    while i < len(text):
        ch = text[i]
        if closer is not None:
            buf.append(ch)
            if ch == closer and not (ch == "'" and _is_apostrophe(text, i)):
                closer = None
            i += 1
            continue
        if ch in _OPENERS and not (ch == "'" and _is_apostrophe(text, i)):
            closer = _OPENERS[ch]
            buf.append(ch)
            i += 1
            continue
        if ch in ".!?" or ch == "\n":
            sentence = "".join(buf).strip()
            if ch != "\n":
                sentence += ch
            if sentence.strip(".!? "):
                sentences.append(sentence.strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail.strip(".!? "):
        sentences.append(tail)
    return sentences


# ---------------------------------------------------------------------------
# Per-sentence extraction helpers
# ---------------------------------------------------------------------------

def _first_match(text: str, patterns: list[tuple[str, "re.Pattern[str]"]]) -> Optional[str]:
    """Return the value whose keyword appears earliest in ``text``."""
    best: Optional[tuple[int, int, str]] = None  # (start, -len, value)
    for value, pattern in patterns:
        m = pattern.search(text)
        if m:
            key = (m.start(), -(m.end() - m.start()), value)
            if best is None or key < best:
                best = key
    return best[2] if best else None


def _ordered_unique(text: str, patterns: list[tuple[str, "re.Pattern[str]"]]) -> list[str]:
    """Values whose keywords appear in ``text``, ordered by appearance."""
    hits: list[tuple[int, str]] = []
    for value, pattern in patterns:
        m = pattern.search(text)
        if m:
            hits.append((m.start(), value))
    return [value for _, value in sorted(hits, key=lambda h: h[0])]


def _resolve_dono_characters(
    explicit: list[str], seen_characters: list[str]
) -> list[str]:
    """Resolve ``dono`` to the last two distinct known characters.

    ``seen_characters`` is in first-mention order across earlier scenes.
    Explicit names in the current sentence keep their sentence order when
    both are present.  If fewer than two characters are known, only the
    explicit current names are returned; the parser does not invent the
    missing second person.
    """

    if len(explicit) >= 2:
        return explicit

    history = list(seen_characters)
    for name in explicit:
        if name not in history:
            history.append(name)
    if len(history) >= 2:
        return history[-2:]
    return explicit


def _speaker_before(original: str, pos: int, fallback: Optional[str]) -> str:
    """Last character mentioned in ``original`` before offset ``pos``."""
    best: Optional[tuple[int, str]] = None
    for name, pattern in _CHARACTER_PATTERNS:
        for m in pattern.finditer(original, 0, pos):
            if best is None or m.start() > best[0]:
                best = (m.start(), name)
    if best:
        return best[1]
    return fallback or "Unknown"


def _extract_dialogue(original: str, characters: list[str]) -> list[dict]:
    """Pull dialogue lines out of one sentence (quoted, or after a colon)."""
    fallback = characters[0] if characters else None
    dialogue: list[dict] = []
    for m in _QUOTE_RE.finditer(original):
        line = next(g for g in m.groups() if g is not None).strip()
        if not line:
            continue
        dialogue.append({"speaker": _speaker_before(original, m.start(), fallback), "line": line})
    if dialogue:
        return dialogue
    colon = _COLON_DIALOGUE_RE.search(original)
    if colon:
        line = colon.group(1).strip().strip(".").strip()
        if line:
            dialogue.append(
                {"speaker": _speaker_before(original, colon.start(1), fallback), "line": line}
            )
    return dialogue


def _duration(actions: list[str], dialogue: list[dict]) -> float:
    seconds = 3.0 + 1.0 * len(dialogue) + 0.5 * max(0, len(actions) - 1)
    return min(8.0, seconds)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_script(text: str) -> list[dict]:
    """Parse a Roman Urdu / English mixed script into a list of scenes."""
    scenes: list[dict] = []
    seen_characters: list[str] = []
    for raw in split_sentences(text or ""):
        # Keyword scans run on narrative text only (quotes removed).
        narrative = _QUOTE_RE.sub(" ", raw)
        # Location/time never inherit: each scene uses its own default.
        location = _first_match(narrative, _LOCATION_PATTERNS) or "fort"
        time_of_day = _first_match(narrative, _TIME_PATTERNS) or "day"
        characters = _ordered_unique(narrative, _CHARACTER_PATTERNS)
        if _DONO_RE.search(narrative):
            characters = _resolve_dono_characters(characters, seen_characters)
        actions = _ordered_unique(narrative, _ACTION_PATTERNS)
        dialogue = _extract_dialogue(raw, characters)
        scenes.append(
            {
                "scene_id": len(scenes) + 1,
                "location": location,
                "time_of_day": time_of_day,
                "characters": characters,
                "actions": actions,
                "dialogue": dialogue,
                "duration_sec": _duration(actions, dialogue),
            }
        )
        for name in characters:
            if name not in seen_characters:
                seen_characters.append(name)
    return scenes
