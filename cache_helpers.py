"""
Cache helper functions for pipeline operations.
"""

import hashlib
import json
import os
from typing import Any, Optional

from etl.pymupdf_parse import PyMuPDFOutput
from etl.zip_llama_pymupdf import ZippedOutputsPage


def get_cache_key(pdf_path: str, operation: str) -> str:
    """Generate a cache key based on PDF path and operation."""
    # Use file modification time to detect changes
    mtime = os.path.getmtime(pdf_path)
    key_data = f"{pdf_path}:{mtime}:{operation}"
    return hashlib.md5(key_data.encode()).hexdigest()


def get_cache_path(pdf_path: str, operation: str) -> str:
    """Get the cache file path for a given PDF and operation."""
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    cache_key = get_cache_key(pdf_path, operation)
    cache_dir = f".cache/{pdf_name}"
    os.makedirs(cache_dir, exist_ok=True)
    return f"{cache_dir}/{operation}_{cache_key}.json"


def is_cache_valid(pdf_path: str, operation: str) -> bool:
    """Check if cache exists and is valid for the given PDF and operation."""
    cache_path = get_cache_path(pdf_path, operation)
    if not os.path.exists(cache_path):
        return False

    # Check if cache is older than the PDF file
    cache_mtime = os.path.getmtime(cache_path)
    pdf_mtime = os.path.getmtime(pdf_path)

    return cache_mtime >= pdf_mtime


def load_from_cache(pdf_path: str, operation: str) -> Optional[Any]:
    """Load data from cache if it exists and is valid."""
    if not is_cache_valid(pdf_path, operation):
        return None

    cache_path = get_cache_path(pdf_path, operation)
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached_data = json.load(f)

        # Convert back to appropriate objects based on operation
        if operation == "pymupdf_extract":
            return PyMuPDFOutput(**cached_data)
        elif operation == "zip_outputs":
            # Convert the list of pages back to ZippedOutputsPage objects
            pages = []
            for page_data in cached_data:
                pages.append(ZippedOutputsPage(**page_data))
            return pages

        return cached_data
    except Exception as e:
        print(f"⚠️ Could not load cache for {operation}: {e}")
        return None


def save_to_cache(pdf_path: str, operation: str, data: Any) -> None:
    """Save data to cache."""
    cache_path = get_cache_path(pdf_path, operation)
    try:
        # Convert data to JSON-serializable format
        if hasattr(data, "model_dump"):
            # Pydantic model
            serializable_data = data.model_dump()
        elif isinstance(data, list) and all(
            hasattr(item, "model_dump") for item in data
        ):
            # List of Pydantic models
            serializable_data = [item.model_dump() for item in data]
        else:
            serializable_data = data

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=2, ensure_ascii=False)

        print(f"💾 Cached {operation} result for: {os.path.basename(pdf_path)}")
    except Exception as e:
        print(f"⚠️ Could not save cache for {operation}: {e}")
