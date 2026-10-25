"""Institution registry logic. M1 has only the name normalizer; search and the resolver are added in M2."""
import re

# Short forms people type -> full word. Applied after lower-casing and stripping punctuation.
ABBREVIATIONS = {"engg": "engineering", "clg": "college", "univ": "university", "inst": "institute"}
# Words that carry no meaning for matching.
FILLER_WORDS = {"the", "of", "and"}


def normalize_name(text: str) -> str:
    """'Orbelis Clg. of Technology' -> 'orbelis college technology' (same function is used for names and aliases)."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)  # punctuation -> space
    words = [ABBREVIATIONS.get(w, w) for w in t.split()]
    return " ".join(w for w in words if w not in FILLER_WORDS)
