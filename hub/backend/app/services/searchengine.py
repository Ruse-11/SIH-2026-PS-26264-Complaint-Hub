"""Institution search engine (one engine for the hub dashboard and both portals).

Plain rules, no AI, built to stay fast on a slow server and a registry of many thousands of colleges:
  * An in-memory INDEX is built once (names, aliases, place words, initialisms) and reused for every search.
    It rebuilds by itself when colleges or aliases change (for example an officer's learned alias).
  * A search touches only the index: dictionary lookups, a sorted word list for "starts with", and rapidfuzz on a
    small set of similar-length words for typos. No database query per keystroke except two cheap COUNTs.
  * What it understands: partial words ("souther"), typos ("zenvra"), place names ("orbelis chennai"), AICTE IDs
    and INITIALS ("kip" = Kestora Institute of Pharmacy). Every typed word must match something.
  * It is never empty when a good guess exists: if nothing matches every word, it shows colleges matching some
    of the words, then the closest names. These weaker answers are labelled by `tier`.
Tiers: "match" (every word matched), "partial" (some words), "closest" (spelling-level guess).
"""
import bisect
import threading
from collections import defaultdict

from rapidfuzz import fuzz, process
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .institutions import FILLER_WORDS, GENERIC_WORDS, WORD_MATCH, card, normalize_name

# scores on a 0-100 scale
S_EXACT, S_PREFIX, S_SUBSTRING, S_TYPO = 100, 92, 70, 62
S_INITIALS, S_INITIALS_PREFIX = 90, 78
S_ID = 95
W_NAME, W_ALIAS, W_PLACE = 1.0, 0.9, 0.8      # a word in the name counts more than in an alias, more than in the place
BONUS_NAME_START, BONUS_ALIAS_START = 8, 6
CLOSEST_CUTOFF = 70                           # a spelling-level guess below this is not worth showing
SMALL_REGISTRY = 500                          # at or below this size the resolver may scan every college

_lock = threading.Lock()
_cache: dict = {}


class Index:
    """Everything a search needs, built once from the database."""

    def __init__(self, db: Session):
        insts = sorted(db.scalars(select(m.Institution)).all(), key=lambda i: i.aicte_id)
        by_id = {i.aicte_id: i for i in insts}
        aliases = defaultdict(list)
        for iid, a in db.execute(select(m.InstitutionAlias.institution_id, m.InstitutionAlias.alias_normalized)):
            aliases[iid].append(a)
        kids = defaultdict(int)
        for i in insts:
            if i.parent_id:
                kids[i.parent_id] += 1
        self.ids = [i.aicte_id for i in insts]
        self.idx = {iid: n for n, iid in enumerate(self.ids)}
        self.upper_ids = [iid.upper() for iid in self.ids]
        self.name_norm = [i.name_normalized for i in insts]
        self.aliases = [aliases.get(i.aicte_id, []) for i in insts]
        self.place = [normalize_name(f"{i.area or ''} {i.district or ''} {i.state or ''}").split() for i in insts]
        self.cards = []
        for i in insts:
            c = card(i, by_id[i.parent_id].official_name if i.parent_id else None, 0, "")
            c["colleges"] = kids.get(i.aicte_id, 0)  # > 0: a university with that many constituent colleges
            self.cards.append(c)
        # word -> {institution number: weight}
        self.postings: dict[str, dict[int, float]] = defaultdict(dict)
        for n in range(len(insts)):
            for words, weight in ((self.name_norm[n].split(), W_NAME), (self._alias_words(n), W_ALIAS), (self.place[n], W_PLACE)):
                for w in words:
                    if self.postings[w].get(n, 0) < weight:
                        self.postings[w][n] = weight
        self.vocab = sorted(self.postings)
        self.by_len: dict[int, list[str]] = defaultdict(list)
        for w in self.vocab:
            self.by_len[len(w)].append(w)
        # initialisms: "kestora institute pharmacy" -> "kip" (all words) and the same without generic words
        self.acronyms: dict[str, set[int]] = defaultdict(set)
        for n, name in enumerate(self.name_norm):
            words = name.split()
            if len(words) >= 2:
                self.acronyms["".join(w[0] for w in words)].add(n)
            core = [w for w in words if w not in GENERIC_WORDS and not w.isdigit()]
            if len(core) >= 2 and core != words:
                self.acronyms["".join(w[0] for w in core)].add(n)
        self.acr_sorted = sorted(self.acronyms)
        # every name and alias as one string, for the last-resort spelling guess
        self.strings: list[str] = []
        self.string_owner: list[int] = []
        for n in range(len(insts)):
            for s in [self.name_norm[n]] + self.aliases[n]:
                self.strings.append(s)
                self.string_owner.append(n)

    def _alias_words(self, n):
        return [w for a in self.aliases[n] for w in a.split()]

    def __len__(self):
        return len(self.ids)

    # ---- one typed word -> {institution number: score} ----
    def token_matches(self, t: str) -> dict[int, float]:
        out: dict[int, float] = {}

        def put(n, s):
            if s > out.get(n, 0):
                out[n] = s

        def hit(word, s):
            for n, weight in self.postings[word].items():
                put(n, s * weight)

        lo = bisect.bisect_left(self.vocab, t)
        for w in self.vocab[lo:lo + 5000]:  # words that start with the typed text (sorted list -> contiguous)
            if not w.startswith(t):
                break
            hit(w, S_EXACT if w == t else S_PREFIX)
        if len(t) >= 3:  # the typed text inside a word
            for w in self.vocab:
                if t in w and not w.startswith(t):
                    hit(w, S_SUBSTRING)
        if len(t) >= 4:  # a typo: only words of similar length are compared
            for length in range(len(t) - 2, len(t) + 3):
                for w, score, _ in process.extract(t, self.by_len.get(length, []), scorer=fuzz.ratio, score_cutoff=WORD_MATCH, limit=None):
                    if w != t and not w.startswith(t):
                        hit(w, S_TYPO)
        if len(t) >= 2:  # initials
            for a in self.acr_sorted[bisect.bisect_left(self.acr_sorted, t):]:
                if not a.startswith(t):
                    break
                for n in self.acronyms[a]:
                    put(n, S_INITIALS if a == t else S_INITIALS_PREFIX)
        return out

    def candidates(self, normalized: str) -> set[int]:
        """Colleges that match at least one typed word (used by the strict resolver to avoid scanning everything)."""
        if len(self) <= SMALL_REGISTRY:
            return set(range(len(self)))
        found: set[int] = set()
        for t in normalized.split():
            found |= set(self.token_matches(t))
        return found


