"""OpenAI embedding client with batching and L2 normalization."""

import logging
import math
import os
import time
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MODEL = "text-embedding-3-large"
DEFAULT_DIM = 3072
MAX_BATCH_SIZE = 2048  # OpenAI limit
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class EmbeddingClient:
    """OpenAI embedding client with batching and normalization."""
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        dim: int = DEFAULT_DIM,
        normalize: bool = True,
    ):
        """Initialize embedding client.
        
        Args:
            api_key: OpenAI API key (defaults to env OPENAI_API_KEY)
            model: Embedding model name
            dim: Expected embedding dimension
            normalize: Whether to L2-normalize vectors
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required (set OPENAI_API_KEY)")
        
        self.model = model
        self.dim = dim
        self.normalize = normalize
        
        self.client = OpenAI(api_key=self.api_key)
        
        logger.info(f"EmbeddingClient initialized: model={model}, dim={dim}")
    
    @staticmethod
    def l2_normalize(vector: list[float]) -> list[float]:
        """L2 normalize a vector for cosine similarity.
        
        Args:
            vector: Input vector
        
        Returns:
            L2-normalized vector
        """
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]
    
    def embed_single(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed a single text.
        
        Args:
            text: Text to embed
        
        Returns:
            Tuple of (embedding_vector, metadata)
        """
        vectors, metadata = self.embed_texts([text])
        return vectors[0], metadata
    
    def embed_texts(
        self,
        texts: list[str],
        batch_size: int = MAX_BATCH_SIZE,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Embed multiple texts with batching.
        
        Args:
            texts: List of texts to embed
            batch_size: Max texts per API call
        
        Returns:
            Tuple of (list of embedding vectors, metadata)
        """
        if not texts:
            return [], {"model": self.model, "total_tokens": 0}
        
        all_embeddings: list[list[float]] = []
        total_tokens = 0
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch,
                    )
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(f"Embedding API error (attempt {attempt + 1}): {e}")
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        logger.error(f"Embedding API failed after {MAX_RETRIES} attempts")
                        raise
            
            # Extract embeddings
            batch_embeddings = []
            for item in response.data:
                embedding = item.embedding
                
                # Validate dimension
                if len(embedding) != self.dim:
                    raise ValueError(
                        f"Dimension mismatch: expected {self.dim}, got {len(embedding)}"
                    )
                
                # Normalize if requested
                if self.normalize:
                    embedding = self.l2_normalize(embedding)
                
                batch_embeddings.append(embedding)
            
            all_embeddings.extend(batch_embeddings)
            total_tokens += response.usage.total_tokens
            
            logger.debug(
                f"Embedded batch {i // batch_size + 1}: "
                f"{len(batch)} texts, {response.usage.total_tokens} tokens"
            )
        
        metadata = {
            "model": self.model,
            "dim": self.dim,
            "normalized": self.normalize,
            "total_tokens": total_tokens,
            "text_count": len(texts),
        }
        
        logger.info(f"Embedded {len(texts)} texts, {total_tokens} total tokens")
        
        return all_embeddings, metadata


# Singleton instance
_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    """Get or create singleton embedding client."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
