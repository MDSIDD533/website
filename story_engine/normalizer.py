"""Language detection and Roman-Urdu / Urdu / English text normalization."""

from __future__ import annotations

import re

from backend.core.security import sanitize_story_text

_URDU_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# High-frequency Roman Urdu vocabulary & particles for reliable detection and Urdu/phonetic mapping
ROMAN_URDU_LEXICON: dict[str, str] = {
    "aur": "اور",
    "hai": "ہے",
    "hain": "ہیں",
    "tha": "تھا",
    "thi": "تھی",
    "the": "تھے",
    "mein": "میں",
    "main": "میں",
    "hum": "ہم",
    "tum": "تم",
    "aap": "آپ",
    "woh": "وہ",
    "yeh": "یہ",
    "ye": "یہ",
    "ke": "کے",
    "ki": "کی",
    "ka": "کا",
    "ko": "کو",
    "se": "سے",
    "par": "پر",
    "ne": "نے",
    "nahi": "نہیں",
    "nahin": "نہیں",
    "kya": "کیا",
    "kyun": "کیوں",
    "kaise": "کیسے",
    "jab": "جب",
    "tab": "تب",
    "ab": "اب",
    "phir": "پھر",
    "lekin": "لیکن",
    "magar": "مگر",
    "sardar": "سردار",
    "sipahi": "سپاہی",
    "badshah": "بادشاہ",
    "shehzadi": "شہزادی",
    "qila": "قلعہ",
    "qilay": "قلعے",
    "qile": "قلعے",
    "purana": "پرانا",
    "purane": "پرانے",
    "purani": "پرانی",
    "darwaza": "دروازہ",
    "darwaze": "دروازے",
    "bahadur": "بہادر",
    "pehra": "پہرہ",
    "de": "دے",
    "raha": "رہا",
    "rahi": "رہی",
    "rahe": "رہے",
    "achanak": "اچانک",
    "paas": "پاس",
    "qareeb": "قریب",
    "aane": "آنے",
    "aana": "آنا",
    "aata": "آتا",
    "aati": "آتی",
    "koshish": "کوشش",
    "karta": "کرتا",
    "karti": "کرتی",
    "karte": "کرتے",
    "dono": "دونوں",
    "darmiyan": "درمیان",
    "mukalma": "مکالمہ",
    "baat": "بات",
    "hota": "ہوتا",
    "hoti": "ہوتی",
    "hote": "ہوتے",
    "chhota": "چھوٹا",
    "chhoti": "چھوٹی",
    "larai": "لڑائی",
    "jung": "جنگ",
    "pehla": "پہلا",
    "pehli": "پہلی",
    "aakhir": "آخر",
    "band": "بند",
    "khol": "کھول",
    "kar": "کر",
    "deta": "دیتا",
    "deti": "دیتی",
    "mehfooz": "محفوظ",
    "rehta": "رہتا",
    "rehti": "رہتی",
    "khabardar": "خبردار",
    "ruko": "رکو",
    "rasta": "راستہ",
    "chhor": "چھوڑ",
    "aayenge": "آئیں گے",
    "kon": "کون",
    "kaun": "کون",
    "ho": "ہو",
    "piche": "پیچھے",
    "hato": "ہٹو",
    "deewar": "دیوار",
    "talwar": "تلوار",
    "dhaal": "ڈھال",
    "jang": "جنگ",
    "maidan": "میدان",
    "registan": "ریگستان",
    "sham": "شام",
    "subah": "صبح",
    "raat": "رات",
    "andhera": "اندھیرا",
    "roshni": "روشنی",
    "toofan": "طوفان",
    "baarish": "بارش",
    "aag": "آگ",
    "dushman": "دشمن",
    "dost": "دوست",
    "fauj": "فوج",
    "qareeb": "قریب",
    "dur": "دور",
    "dekha": "دیکھا",
    "kaha": "کہا",
    "bola": "بولا",
    "boli": "بولی",
    "chalo": "چلو",
    "ruko": "رکو",
    "hamla": "حملہ",
    "hifazat": "حفاظت",
    "watan": "وطن",
    "izzat": "عزت",
    "hosla": "حوصلہ",
    "himmat": "ہمت",
    "kahan": "کہاں",
    "yahan": "یہاں",
    "wahan": "وہاں",
    "aaj": "آج",
    "kal": "کل",
    "ek": "ایک",
    "do": "دو",
    "bohat": "بہت",
    "bahut": "بہت",
    "bhi": "بھی",
    "toh": "تو",
    "jo": "جو",
    "apni": "اپنی",
    "apna": "اپنا",
    "apne": "اپنے",
    "taraf": "طرف",
    "andar": "اندر",
    "bahar": "باہر",
    "upar": "اوپر",
    "neeche": "نیچے",
    "kadam": "قدم",
    "aage": "آگے",
    "peeche": "پیچھے",
    "tyaar": "تیار",
    "taiyar": "تیار",
    "fateh": "فتح",
    "tareekh": "تاریخ",
    "kahani": "کہانی",
    "shehar": "شہر",
    "mahal": "محل",
    "pahad": "پہاڑ",
    "jangal": "جنگل",
    "dariya": "دریا",
}

