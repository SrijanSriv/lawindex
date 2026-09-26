"""Vector index over admitted whole-section passages, bound to one model and one corpus.

LawIndex ships no embedding model. An index is built by passing an `embed`
function to `build`; the caller names the model. A loaded index is refused
unless its model, passage strategy and corpus fingerprint all match the live
snapshot, so vectors from different models or corpora are never mixed.
Vectors are derived data: they rank admitted records and never admit text.
"""
from __future__ import annotations

from array import array
import base64
from dataclasses import dataclass
import hashlib
import json
import math
from operator import mul
from pathlib import Path
import sys

from .benchmark import corpus_fingerprint
from .retrieval import Candidate

FORMAT = "lawindex-vectors-v1"
PASSAGE_STRATEGY = "whole-section-v1"


class IndexMismatch(ValueError):
    """The index was built for another model, passage strategy or corpus."""


def embedding_text(record: dict) -> str:
    """Text given to the model. Title and heading are context for the vector
    only; the displayed text is always the record's own body."""
    return "\n".join((record["act_title"], record["heading"], record["body_text"]))


def text_digest(record: dict) -> str:
    return hashlib.sha256(embedding_text(record).encode()).hexdigest()


def _unit(values, where: str) -> array:
    vector = array("f", values)
    if not all(math.isfinite(v) for v in vector):
        raise ValueError(f"{where}: vector has a non-finite value")
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise ValueError(f"{where}: vector is all zeros")
    return array("f", (v / norm for v in vector))


@dataclass(frozen=True)
class VectorIndex:
    model: str
    dim: int
    corpus_fingerprint: str
    vectors: dict  # key -> unit-length array("f")
    digests: dict  # key -> text_digest of what was embedded
    passage_strategy: str = PASSAGE_STRATEGY


def build(records: dict, embed, model: str, *, previous: VectorIndex | None = None,
          batch_size: int = 32, on_batch=None) -> VectorIndex:
    """Embed every record, reusing `previous` vectors whose model and text are unchanged.

    `embed(texts)` returns one vector per text. `on_batch(partial_index)` is
    called after each batch so a long build can save progress and resume by
    passing the saved partial index back as `previous`.
    """
    if not model or not isinstance(model, str):
        raise ValueError("model must name the embedding model and version")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    fingerprint = corpus_fingerprint(records)
    reusable = previous if previous is not None and previous.model == model \
        and previous.passage_strategy == PASSAGE_STRATEGY else None
    vectors, digests, todo = {}, {}, []
    for key in sorted(records):
        digest = text_digest(records[key])
        if reusable is not None and reusable.digests.get(key) == digest:
            vectors[key], digests[key] = reusable.vectors[key], digest
        else:
            todo.append((key, digest))
    dim = reusable.dim if reusable is not None and vectors else None
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        output = list(embed([embedding_text(records[key]) for key, _ in batch]))
        if len(output) != len(batch):
            raise ValueError(f"embed returned {len(output)} vectors for {len(batch)} texts")
        for (key, digest), values in zip(batch, output):
            vector = _unit(values, key)
            if dim is None:
                dim = len(vector)
            if len(vector) != dim:
                raise ValueError(f"{key}: vector has {len(vector)} dimensions, expected {dim}")
            vectors[key], digests[key] = vector, digest
        if on_batch is not None:
            on_batch(VectorIndex(model, dim, fingerprint, dict(vectors), dict(digests)))
    if dim is None:
        raise ValueError("no records to embed")
    return VectorIndex(model, dim, fingerprint, vectors, digests)


def check(index: VectorIndex, records: dict, model: str) -> None:
    """Refuse an index that does not belong to this model and this exact corpus."""
    if index.model != model:
        raise IndexMismatch(f"index was built with {index.model!r}, not {model!r}")
    if index.passage_strategy != PASSAGE_STRATEGY:
        raise IndexMismatch(f"index uses passage strategy {index.passage_strategy!r}")
    if index.corpus_fingerprint != corpus_fingerprint(records) or set(index.vectors) != set(records):
        raise IndexMismatch("index was built for a different corpus; rebuild it")
    stale = [key for key in sorted(records) if index.digests.get(key) != text_digest(records[key])]
    if stale:
        raise IndexMismatch(f"{len(stale)} records changed since the index was built, e.g. {stale[0]}")


def search(index: VectorIndex, query_vector, eligible, k: int) -> list[Candidate]:
    """The k eligible keys most similar to the query, by cosine similarity, ties by key."""
    if len(query_vector) != index.dim:
        raise IndexMismatch(f"query vector has {len(query_vector)} dimensions, index has {index.dim}")
    query = _unit(query_vector, "query")
    scored = [(-round(sum(map(mul, query, index.vectors[key])), 6), key)
              for key in eligible if key in index.vectors]
    scored.sort()
    return [Candidate(key, -negated) for negated, key in scored[:k]]


def save(index: VectorIndex, path: Path) -> None:
    """One JSON file: the manifest, then each vector as little-endian float32, base64."""
    def encode(vector):
        data = array("f", vector)
        if sys.byteorder != "little":
            data.byteswap()
        return base64.b64encode(data.tobytes()).decode()

    payload = {"format": FORMAT, "model": index.model, "dim": index.dim,
               "passage_strategy": index.passage_strategy,
               "corpus_fingerprint": index.corpus_fingerprint,
               "records": {key: {"digest": index.digests[key], "vector": encode(index.vectors[key])}
                           for key in sorted(index.vectors)}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    temporary.replace(path)


def load(path: Path) -> VectorIndex:
    payload = json.loads(Path(path).read_text())
    if payload.get("format") != FORMAT:
        raise IndexMismatch(f"{path}: not a {FORMAT} file")
    dim = payload["dim"]
    vectors, digests = {}, {}
    for key, entry in payload["records"].items():
        data = array("f")
        data.frombytes(base64.b64decode(entry["vector"]))
        if sys.byteorder != "little":
            data.byteswap()
        if len(data) != dim:
            raise IndexMismatch(f"{path}: {key} has {len(data)} dimensions, expected {dim}")
        vectors[key], digests[key] = data, entry["digest"]
    return VectorIndex(payload["model"], dim, payload["corpus_fingerprint"], vectors, digests,
                       payload["passage_strategy"])
