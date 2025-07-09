import argparse
import json
import os
import sys
from typing import Optional

import qdrant_client
from dotenv import load_dotenv
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant.base import QdrantVectorStore
from qdrant_client import models

from export.models import Blocks, Documents
from fixme import find_document_by_chapter, list_blocks

load_dotenv()

COLLECTION_NAME = "williston_town_plan"


def index_block(
    block: Blocks,
    chapter_number: int,
    chapter_title: str,
    section_path: Optional[list[str]] = None,
) -> list[Document]:
    """
    For each block, return a (or multiple) LlamaIndex Documents.

    paragraph block types should be split at new lines, with one Document
    per nested paragraph.

    Citations, Images, Image headers can all be ignored.

    The actions table will need to get broken down into 1 document/objective,strategy and action.
    Though each action should keep the strategy text in its document.
    """
    if section_path is None:
        section_path = []

    base_metadata = {
        "block_id": str(block.id),
        "block_type": block.type,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "document_index": block.document_index,
    }

    documents = []
    section_path = " > ".join(section_path) if section_path else ""

    # Handle different block types
    if block.type == "paragraph":
        # Split paragraph at newlines, create one Document per nested paragraph
        for elem in block.content:
            if elem["type"] != "text":
                continue

            individual_paragraphs = elem["text"].split("\n")
            for p in individual_paragraphs:
                if not p.strip():
                    continue
                text = p if not section_path else f"Section: {section_path}.\n{p}"
                doc_metadata = base_metadata.copy()
                doc_metadata["text_type"] = "paragraph"
                documents.append(Document(text=text, metadata=doc_metadata))

    elif block.type in [
        "citation",
        "image",
        "imageHeader",
        "heading",
        "table",
        "custom",
    ]:
        # Ignore these block types as specified
        return []

    elif block.type == "action_table":
        # Break down action table into multiple documents
        if block.content:
            # Create documents for objectives
            objectives = block.content.get("objectives", [])
            for obj in objectives:
                obj_metadata = base_metadata.copy()
                obj_metadata["text_type"] = "objective"
                obj_metadata["objective_label"] = obj.get("label", "")

                objective_text = (
                    f"Objective {obj.get('label', '')}: {obj.get('text', '')}"
                )
                documents.append(Document(text=objective_text, metadata=obj_metadata))

            # Create documents for strategies and their actions
            strategies = block.content.get("strategies", [])
            for strategy in strategies:
                strategy_label = strategy.get("label", "")
                strategy_text = strategy.get("text", "")

                # Create document for the strategy itself
                strat_metadata = base_metadata.copy()
                strat_metadata["text_type"] = "strategy"
                strat_metadata["strategy_label"] = strategy_label

                strategy_doc_text = f"Strategy {strategy_label}: {strategy_text}"
                documents.append(
                    Document(text=strategy_doc_text, metadata=strat_metadata)
                )

                # Create documents for each action under this strategy
                actions = strategy.get("actions", [])
                for action in actions:
                    action_metadata = base_metadata.copy()
                    action_metadata["text_type"] = "action"
                    action_metadata["strategy_label"] = strategy_label
                    action_metadata["action_label"] = action.get("label", "")

                    # Include strategy text in action document as specified
                    action_text = (
                        f"Strategy {strategy_label}: {strategy_text}\n\n"
                        f"Action {action.get('label', '')}: {action.get('text', '')}\n"
                        f"Responsibility: {action.get('responsibility', '')}\n"
                        f"Timeframe: {action.get('timeframe', '')}\n"
                        f"Cost: {action.get('cost', '')}"
                    )
                    documents.append(
                        Document(text=action_text, metadata=action_metadata)
                    )

    elif block.type == "goal_item":
        # Handle goal items with their trait attribute
        text = block.text or ""
        if text.strip():
            text = f"Goal: {block.attrs.get('trait', '')} in 2050 {text}"
            goal_metadata = base_metadata.copy()
            goal_metadata["text_type"] = "goal_item"
            if block.attrs:
                goal_metadata["trait"] = block.attrs.get("trait", "")
            documents.append(Document(text=text, metadata=goal_metadata))

    elif block.type == "fact_item":
        # Handle fact items with their label attribute
        text = block.text or ""
        if text.strip():
            fact_metadata = base_metadata.copy()
            fact_metadata["text_type"] = "fact_item"
            if block.attrs:
                fact_metadata["label"] = block.attrs.get("label", "")
            documents.append(Document(text=text, metadata=fact_metadata))

    else:
        # Handle other block types generically
        raise Exception(f"Unexpected block type: {block.type}")

    return documents


