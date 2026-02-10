# Embeddings module
from .templates import TemplateRenderer
from .client import EmbeddingClient
from .vector_record import MultiViewVectorRecordBuilder

__all__ = ["TemplateRenderer", "EmbeddingClient", "MultiViewVectorRecordBuilder"]
