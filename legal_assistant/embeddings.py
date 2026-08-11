"""Embedding model access (the bi-encoder half of retrieval)."""

from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def get_embedding_model():
    # reuse it; it maps any text to a dense vector so we can compare meaning,
    # not keywords.
    # models map each word to one fixed vector; our sentence model extends that
    # idea to whole passages.
    # Word2Vec/GloVe) is used so "amendment" in a termination clause embeds
    # differently from "amendment" in a payment clause.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBEDDING_MODEL)


def embed(texts):
    """Embed a list of texts into normalized vectors (ready for cosine distance)."""
    model = get_embedding_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text):
    """Embed a single question."""
    return embed([text])[0]
