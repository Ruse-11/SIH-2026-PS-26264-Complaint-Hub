"""Institution registry logic: name normalizer, resolver (search), guided filters, profile.

The resolver is rules + fuzzy string matching, no AI (CLAUDE.md section 6). It NEVER guesses:
it returns one suggestion only when it is clearly the winner, otherwise a short list or nothing.
"""
import re

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m

# ---- normalizing ----
# Short forms people type -> full word. Applied after lower-casing and stripping punctuation.
ABBREVIATIONS = {"engg": "engineering", "clg": "college", "univ": "university", "inst": "institute"}
# Words that carry no meaning for matching.
FILLER_WORDS = {"the", "of", "and"}
# Words that only say WHAT KIND of institution it is. They never identify one by themselves, so
# "Unlisted Fictional Technical College" must not match every college just because of "college".
GENERIC_WORDS = {
    "college", "institute", "institution", "school", "university", "academy", "technology", "technical",
    "engineering", "management", "pharmacy", "architecture", "applied", "sciences", "science", "studies",
    "polytechnic", "campus", "main", "city",
}

# ---- tuning numbers (0-100 scale), tested against data/institution_name_tests.csv ----
WORD_MATCH = 82      # two distinctive words count as "the same word" at this similarity (allows typos)
NOT_LISTED_BELOW = 70  # best score under this -> nothing is suggested
CLEAR_WINNER = 85    # best score at least this AND ahead of the runner-up -> one suggestion
LEAD_NEEDED = 6      # how far ahead of the runner-up the winner must be
MAX_SHOWN = 3        # "show top 3, never auto-pick"
LOCATION_BONUS = 4   # per query word that matches the college's district/area/state (max 2 words)


