"""Own BM25 retrieval over the plant care corpus, independent of Django."""

from .search import retrieve

__all__ = ["retrieve"]