ROMAN_URDU_MARKERS = {
    "aur",
    "hai",
    "hain",
    "tha",
    "thi",
    "mein",
    "nahi",
    "nahin",
    "kya",
    "lekin",
    "magar",
    "qila",
    "qilay",
    "qile",
    "sipahi",
    "darwaza",
    "darwaze",
    "larai",
    "mukalma",
    "mehfooz",
    "sardar",
    "talwar",
    "dushman",
    "dekha",
    "kaha",
    "bola",
    "hum",
    "tum",
    "aap",
    "woh",
    "yeh",
    "ek",
    "ke",
    "ka",
    "ki",
}


def detect_script_language(text: str) -> str:
    """Detect primary language code: 'ur' (Urdu script), 'roman_ur' (Roman Urdu), or 'en' (English)."""
    cleaned = sanitize_story_text(text)
    if not cleaned.strip():
        return "en"

    urdu_chars = len(_URDU_ARABIC_RE.findall(cleaned))
    alpha_chars = sum(1 for ch in cleaned if ch.isalpha())
    if urdu_chars >= 8 and (alpha_chars == 0 or urdu_chars / max(alpha_chars, 1) > 0.2):
        return "ur"

    tokens = re.findall(r"[A-Za-z']+", cleaned.lower())
    if not tokens:
        return "en"
    marker_hits = sum(1 for tok in tokens if tok in ROMAN_URDU_MARKERS)
    if marker_hits >= 3 and (marker_hits / len(tokens)) >= 0.08:
        return "roman_ur"
    return "en"


def normalize_roman_urdu_for_tts(text: str) -> tuple[str, str]:
    """Convert Roman Urdu text into (urdu_script_approx, phonetic_latin) for local TTS engines.

    Words in ROMAN_URDU_LEXICON map directly to verified Urdu script for `espeak-ng -v ur`,
    while unknown proper nouns or loanwords receive phonetic syllable smoothing so speech synthesis
    pronounces them naturally without spelling letters aloud.
    """
    cleaned = sanitize_story_text(text).strip()
    if not cleaned:
        return ("", "")

    def _replace_word(match: re.Match[str]) -> str:
        word = match.group(0)
        low = word.lower()
        if low in ROMAN_URDU_LEXICON:
            return ROMAN_URDU_LEXICON[low]
        return word

    urdu_mixed = re.sub(r"[A-Za-z]+", _replace_word, cleaned)

    # Also build clean phonetic Latin fallback for English/Indic voice variants
    phonetic = cleaned
    phonetic_rules = [
        (r"\bphir\b", "fir"),
        (r"\bqila\b", "kila"),
        (r"\bqilay\b", "kilay"),
        (r"\bqareeb\b", "kareeb"),
        (r"\bkh", "kh"),
        (r"aa", "ah"),
        (r"ee", "ee"),
        (r"oo", "oo"),
    ]
    for pat, repl in phonetic_rules:
        phonetic = re.sub(pat, repl, phonetic, flags=re.IGNORECASE)

    return (urdu_mixed, phonetic)


