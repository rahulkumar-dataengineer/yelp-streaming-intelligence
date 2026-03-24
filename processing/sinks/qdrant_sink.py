"""Qdrant vector sink — Gemini embedding + Qdrant upsert for the Gold layer.

Three classes, each with a single responsibility:
  - GeminiEmbedder  — embeds text via the Gemini API with rate limiting + retry
  - QdrantManager   — manages the Qdrant collection (create, reset, upsert)
  - BatchSink       — composes the two above to process foreachBatch micro-batches
"""

import time
import uuid
from collections import deque

from google import genai
from google.genai import types as genai_types
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    HnswConfigDiff,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)
from pyspark.sql import DataFrame
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import settings
from processing.schemas import Gold
from platform_commons.logger import Logger

log = Logger.get(__name__)


# -------------------------
# Constants
# -------------------------

EMBEDDING_BATCH_SIZE: int = 100         # texts per Gemini API call (hard API limit)
QDRANT_UPSERT_BATCH_SIZE: int = 500     # vectors per Qdrant upsert call
EMBEDDING_RPM_LIMIT: int = 2_900        # Gemini free tier is 3,000 RPM; stay slightly under

EMBEDDING_TEXT_FIELDS: list[str] = Gold.QDRANT_FIELDS["embedding_text_fields"]
PAYLOAD_FIELDS: list[str] = Gold.QDRANT_FIELDS["payload_fields"]


# -------------------------
# GeminiEmbedder
# -------------------------

