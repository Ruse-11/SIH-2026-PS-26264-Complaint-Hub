"""Optional local text embeddings (M12). No external API, no GPU, nothing leaves the machine.

Off by default. Turn on with the environment variable  HUB_EMBEDDINGS=on  (needs `pip install fastembed==0.5.1`; the small
model, about 130 MB, downloads once on first use). If the package or the model cannot be loaded, or anything fails
while embedding, the hub quietly stays on the TF-IDF similarity from M6, so matching never stops working.
"""
import logging
import math
import os

log = logging.getLogger("hub.embeddings")

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# Raw cosine between unrelated complaints is already about 0.5 with this model, so stretch 0.5..1 onto 0..1
# before blending (an assumption, tune it on the synthetic data together with T_A / T_B).
COSINE_FLOOR = 0.5

_state = {"model": None, "tried": False, "error": "", "cache": {}}


def requested() -> bool:
    return os.getenv("HUB_EMBEDDINGS", "off").strip().lower() in ("on", "1", "true", "yes")


def _load():
    """Load the model once. Returns it, or None (reason kept in status)."""
    if _state["tried"]:
        return _state["model"]
    _state["tried"] = True
    try:
        from fastembed import TextEmbedding  # imported here so the hub starts without the package
        _state["model"] = TextEmbedding(MODEL_NAME)
    except Exception as e:  # noqa: BLE001 - any failure means "use TF-IDF"
        _state["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        log.warning("Embeddings unavailable, using TF-IDF: %s", _state["error"])
    return _state["model"]


def embed_many(texts: list[str]) -> dict[str, list[float]] | None:
    """Vectors for the given texts (cached), or None when embeddings are off or unavailable."""
    if not requested():
        return None
    model = _load()
    if model is None:
        return None
    cache = _state["cache"]
    todo = sorted({t for t in texts if t not in cache})
    if todo:
        try:
            for t, v in zip(todo, model.embed(todo)):
                cache[t] = [float(x) for x in v]
        except Exception as e:  # noqa: BLE001
            _state["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            _state["model"] = None
            log.warning("Embedding failed, using TF-IDF: %s", _state["error"])
            return None
    return {t: cache[t] for t in texts if t in cache}


def warm_up():
    """Load the model at hub start so /api/health tells the truth straight away. Never raises."""
    embed_many(["warm up"])


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def scaled(a: list[float], b: list[float]) -> float:
    """Cosine stretched so 'unrelated' is about 0 and 'same meaning' about 1."""
    return max(0.0, min(1.0, (cosine(a, b) - COSINE_FLOOR) / (1 - COSINE_FLOOR)))


def status() -> dict:
    """What the hub is using right now (does not load the model)."""
    if not requested():
        return {"similarity": "tfidf", "embeddings": "off", "detail": "HUB_EMBEDDINGS is not set to on"}
    if _state["model"] is not None:
        return {"similarity": "embeddings", "embeddings": "active", "detail": MODEL_NAME}
    if _state["tried"]:
        return {"similarity": "tfidf", "embeddings": "unavailable", "detail": _state["error"] or "model could not be loaded"}
    return {"similarity": "tfidf", "embeddings": "on-not-loaded-yet", "detail": "loads on the first comparison"}


def reset_for_tests():
    _state.update({"model": None, "tried": False, "error": "", "cache": {}})
