"""Schemas for RAG pipeline handoffs."""

from pydantic import BaseModel, Field, field_validator


class ParsedQuery(BaseModel):
    """Output from query parser."""
    original_query: str
    search_query: str = Field(min_length=3, description="Optimized for retrieval")
    filters: dict = Field(default_factory=dict)
    max_results: int = Field(default=10, ge=1, le=100)


class Document(BaseModel):
    """A retrieved document."""
    id: str
    content: str = Field(min_length=10)
    metadata: dict = Field(default_factory=dict)


class RetrievedDocs(BaseModel):
    """Output from retriever."""
    query: str
    documents: list[Document] = Field(min_length=1)  # Must retrieve at least 1
    total_found: int = Field(ge=0)

    @field_validator("documents")
    @classmethod
    def check_not_empty(cls, v):
        if len(v) == 0:
            raise ValueError("Retriever returned no documents")
        return v


class RankedDocument(BaseModel):
    """A document with relevance score."""
    id: str
    content: str
    score: float = Field(ge=0.0, le=1.0)  # Normalized score
    rank: int = Field(ge=1)


class RankedDocs(BaseModel):
    """Output from reranker."""
    query: str
    documents: list[RankedDocument] = Field(min_length=1)
    model_used: str

    @field_validator("documents")
    @classmethod
    def check_sorted(cls, v):
        """Verify documents are sorted by score descending."""
        scores = [doc.score for doc in v]
        if scores != sorted(scores, reverse=True):
            raise ValueError("Documents not sorted by score")
        return v


class Citation(BaseModel):
    """A citation in the generated answer."""
    doc_id: str
    quote: str = Field(min_length=5)
    relevance: str = Field(description="Why this source supports the claim")


class RAGOutput(BaseModel):
    """Final output from generator."""
    answer: str = Field(min_length=50)
    citations: list[Citation] = Field(min_length=1)  # Must cite at least 1 source
    confidence: float = Field(ge=0.0, le=1.0)
    sources_used: int = Field(ge=1)
