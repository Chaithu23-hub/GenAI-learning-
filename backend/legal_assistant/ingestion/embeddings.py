from functools import lru_cache

from .. import config

# [Embeddings & dense retrieval] [Word embeddings (Word2Vec / GloVe)]
# [Static vs contextual embeddings]
# We use a sentence-transformer bi-encoder for dense retrieval.
# The model is loaded once and cached for the process lifetime.


@lru_cache(maxsize=1)
def get_embedding_model():
    """Load and cache the sentence-transformer bi-encoder."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBEDDING_MODEL)


def embed(texts):
    """Encode a list of texts into normalized embedding vectors."""
    model = get_embedding_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text):
    """Encode a single query string into a normalized embedding vector."""
    return embed([text])[0]
