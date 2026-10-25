"""
Speaker Index Management module for Pinecone.
Handles dedicated Pinecone index creation, validation, embedding upserts,
and similarity queries for registered speaker identification.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec

try:
    import dotenv
    _base_dir = Path(__file__).resolve().parent.parent
    dotenv.load_dotenv(_base_dir / '.env')
    dotenv.load_dotenv(_base_dir.parent / '.env')
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Constants & Defaults
DEFAULT_INDEX_NAME = "meeting-speakers"
DEFAULT_NAMESPACE = "company_speakers"
EMBEDDING_DIMENSION = 256
SIMILARITY_METRIC = "cosine"
DEFAULT_CLOUD = "aws"
DEFAULT_REGION = "us-east-1"

_pinecone_client = None
_speaker_index = None


def get_pinecone_config() -> Dict[str, Any]:
    """Retrieves Pinecone configuration from environment variables."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError(
            "PINECONE_API_KEY is not configured. Please set PINECONE_API_KEY in your environment or .env file."
        )

    index_name = os.getenv("PINECONE_SPEAKER_INDEX", DEFAULT_INDEX_NAME).strip()
    namespace = os.getenv("PINECONE_SPEAKER_NAMESPACE", DEFAULT_NAMESPACE).strip()
    cloud = os.getenv("PINECONE_CLOUD", DEFAULT_CLOUD).strip()
    region = os.getenv("PINECONE_REGION", DEFAULT_REGION).strip()

    return {
        "api_key": api_key,
        "index_name": index_name,
        "namespace": namespace,
        "cloud": cloud,
        "region": region,
        "dimension": EMBEDDING_DIMENSION,
        "metric": SIMILARITY_METRIC,
    }


def get_pinecone_client() -> Pinecone:
    """Returns singleton Pinecone client instance."""
    global _pinecone_client
    if _pinecone_client is None:
        cfg = get_pinecone_config()
        try:
            _pinecone_client = Pinecone(api_key=cfg["api_key"])
        except Exception as exc:
            logger.error(f"[PINECONE] Failed to initialize Pinecone client: {exc}")
            raise ConnectionError(f"Failed to connect to Pinecone: {exc}") from exc
    return _pinecone_client


def get_or_create_speaker_index(create_if_missing: bool = True):
    """
    Validates or creates the dedicated speaker embedding index.
    Ensures dimensions and metric match expected values.
    Never deletes or overwrites existing index data.
    """
    global _speaker_index
    if _speaker_index is not None:
        return _speaker_index

    client = get_pinecone_client()
    cfg = get_pinecone_config()
    target_name = cfg["index_name"]

    try:
        existing_indexes = client.list_indexes()
        existing_names = [idx.name for idx in existing_indexes]
    except Exception as exc:
        logger.error(f"[PINECONE] Error listing indexes: {exc}")
        raise ConnectionError(f"Could not retrieve Pinecone index list: {exc}") from exc

    if target_name not in existing_names:
        if not create_if_missing:
            raise FileNotFoundError(
                f"Pinecone index '{target_name}' does not exist and create_if_missing is False."
            )

        logger.info(
            f"[PINECONE] Creating new dedicated speaker index: '{target_name}' "
            f"(dim={cfg['dimension']}, metric={cfg['metric']}, cloud={cfg['cloud']}, region={cfg['region']})..."
        )
        try:
            client.create_index(
                name=target_name,
                dimension=cfg["dimension"],
                metric=cfg["metric"],
                spec=ServerlessSpec(
                    cloud=cfg["cloud"],
                    region=cfg["region"]
                )
            )
            logger.info(f"[PINECONE] Created speaker index '{target_name}' successfully.")
        except Exception as exc:
            logger.error(f"[PINECONE] Failed to create index '{target_name}': {exc}")
            raise RuntimeError(f"Failed to create Pinecone index '{target_name}': {exc}") from exc

    # Describe index to validate configuration
    try:
        description = client.describe_index(target_name)
    except Exception as exc:
        logger.error(f"[PINECONE] Failed to describe index '{target_name}': {exc}")
        raise RuntimeError(f"Failed to inspect Pinecone index '{target_name}': {exc}") from exc

    dim = getattr(description, "dimension", None)
    if dim is None and isinstance(description, dict):
        dim = description.get("dimension")

    metric = getattr(description, "metric", None)
    if metric is None and isinstance(description, dict):
        metric = description.get("metric")

    if dim != cfg["dimension"]:
        raise ValueError(
            f"Index dimension mismatch for '{target_name}': expected {cfg['dimension']}, found {dim}. "
            "Please configure a different PINECONE_SPEAKER_INDEX to avoid mixing dimensions."
        )

    if metric and metric.lower() != cfg["metric"].lower():
        logger.warning(
            f"[PINECONE] Index metric is '{metric}', expected '{cfg['metric']}'."
        )

    _speaker_index = client.Index(target_name)
    return _speaker_index


