"""Text similarity for complaints (M6 baseline, no AI model): TF-IDF cosine blended with keyword overlap.

M12 blends in embeddings when they are switched on and loadable (see embeddings.py); this stays as the fallback. Steps: lowercase -> keep words -> drop filler words ->
map a few synonyms and strip plural endings -> weight rare words higher (TF-IDF) -> compare.
"""
import math
import re
from collections import Counter

from . import embeddings

STOP = set("""a an the and or but if of to in on at for from by with without about into after before during is are was
were be been being has have had not no this that these those it its they them their there here we our you your i my me he
she his her as so than then very also still please kindly request requests requested reporter says say said asks ask asked
new one two""".split())
# Different words that mean the same thing in a complaint (assumption, small and editable).
SYNONYMS = {"food": "meal", "meals": "meal", "mess": "meal", "canteen": "meal", "menu": "meal", "fees": "fee", "payment": "fee",
            "refund": "refund", "refundable": "refund", "deposit": "refund", "money": "refund", "returned": "refund",
            "lab": "laboratory", "labs": "laboratory", "equipment": "laboratory", "devices": "laboratory",
            "teachers": "faculty", "teacher": "faculty", "staff": "faculty", "lecturers": "faculty",
            "documents": "record", "document": "record", "documentation": "record", "records": "record",
            "papers": "record", "certificates": "record", "residents": "student", "students": "student",
            "investigate": "review", "return": "refund", "back": "refund", "pending": "delay", "delayed": "delay",
            "waiting": "delay", "withdrawal": "withdraw", "withdrew": "withdraw", "leaving": "withdraw", "left": "withdraw",
            "repeated": "repeat", "repeatedly": "repeat", "differed": "mismatch", "match": "mismatch", "stated": "published",
            "investigate": "review", "investigation": "review", "inspect": "review", "hostel": "hostel"}


def keywords(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]{3,}", (text or "").lower()):
        if w in STOP:
            continue
        w = SYNONYMS.get(w, w)
        for end in ("ing", "ed", "es", "s"):  # crude stemming, enough to match "meals"/"meal"
            if w.endswith(end) and len(w) - len(end) >= 4:
                w = w[: -len(end)]
                break
        out.append(SYNONYMS.get(w, w))
    return out


def build_idf(texts: list[str]) -> dict:
    """Rare words get a high weight, words in every complaint ('institution', 'hostel') a low one."""
    docs = [set(keywords(t)) for t in texts]
    n = len(docs) or 1
    df = Counter(w for d in docs for w in d)
    return {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}


def compare(text_a: str, text_b: str, idf: dict | None = None, vectors: dict | None = None) -> tuple[float, list[str]]:
    """Return (score 0..1, shared keywords). Keyword score = 0.6 * TF-IDF cosine + 0.4 * keyword overlap (Jaccard).
    With embedding `vectors` for both texts the score is half keyword score, half embedding similarity."""
    ka, kb = keywords(text_a), keywords(text_b)
    if not ka or not kb:
        return 0.0, []
    idf = idf or {}
    wa = {w: c * idf.get(w, 1.0) for w, c in Counter(ka).items()}
    wb = {w: c * idf.get(w, 1.0) for w, c in Counter(kb).items()}
    dot = sum(wa[w] * wb[w] for w in wa.keys() & wb.keys())
    cos = dot / (math.sqrt(sum(v * v for v in wa.values())) * math.sqrt(sum(v * v for v in wb.values())))
    sa, sb = set(ka), set(kb)
    jac = len(sa & sb) / len(sa | sb)
    score = 0.6 * cos + 0.4 * jac
    if vectors and text_a in vectors and text_b in vectors:
        score = 0.5 * score + 0.5 * embeddings.scaled(vectors[text_a], vectors[text_b])
    return round(score, 3), sorted(sa & sb)