_BASIC_SYLLABLE_URDU = [
    ("sh", "ش"),
    ("chh", "چھ"),
    ("ch", "چ"),
    ("kh", "خ"),
    ("gh", "غ"),
    ("ph", "پھ"),
    ("th", "تھ"),
    ("dh", "دھ"),
    ("bh", "بھ"),
    ("zh", "ژ"),
    ("aa", "ا"),
    ("ee", "ی"),
    ("oo", "و"),
    ("ai", "ے"),
    ("au", "و"),
    ("q", "ق"),
    ("k", "ک"),
    ("g", "گ"),
    ("j", "ج"),
    ("t", "ت"),
    ("d", "د"),
    ("r", "ر"),
    ("z", "ز"),
    ("s", "س"),
    ("f", "ف"),
    ("p", "پ"),
    ("b", "ب"),
    ("m", "م"),
    ("n", "ن"),
    ("l", "ل"),
    ("w", "و"),
    ("v", "و"),
    ("y", "ی"),
    ("h", "ہ"),
    ("a", "ا"),
    ("i", "ی"),
    ("u", "و"),
    ("e", "ے"),
    ("o", "و"),
]


def transliterate_roman_urdu_to_urdu(text: str) -> str:
    """Convert Roman Urdu subtitle text into readable Urdu (اردو) script."""
    cleaned = sanitize_story_text(text).strip()
    if not cleaned:
        return ""

    def _conv_token(match: re.Match[str]) -> str:
        word = match.group(0)
        low = word.lower()
        if low in ROMAN_URDU_LEXICON:
            return ROMAN_URDU_LEXICON[low]
        # Fallback phonetic character transliteration for out-of-lexicon Roman Urdu words
        idx = 0
        out: list[str] = []
        while idx < len(low):
            matched = False
            for lat, ur_ch in _BASIC_SYLLABLE_URDU:
                if low.startswith(lat, idx):
                    if idx == 0 and lat == "a":
                        out.append("ا")
                    else:
                        out.append(ur_ch)
                    idx += len(lat)
                    matched = True
                    break
            if not matched:
                out.append(low[idx])
                idx += 1
        return "".join(out)

    converted = re.sub(r"[A-Za-z]+", _conv_token, cleaned)
    converted = re.sub(r"\.(?=\s|$)", "۔", converted)
    converted = re.sub(r"\?(?=\s|$)", "؟", converted)
    return converted