def normalize_name(text: str) -> str:
    """'Orbelis Clg. of Technology' -> 'orbelis college technology' (same function is used for names and aliases)."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)  # punctuation -> space
    words = [ABBREVIATIONS.get(w, w) for w in t.split()]
    return " ".join(w for w in words if w not in FILLER_WORDS)


def _distinctive(tokens):
    """The words that actually identify a college (not generic, not just a number)."""
    return [t for t in tokens if t not in GENERIC_WORDS and not t.isdigit()]


# ---- cards shown to the reporter / officer ----
def card(inst: m.Institution, parent_name, score, match) -> dict:
    return {
        "aicte_id": inst.aicte_id, "official_name": inst.official_name, "address_line": inst.address_line,
        "area": inst.area, "district": inst.district, "state": inst.state, "pincode": inst.pincode,
        "region": inst.region, "type": inst.type, "lat": inst.lat, "lng": inst.lng, "programs": inst.programs,
        "parent_id": inst.parent_id, "parent_name": parent_name, "score": round(score, 1), "match": match,
    }


def _cards(db: Session, ids, score, match):
    """Build cards for a list of institution ids, keeping the given order."""
    by_id = {i.aicte_id: i for i in db.scalars(select(m.Institution))}
    return [card(by_id[i], by_id[by_id[i].parent_id].official_name if by_id[i].parent_id else None, score, match)
            for i in ids]


def _expand_parents(db: Session, ids):
    """A parent university is never offered as the answer: it is replaced by its constituent colleges."""
    out = []
    for i in ids:
        kids = db.scalars(select(m.Institution.aicte_id).where(m.Institution.parent_id == i)
                          .order_by(m.Institution.aicte_id)).all()
        for x in (kids or [i]):
            if x not in out:
                out.append(x)
    return out


def _answer(query, normalized, outcome, match_type, reason, candidates):
    return {"query": query, "normalized": normalized, "outcome": outcome, "match_type": match_type,
            "reason": reason, "candidates": candidates}


# ---- the resolver ----
def resolve(db: Session, query: str) -> dict:
    """Decide what a typed name means. outcome: RESOLVED (one suggestion), AMBIGUOUS (up to 3) or NOT_LISTED."""
    q = (query or "").strip()
    qn = normalize_name(q)
    if not qn:
        return _answer(query, qn, "NOT_LISTED", "NONE", "Nothing to search for.", [])

    # 1. An AICTE ID typed exactly.
    inst = db.get(m.Institution, q.upper())
    if inst:
        return _answer(query, qn, "RESOLVED", "ID", "Exact institution ID.", _cards(db, [inst.aicte_id], 100, "ID"))

    # 2. Exact official name or exact alias (after normalizing both sides).
    by_name = db.scalars(select(m.Institution.aicte_id).where(m.Institution.name_normalized == qn)).all()
    by_alias = db.scalars(select(m.InstitutionAlias.institution_id)
                          .where(m.InstitutionAlias.alias_normalized == qn)).all()
    exact = list(dict.fromkeys(by_name + by_alias))
    if exact:
        match_type = "NAME" if by_name else "ALIAS"
        ids = _expand_parents(db, exact)
        if len(ids) == 1:
            return _answer(query, qn, "RESOLVED", match_type, "Exact match.", _cards(db, ids, 100, match_type))
        why = ("This is a university with several constituent colleges." if any(i not in exact for i in ids)
               else "This name or short form belongs to more than one institution.")
        return _answer(query, qn, "AMBIGUOUS", match_type, why + " Please pick one.",
                       _cards(db, ids[:MAX_SHOWN], 100, match_type))

    # 3. Fuzzy match against official names and aliases.
    institutions = db.scalars(select(m.Institution)).all()
    aliases = {}
    for iid, a in db.execute(select(m.InstitutionAlias.institution_id, m.InstitutionAlias.alias_normalized)):
        aliases.setdefault(iid, []).append(a)

    q_tokens = qn.split()
    scored = []
    for inst in institutions:
        texts = [inst.name_normalized] + aliases.get(inst.aicte_id, [])
        # Words in the query that name the college's place (district, area, state) are evidence of place, not name.
        place = set(_distinctive(normalize_name(f"{inst.area or ''} {inst.district or ''} {inst.state or ''}").split()))
        name_tokens = [t for t in q_tokens if t not in place]
        place_hits = len(q_tokens) - len(name_tokens)
        # Gate: at least one identifying word of the query must (nearly) match an identifying word of this college.
        q_words = _distinctive(name_tokens)
        c_words = {w for t in texts for w in _distinctive(t.split())}
        # (a word of 3+ letters that starts a college's word also counts, so live typing "zenv" finds Zenvora)
        if not any(fuzz.ratio(a, b) >= WORD_MATCH or (len(a) >= 3 and b.startswith(a)) for a in q_words for b in c_words):
            continue
        base = max(fuzz.WRatio(" ".join(name_tokens), t) for t in texts)
        scored.append((min(100.0, base + LOCATION_BONUS * min(place_hits, 2)), inst.aicte_id))

    scored.sort(key=lambda s: (-s[0], s[1]))
    if not scored or scored[0][0] < NOT_LISTED_BELOW:
        return _answer(query, qn, "NOT_LISTED", "NONE", "No institution in the registry matches this name.", [])

    top = scored[0][0]
    runner_up = scored[1][0] if len(scored) > 1 else 0
    ids = _expand_parents(db, [i for _, i in scored[:1]])
    if top >= CLEAR_WINNER and top - runner_up >= LEAD_NEEDED and len(ids) == 1:
        return _answer(query, qn, "RESOLVED", "FUZZY", "Clearly the closest name.", _cards(db, ids, top, "FUZZY"))

    # Not clear: show the closest few (parents replaced by their colleges), never pick for the reporter.
    shortlist = _expand_parents(db, [i for s, i in scored if s >= max(NOT_LISTED_BELOW, top - 15)])[:MAX_SHOWN]
    score_of = {i: s for s, i in scored}
    cards = _cards(db, shortlist, top, "FUZZY")
    for c in cards:
        c["score"] = round(score_of.get(c["aicte_id"], top), 1)
    return _answer(query, qn, "AMBIGUOUS", "FUZZY", "Several close matches. Please pick one.", cards)


# ---- guided questions (state -> district -> type -> area -> programs): plain filtering ----
def _programs(inst):
    return [p.strip() for p in (inst.programs or "").split(";") if p.strip()]


def guided_filters(db: Session, state=None, district=None, type=None, area=None, program=None) -> dict:
    """Narrow the registry by the answers so far.

    Returns the matching colleges and, for each question, the choices that are still possible. The choices for a
    question ignore that question's own answer, so the reporter can switch from one state to another directly.
    """
    rows = db.scalars(select(m.Institution).order_by(m.Institution.aicte_id)).all()
    answers = {"state": state, "district": district, "type": type, "area": area, "program": program}

    def fits(inst, skip=None):  # does the college fit every answer except the one named in `skip`?
        values = {"state": inst.state, "district": inst.district, "type": inst.type, "area": inst.area}
        return all(a is None or a == "" or k == skip or (a in _programs(inst) if k == "program" else values[k] == a)
                   for k, a in answers.items())

    def choices(skip, getter):
        return sorted({v for i in rows if fits(i, skip) for v in getter(i) if v})

    picked = [i for i in rows if fits(i)]
    facets = {
        "states": choices("state", lambda i: [i.state]), "districts": choices("district", lambda i: [i.district]),
        "types": choices("type", lambda i: [i.type]), "areas": choices("area", lambda i: [i.area]),
        "programs": choices("program", _programs),
    }
    names = {i.aicte_id: i.official_name for i in rows}
    return {"count": len(picked), "facets": facets,
            "candidates": [card(i, names.get(i.parent_id), 0, "FILTER") for i in picked[:20]]}


# ---- profile ----
def profile(db: Session, aicte_id: str):
    """Institution details + its parent/children + case counts. (The full case history is added in M8.)"""
    inst = db.get(m.Institution, aicte_id)
    if not inst:
        return None
    parent = db.get(m.Institution, inst.parent_id) if inst.parent_id else None
    children = db.scalars(select(m.Institution).where(m.Institution.parent_id == aicte_id)
                          .order_by(m.Institution.aicte_id)).all()
    by_status = dict(db.execute(select(m.Case.status, func.count()).where(m.Case.institution_id == aicte_id)
                                .group_by(m.Case.status)).all())
    by_bureau = dict(db.execute(select(m.Case.assigned_bureau, func.count()).where(m.Case.institution_id == aicte_id)
                                .group_by(m.Case.assigned_bureau)).all())
    data = card(inst, parent.official_name if parent else None, 0, "PROFILE")
    data.pop("score"), data.pop("match")
    data["established_year"] = inst.established_year
    data["children"] = [{"aicte_id": c.aicte_id, "official_name": c.official_name} for c in children]
    data["cases"] = {"total": sum(by_status.values()), "by_status": by_status, "by_bureau": by_bureau}
    return data


def history(db: Session, user, aicte_id: str):
    """Profile + the complaint history of one institution, as far as `user` may see it (M8)."""
    from . import alerts as alert_service, cases as case_service, matching, scope  # local import: avoids a circular import
    data = profile(db, aicte_id)
    if data is None:
        return None
    visible = scope.visible_case_ids(db, user)
    data["cases"] = case_service.list_cases(db, user, institution_id=aicte_id, sort="oldest", page_size=100)["items"]
    data["links"] = matching.list_links(db, institution_id=aicte_id, visible=visible)
    data["alerts"] = alert_service.list_alerts(db, institution_id=aicte_id, visible=visible)
    return data