def upsert_speaker_embedding(
    vector_id: str,
    vector: List[float],
    metadata: Dict[str, Any],
    namespace: Optional[str] = None
) -> None:
    """
    Upserts a single speaker embedding vector with deterministic metadata.
    """
    index = get_or_create_speaker_index(create_if_missing=True)
    ns = namespace or get_pinecone_config()["namespace"]

    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding length {len(vector)} does not match index dimension {EMBEDDING_DIMENSION}."
        )

    payload = [(vector_id, vector, metadata)]
    index.upsert(vectors=payload, namespace=ns)
    logger.info(f"[PINECONE] Upserted vector '{vector_id}' to namespace '{ns}'.")


def upsert_speaker_embeddings_batch(
    vectors: List[Dict[str, Any]],
    namespace: Optional[str] = None
) -> None:
    """
    Batch upserts speaker vectors.
    Each vector dict must contain 'id', 'values', 'metadata'.
    """
    if not vectors:
        return
    index = get_or_create_speaker_index(create_if_missing=True)
    ns = namespace or get_pinecone_config()["namespace"]
    index.upsert(vectors=vectors, namespace=ns)
    logger.info(f"[PINECONE] Batch upserted {len(vectors)} vectors to namespace '{ns}'.")


def query_speaker_embedding(
    query_vector: List[float],
    top_k: int = 5,
    namespace: Optional[str] = None,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Queries Pinecone for nearest matching speaker profiles.
    Returns list of matches: [{'id': str, 'score': float, 'metadata': dict}]
    """
    index = get_or_create_speaker_index(create_if_missing=False)
    ns = namespace or get_pinecone_config()["namespace"]

    query_params = {
        "vector": query_vector,
        "top_k": top_k,
        "include_metadata": True,
        "namespace": ns,
    }
    if filter_metadata:
        query_params["filter"] = filter_metadata

    try:
        response = index.query(**query_params)
        matches = []
        raw_matches = response.get("matches", []) if isinstance(response, dict) else getattr(response, "matches", [])
        for m in raw_matches:
            if isinstance(m, dict):
                matches.append({
                    "id": m.get("id"),
                    "score": float(m.get("score", 0.0)),
                    "metadata": m.get("metadata", {})
                })
            else:
                matches.append({
                    "id": getattr(m, "id", ""),
                    "score": float(getattr(m, "score", 0.0)),
                    "metadata": getattr(m, "metadata", {}) or {}
                })
        return matches
    except Exception as exc:
        logger.error(f"[PINECONE] Query failed: {exc}")
        raise RuntimeError(f"Pinecone similarity query failed: {exc}") from exc


def delete_speaker_embeddings(
    ids: Optional[List[str]] = None,
    delete_all: bool = False,
    namespace: Optional[str] = None
) -> None:
    """
    Deletes specific vector IDs or clears namespace.
    """
    index = get_or_create_speaker_index(create_if_missing=False)
    ns = namespace or get_pinecone_config()["namespace"]
    if delete_all:
        index.delete(delete_all=True, namespace=ns)
        logger.info(f"[PINECONE] Cleared all vectors in namespace '{ns}'.")
    elif ids:
        index.delete(ids=ids, namespace=ns)
        logger.info(f"[PINECONE] Deleted {len(ids)} vectors from namespace '{ns}'.")