class GeminiEmbedder:
    """Embeds text via the Gemini Embedding API with rate limiting and retry.

    Batches up to 100 texts per API call (hard Gemini limit).  A sliding-window
    rate limiter keeps throughput under the free-tier RPM cap, and tenacity
    retries with exponential backoff on 429/5xx errors.
    """

    def __init__(self, rpm_limit: int = EMBEDDING_RPM_LIMIT) -> None:
        self._client = genai.Client(api_key=settings.gemini.API_KEY)
        self._model = settings.gemini.EMBEDDING_MODEL
        self._dimensions = settings.gemini.EMBEDDING_DIMENSIONS
        self._rpm_limit = rpm_limit
        self._window: deque[float] = deque(maxlen=rpm_limit)
        log.info(f"GeminiEmbedder created: model={self._model}, dims={self._dimensions}")

    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        """Returns True for HTTP 429 (rate limit) and 5xx (server) errors."""

        exc_str = str(exc).lower()
        return "429" in exc_str or "500" in exc_str or "503" in exc_str or "resource exhausted" in exc_str

    def _wait_if_needed(self) -> None:
        """Blocks until a request slot is available within the RPM window."""

        now = time.time()
        if len(self._window) < self._rpm_limit:
            self._window.append(now)
            return

        oldest = self._window[0]
        elapsed = now - oldest
        if elapsed < 60.0:
            sleep_time = 60.0 - elapsed + 0.1
            log.info(f"Rate limiter: sleeping {sleep_time:.1f}s to stay under {self._rpm_limit} RPM")
            time.sleep(sleep_time)

        self._window.append(time.time())

    @retry(
        retry=retry_if_exception(lambda exc: GeminiEmbedder._is_retryable(exc)),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        stop=stop_after_attempt(8),
        before_sleep=lambda retry_state: log.warning(
            f"Embedding API retry #{retry_state.attempt_number}: "
            f"waiting {retry_state.next_action.sleep:.1f}s after {retry_state.outcome.exception()}"
        ),
    )
    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Single API call to embed up to 100 texts."""

        result = self._client.models.embed_content(
            model=self._model,
            contents=texts,
            config=genai_types.EmbedContentConfig(
                output_dimensionality=self._dimensions,
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        return [list(e.values) for e in result.embeddings]

    def embed_batch(self, texts: list[str], batch_id: int) -> list[list[float]]:
        """Embeds a list of texts, chunking into API calls of 100.

        Args:
            texts: All texts to embed for this micro-batch.
            batch_id: For progress logging.

        Returns:
            List of embedding vectors, one per input text.
        """

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            chunk = texts[i:i + EMBEDDING_BATCH_SIZE]
            self._wait_if_needed()
            embeddings = self._call_api(chunk)
            all_embeddings.extend(embeddings)
            log.info(f"Batch {batch_id}: embedded {i + len(chunk)}/{len(texts)} texts")

        return all_embeddings


# -------------------------
# QdrantManager
# -------------------------

class QdrantManager:
    """Manages the Qdrant collection: creation, reset, and batch upsert."""

    def __init__(self) -> None:
        self._client = QdrantClient(
            host=settings.qdrant.HOST,
            port=settings.qdrant.PORT,
            timeout=30,
        )
        self._collection = settings.qdrant.COLLECTION
        self._dimensions = settings.gemini.EMBEDDING_DIMENSIONS
        log.info(f"QdrantManager created: {settings.qdrant.HOST}:{settings.qdrant.PORT}")

    def ensure_collection(self) -> None:
        """Creates the collection if it doesn't already exist.

        Config: cosine similarity, vectors on disk, HNSW m=8/ef_construct=50,
        scalar int8 quantization in RAM. Tuned for 1M vectors on the GCP
        e2-micro VM (1GB RAM).
        """

        if self._client.collection_exists(collection_name=self._collection):
            info = self._client.get_collection(collection_name=self._collection)
            log.info(
                f"Qdrant collection already exists: {self._collection} "
                f"| vectors={info.points_count}"
            )
            return

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=self._dimensions,
                distance=Distance.COSINE,
                on_disk=True,
            ),
            hnsw_config=HnswConfigDiff(
                m=8,
                ef_construct=50,
            ),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    always_ram=True,
                ),
            ),
        )
        log.info(
            f"Qdrant collection created: {self._collection} "
            f"| size={self._dimensions}, distance=Cosine, on_disk=True, "
            f"hnsw(m=8, ef_construct=50), quantization=int8"
        )

    def upsert_points(self, points: list[PointStruct]) -> None:
        """Upserts points in chunks of QDRANT_UPSERT_BATCH_SIZE."""

        for i in range(0, len(points), QDRANT_UPSERT_BATCH_SIZE):
            chunk = points[i:i + QDRANT_UPSERT_BATCH_SIZE]
            self._client.upsert(
                collection_name=self._collection,
                points=chunk,
                wait=True,
            )
    
    def reset(self) -> None:
        """Deletes the collection for a clean rerun."""

        if self._client.collection_exists(collection_name=self._collection):
            self._client.delete_collection(collection_name=self._collection)
            log.info(f"Qdrant collection deleted: {self._collection}")
        else:
            log.info(f"Qdrant collection does not exist (nothing to reset): {self._collection}")



# -------------------------
# BatchSink
# -------------------------

class BatchSink:
    """Composes GeminiEmbedder + QdrantManager to process foreachBatch micro-batches.

    Usage in gold.py:
        sink = BatchSink()
        sink.sink_batch(batch_df, batch_id)
    """

    def __init__(self) -> None:
        self._embedder = GeminiEmbedder()
        self._qdrant = QdrantManager()
        self._total_upserted: int = 0

    @property
    def qdrant(self) -> QdrantManager:
        """Exposes QdrantManager for setup/reset operations in gold.py."""
        return self._qdrant

    def _review_id_to_uuid(self, review_id: str) -> str:
        """Deterministic UUID from review_id for idempotent Qdrant upserts."""

        return str(uuid.uuid5(uuid.NAMESPACE_URL, review_id))

    def _build_embedding_text(self, row: dict) -> str:
        """Concatenates embedding text fields: "business_name | categories | review_text"."""

        parts = [str(row.get(field, "") or "") for field in EMBEDDING_TEXT_FIELDS]
        return " | ".join(parts)

    def _build_payload(self, row: dict) -> dict:
        """Extracts payload fields from a row, dropping None values."""

        payload = {}
        for field in PAYLOAD_FIELDS:
            value = row.get(field)
            if value is not None:
                # Convert numpy/pandas types to native Python for JSON serialization
                payload[field] = value.item() if hasattr(value, "item") else value
        return payload

    def sink_batch(self, batch_df: DataFrame, batch_id: int) -> None:
        """Embeds and upserts a micro-batch to Qdrant.

        Self-contained try/except — errors are logged but never propagated,
        so a Qdrant failure does not block the BigQuery branch.
        """
        try:
            start = time.time()

            # 1. Select payload fields → pandas
            qdrant_pdf = batch_df.select(PAYLOAD_FIELDS).toPandas()
            row_count = len(qdrant_pdf)

            # 2. Build embedding input texts
            texts = [self._build_embedding_text(row) for _, row in qdrant_pdf.iterrows()]

            # 3. Embed all texts (internally batched at 100/call with rate limiting)
            all_embeddings = self._embedder.embed_batch(texts, batch_id)

            # 4. Build PointStructs
            points: list[PointStruct] = [
                PointStruct(
                    id=self._review_id_to_uuid(row["review_id"]),
                    vector=all_embeddings[idx],
                    payload=self._build_payload(row),
                )
                for idx, (_, row) in enumerate(qdrant_pdf.iterrows())
            ]

            # 5. Upsert (internally batched at 500/call)
            self._qdrant.upsert_points(points)

            elapsed = time.time() - start
            self._total_upserted += row_count
            log.info(
                f"Batch {batch_id}: Qdrant upserted {row_count} vectors "
                f"in {elapsed:.1f}s | total_upserted={self._total_upserted}"
            )

        except Exception as exc:
            log.error(f"Batch {batch_id}: Qdrant upsert failed: {exc}")
