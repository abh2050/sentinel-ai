"""
RAG Service Configuration Module
Defines runtime parameters for vector retrieval, reranking, chunking, and inference.
"""
from pydantic import BaseModel, Field
import json
import os

class RAGConfig(BaseModel):
    # Retrieval Configuration
    # Baseline: top_k = 5. Misconfiguration / Incident INC-2026-0042 sets top_k = 30
    top_k: int = Field(default=5, description="Number of chunks retrieved from vector store", ge=1, le=50)
    similarity_threshold: float = Field(default=0.68, description="Minimum cosine similarity score", ge=0.0, le=1.0)
    
    # Reranker Configuration
    reranker_enabled: bool = Field(default=False, description="Enable cross-encoder reranking stage")
    reranker_top_n: int = Field(default=5, description="Number of chunks retained after reranking", ge=1, le=20)
    
    # Chunking & Context Window
    chunk_size: int = Field(default=512, description="Size of each document chunk in tokens")
    chunk_overlap: int = Field(default=64, description="Chunk overlap in tokens")
    max_context_tokens: int = Field(default=2048, description="Maximum allowed context tokens")
    
    # LLM Inference Parameters
    model_name: str = Field(default="gemini-2.5-flash", description="LLM model name")
    temperature: float = Field(default=0.2, description="Sampling temperature", ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=512, description="Maximum output tokens")
    timeout_seconds: float = Field(default=5.0, description="Request timeout")
    retry_attempts: int = Field(default=2, description="Max retries on API failure")

# Global singleton configuration
_active_config = RAGConfig()

def get_config() -> RAGConfig:
    global _active_config
    return _active_config

def set_config(new_cfg: RAGConfig):
    global _active_config
    _active_config = new_cfg

def update_config_fields(**kwargs) -> RAGConfig:
    global _active_config
    data = _active_config.model_dump()
    data.update(kwargs)
    _active_config = RAGConfig(**data)
    return _active_config

def reset_to_healthy_baseline() -> RAGConfig:
    global _active_config
    _active_config = RAGConfig(
        top_k=5,
        similarity_threshold=0.68,
        reranker_enabled=False,
        reranker_top_n=5,
        chunk_size=512,
        chunk_overlap=64,
        max_context_tokens=2048,
        model_name="gemini-2.5-flash",
        temperature=0.2,
        max_output_tokens=512,
        timeout_seconds=5.0,
        retry_attempts=2
    )
    return _active_config
