"""Local embedding model for Phase 5 experiments: BAAI/bge-small-en-v1.5.

Needs `sentence-transformers` from the project's `.venv/`; the import happens
only when an embedder is created, so search and the tests run without it.
The model is loaded from the local Hugging Face cache and never re-fetched
once cached (the download was a recorded one-time exception; see
docs/phase-5/PLAN.md).
"""
from __future__ import annotations

from pathlib import Path

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge models expect this instruction before a query, and nothing before a passage.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, allow_download: bool = False):
        import os
        if not allow_download:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(MODEL_NAME, device="cpu")
        self.revision = _cached_revision()
        self.model_id = f"{MODEL_NAME}@{self.revision}"

    def passages(self, texts):
        return self._model.encode(list(texts), batch_size=32, normalize_embeddings=True,
                                  convert_to_numpy=True).tolist()

    def query(self, text: str):
        return self._model.encode([QUERY_INSTRUCTION + text], normalize_embeddings=True,
                                  convert_to_numpy=True)[0].tolist()


def _cached_revision() -> str:
    """The commit of the cached snapshot, so a run names the exact weights it used."""
    from huggingface_hub import scan_cache_dir
    for repo in scan_cache_dir().repos:
        if repo.repo_id == MODEL_NAME:
            revisions = sorted(repo.revisions, key=lambda r: r.last_modified)
            if revisions:
                return revisions[-1].commit_hash
    raise RuntimeError(f"{MODEL_NAME} is not in the local cache")


def default_index_path(root: Path) -> Path:
    return Path(root) / "data/index/vectors-bge-small-en-v1.5.json"


class VectorBackend:
    """A loaded model and its index, kept for the life of a process (loading the
    model takes seconds). Every request still re-checks the index against the
    live snapshot before it is used."""

    def __init__(self, index, query_vector, model: str):
        self.index, self.query_vector, self.model = index, query_vector, model

    @classmethod
    def load(cls, root: Path, index_path: Path | None = None):
        from . import vectors
        embedder = Embedder()
        return cls(vectors.load(index_path or default_index_path(root)), embedder.query, embedder.model_id)
