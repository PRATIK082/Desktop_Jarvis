"""Memory layers (conversation, explicit long-term, document RAG)."""

from jarvis.memory.chunking import chunk_text, chunk_with_sections
from jarvis.memory.database import MemoryDatabase, close_db, get_db
from jarvis.memory.embeddings import EmbeddingService
from jarvis.memory.extractors import (
    ExtractionResult,
    detect_mime_type,
    extract_text,
    is_text_extension,
)
from jarvis.memory.models import (
    Conversation,
    ConversationMessage,
    Document,
    DocumentChunk,
    Memory,
    SearchResult,
)
from jarvis.memory.rag import format_context_for_prompt, retrieve_context
from jarvis.memory.repositories import (
    ConversationMessageRepository,
    ConversationRepository,
    DocumentChunkRepository,
    DocumentRepository,
    MemoryRepository,
    sha256_file,
)
from jarvis.memory.service import MemoryService

__all__ = [
    "MemoryDatabase",
    "close_db",
    "get_db",
    "EmbeddingService",
    "ExtractionResult",
    "detect_mime_type",
    "extract_text",
    "is_text_extension",
    "Conversation",
    "ConversationMessage",
    "Document",
    "DocumentChunk",
    "Memory",
    "SearchResult",
    "retrieve_context",
    "format_context_for_prompt",
    "ConversationMessageRepository",
    "ConversationRepository",
    "DocumentChunkRepository",
    "DocumentRepository",
    "MemoryRepository",
    "sha256_file",
    "MemoryService",
    "chunk_text",
    "chunk_with_sections",
]