def index_blocks(
    chapter_number: int, document: Documents, blocks: list[Blocks]
) -> list[Document]:
    qdrant_docs = []

    # Build section path as we traverse the document
    current_section_path = []
    last_heading_level = 0

    for block in blocks:
        if block.type == "heading":
            if block.attrs["level"] <= last_heading_level:
                current_section_path = current_section_path[: block.attrs["level"] - 1]

            current_section_path.append(block.text)
            last_heading_level = block.attrs["level"]
            continue

        d = index_block(
            block,
            chapter_number=chapter_number,
            chapter_title=document.title,
            section_path=current_section_path,
        )
        print(f"Got {len(d)} docs for {block.type}")
        qdrant_docs.extend(d)

    for d in qdrant_docs:
        print(d.text)
        print(d.metadata)
        print("\n\n")
    return qdrant_docs


def main():
    parser = argparse.ArgumentParser(description="Index document by chapter number")
    parser.add_argument(
        "--chapter", type=int, required=True, help="Chapter number to find the document"
    )

    args = parser.parse_args()
    chapter_number = args.chapter
    print(f"Fetching document for chapter {chapter_number}")
    # Find the document by chapter
    document = find_document_by_chapter(chapter_number)
    if not document:
        sys.exit(1)

    # List current blocks
    blocks = list_blocks(document)
    if not blocks:
        print("No blocks found in document")
        sys.exit(1)

    qdrant_documents = index_blocks(chapter_number, document, blocks)

    client = qdrant_client.QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_CLOUD_API_KEY"),
    )

    # Configure LlamaIndex
    Settings.embed_model = OpenAIEmbedding()
    Settings.node_parser = SimpleNodeParser.from_defaults()

    # Check if collection exists before creating it
    collections = client.get_collections().collections
    collection_names = [collection.name for collection in collections]

    if COLLECTION_NAME not in collection_names:
        print(f"Creating new collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=1536, distance=models.Distance.COSINE
            ),
        )
    else:
        print(f"Using existing collection: {COLLECTION_NAME}")

        # Set up Qdrant vector store
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
    )

    # Create storage context
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Create and save the index
    index = VectorStoreIndex.from_documents(
        qdrant_documents,
        storage_context=storage_context,
    )

    print(
        f"Indexed {len(qdrant_documents)} documents to Qdrant collection '{COLLECTION_NAME}'"
    )

    # Provide an example query using the index
    example_query = f"What are the main objectives in Chapter {chapter_number}?"
    retriever = index.as_retriever(similarity_top_k=3)
    nodes = retriever.retrieve(example_query)

    print("\nExample query retrieval test:")
    print(f"Query: {example_query}")
    print(f"Retrieved {len(nodes)} nodes:")
    for i, node in enumerate(nodes):
        metadata = node.metadata
        print(f"\nNode {i + 1}:")
        print(f"  Text: {node.text[:100]}...")
        print(f"  Score: {node.score}")
        print(f"  Chapter: {metadata.get('chapter_number')}")
        print(f"  Type: {metadata.get('node_type', 'N/A')}")
        if "section" in metadata:
            print(f"  Section: {metadata.get('section')}")


if __name__ == "__main__":
    main()
