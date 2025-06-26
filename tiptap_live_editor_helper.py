"""
Helper functions to post and update what should be displayed in the live view.
"""

from typing import Any, Dict, List

import requests

from tiptap_models import DocNode, TiptapNode


def update_document(
    doc: DocNode, server_url: str = "http://localhost:8000"
) -> Dict[str, Any]:
    """
    Update the entire document with new content.

    Args:
        content: The complete ProseMirror document schema
        server_url: The base URL of the FastAPI server

    Returns:
        Response from the server
    """
    url = f"{server_url}/api/update-doc"
    payload = {"doc": doc.model_dump()}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to update document: {e}")


def append_to_document(
    content: List[TiptapNode], server_url: str = "http://localhost:8000"
) -> Dict[str, Any]:
    """
    Append content to the existing document.

    Args:
        content: List of ProseMirror node objects to append
        server_url: The base URL of the FastAPI server

    Returns:
        Response from the server
    """
    url = f"{server_url}/api/append-to-doc"

    payload = {"new_nodes": [c.model_dump() for c in content]}

    print(f"New content: {payload}")

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to append to document: {e}")