def _signature(db: Session):
    bind = db.get_bind()
    n_inst = db.scalar(select(func.count()).select_from(m.Institution))
    n_alias, last_alias = db.execute(select(func.count(), func.max(m.InstitutionAlias.id))).one()
    return (str(bind.url), n_inst, n_alias, last_alias)


def get_index(db: Session) -> Index:
    """The shared index; rebuilt when the number of colleges or aliases changes."""
    sig = _signature(db)
    hit = _cache.get("index")
    if hit and hit[0] == sig:
        return hit[1]
    with _lock:
        hit = _cache.get("index")
        if hit and hit[0] == sig:
            return hit[1]
        index = Index(db)
        _cache["index"] = (sig, index)
        return index


def reset_cache():
    _cache.clear()


def _result(ix: Index, n: int, score: float, tier: str) -> dict:
    c = dict(ix.cards[n])
    c["score"] = round(score, 1)
    c["match"] = "SUGGEST" if tier == "match" else "CLOSEST"
    c["tier"] = tier
    return c


def find(db: Session, query: str, limit: int = 8) -> list[dict]:
    """Best colleges for the typed text, best first. See the module note for the three tiers."""
    q = (query or "").strip()
    qn = normalize_name(q)
    if len(q) < 2 or not qn:
        return []
    ix = get_index(db)
    if not len(ix):
        return []
    tokens = qn.split()
    per_token = [ix.token_matches(t) for t in tokens]

    scored: dict[int, float] = {}
    q_upper = q.upper()
    for n, uid in enumerate(ix.upper_ids):  # a typed part of an AICTE ID
        if q_upper in uid:
            scored[n] = S_ID
    if all(per_token):  # tier 1: every typed word matched something
        common = set.intersection(*(set(p) for p in per_token))
        for n in common:
            score = sum(p[n] for p in per_token) / len(tokens)
            if ix.name_norm[n].startswith(qn):
                score += BONUS_NAME_START
            elif any(a.startswith(qn) for a in ix.aliases[n]):
                score += BONUS_ALIAS_START
            scored[n] = max(scored.get(n, 0), score)
    if scored:
        order = sorted(scored.items(), key=lambda x: (-x[1], ix.cards[x[0]]["official_name"]))
        return [_result(ix, n, s, "match") for n, s in order[:limit]]

    # tier 2: colleges matching some of the typed words (a word they got wrong, or an extra word)
    partial: dict[int, float] = defaultdict(float)
    for t, p in zip(tokens, per_token):
        if t in GENERIC_WORDS:
            continue  # "college" alone says nothing about which college
        for n, s in p.items():
            partial[n] += s / len(tokens)
    if partial:
        order = sorted(partial.items(), key=lambda x: (-x[1], ix.cards[x[0]]["official_name"]))
        return [_result(ix, n, s, "partial") for n, s in order[:limit]]

    # tier 3: the closest names by spelling
    core = " ".join(t for t in tokens if t not in GENERIC_WORDS)
    if not core:
        return []
    best: dict[int, float] = {}
    for _, score, pos in process.extract(core, ix.strings, scorer=fuzz.WRatio, score_cutoff=CLOSEST_CUTOFF, limit=limit * 3):
        n = ix.string_owner[pos]
        best[n] = max(best.get(n, 0), score)
    order = sorted(best.items(), key=lambda x: (-x[1], ix.cards[x[0]]["official_name"]))
    return [_result(ix, n, s, "closest") for n, s in order[:limit]]
