"""Local E5 inference; failures leave lexical retrieval available."""

import logging
import os

from wow_knowledge.config import settings

logger = logging.getLogger(__name__)


class E5Encoder:
    def __init__(self) -> None:
        self.model = None
        self.failed = False

    def _load(self) -> bool:
        if not settings.wow_embeddings_enabled or self.failed:
            return False
        if self.model is None:
            try:
                os.environ.setdefault("HF_HOME", settings.hf_home)
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(settings.wow_embedding_model, device="cpu")
            except Exception as exc:
                logger.warning("Embeddings unavailable; using text search: %s", exc)
                self.failed = True
                return False
        return True

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]] | None:
        if not texts or not self._load():
            return None
        prefix = "query: " if query else "passage: "
        try:
            return self.model.encode([prefix + text for text in texts], normalize_embeddings=True, show_progress_bar=False).tolist()
        except Exception as exc:
            logger.warning("E5 inference failed; falling back to text: %s", exc)
            self.failed = True
            return None


encoder = E5Encoder()