SAMPLE_SCRIPTS: dict[str, dict[str, str]] = {
    "en_historical_fortress": {
        "title": "Guardians of the Crimson Fortress",
        "language": "en",
        "genre": "historical",
        "description": "A cinematic historical drama set at sunset on an ancient desert fortress rampart with dialogue and sword combat.",
        "script": (
            "SCENE 1: EXT. ANCIENT FORTRESS RAMPARTS - SUNSET\n"
            "Golden dust drifts across the sandstone battlements as torches flicker against the evening wind.\n"
            "Commander Tariq stands beside Scout Zara, holding an iron sword and gazing toward the desert horizon.\n"
            "TARIQ: (determined) Look beyond the dunes, Zara. Their vanguard moves beneath the rising dust storm.\n"
            "ZARA: (alert) The eastern gate holds strong, Commander, and the watchtowers are lit.\n\n"
            "SCENE 2: EXT. FORTRESS COURTYARD - NIGHT\n"
            "Smoke curls around stone pillars while General Kael steps forward in dark armor, drawing his blade.\n"
            "KAEL: (angry) Yield the citadel tonight, Tariq, or face our siege before dawn!\n"
            "TARIQ: (determined) These walls have protected our people for centuries. We stand our ground!\n"
            "Tariq clashes swords with Kael in fierce combat, dodging a heavy strike, blocking with his shield, and driving Kael back.\n\n"
            "SCENE 3: EXT. PALACE TERRACE - SUNRISE\n"
            "Morning light breaks over the ancient city domes as banners wave gently in the calm breeze.\n"
            "ZARA: (joyful) Dawn has arrived, Commander. The fortress remains unbroken.\n"
            "TARIQ: (calm) Courage kept these gates standing, Zara. Now the city wakes in peace."
        ),
    },
    "roman_ur_adventure": {
        "title": "Qilay Ki Hifazat (Roman Urdu)",
        "language": "roman_ur",
        "genre": "historical",
        "description": "Roman Urdu historical action story featuring Sardar Tariq and Sipahi Hamza defending a mountain fortress.",
        "script": (
            "SCENE 1: QILA KI DEEWAR - SHAM\n"
            "Sham ki surkh roshni mein purana qila aur registan nazar aa raha hai. Hawa mein gard ud rahi hai.\n"
            "TARIQ: (determined) Dekho Hamza, registan ke us taraf dushman fauj qareeb aa rahi hai.\n"
            "HAMZA: (brave) Hum taiyar hain Sardar! Qilay ki har deewar par mashal roshan hai.\n\n"
            "SCENE 2: MAIDAN E JANG - RAAT\n"
            "Raat ke andhere mein aag aur dhuan phail raha hai. Sardar Tariq talwar aur dhaal ke saath aage barhta hai.\n"
            "ZAFAR: (angry) Aaj yeh qila hamara hoga! Rasta chhor do!\n"
            "TARIQ: (determined) Jab tak hum mein himmat hai, koi is shehar ko nahi gira sakta!\n"
            "Tariq aur Zafar ke darmiyan tez talwar bazi aur muqabla hota hai. Tariq hamla rok kar jawabi waar karta hai.\n\n"
            "SCENE 3: QILA KA DARWAZA - SUBAH\n"
            "Subah ki roshni pahadon par chamak rahi hai aur aman wapas aa gaya hai.\n"
            "HAMZA: (joyful) Sardar, subah ho gayi aur hamara watan mehfooz hai!"
        ),
    },
    "ur_cinematic_story": {
        "title": "قدیم قلعے کی داستان (Urdu)",
        "language": "ur",
        "genre": "historical",
        "description": "اردو زبان میں ایک مختصر تاریخی اور سینیمیٹک کہانی۔",
        "script": (
            "منظر 1: قدیم قلعہ - شام\n"
            "سورج غروب ہو رہا ہے اور قدیم قلعے کی فصیل پر مشعلیں جل رہی ہیں۔\n"
            "طارق: دیکھو زارا، صحرا کی طرف سے طوفان اور دشمن کے لشکر کے آثار نظر آ رہے ہیں۔\n"
            "زارا: ہم پوری ہمت کے ساتھ قلعے کی حفاظت کے لیے تیار ہیں سردار۔\n\n"
            "منظر 2: میدانِ جنگ - رات\n"
            "رات کی تاریکی میں تلواروں کی ٹکر اور بہادری کا مقابلہ جاری ہے۔\n"
            "طارق: حوصلہ رکھو، سچائی اور ہمت کی ہمیشہ فتح ہوتی ہے!"
        ),
    },
    "qila_pehli_jung": {
        "title": "Qila Al-Noor — Pehli Jung",
        "language": "roman_ur",
        "genre": "historical",
        "description": "Short narrative Roman Urdu story: fortress guard patrol, intruder confrontation, dialogue, sword duel, and securing the gate.",
        "script": (
            "Ek purane qile ke darwaze par ek bahadur sipahi pehra de raha tha. "
            "Achanak dushman ka ek sipahi qile ke andar aane ki koshish karta hai. "
            "Dono ke darmiyan mukalma hota hai. "
            "Phir ek chhoti talwar ki larai hoti hai. "
            "Aakhir mein qile ka sipahi darwaza band kar deta hai aur qila mehfooz rehta hai."
        ),
    },
}
