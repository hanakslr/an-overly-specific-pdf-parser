"""
Given a file name, get the latest output for it, and dump its blocks to postgres

Need to have dumped models from pg
PGPASSWORD=postgres uv run -m pwiz -e postgresql -H localhost -p 54322 -u postgres postgres > export/models.py

"""

import re
import sys

from peewee import fn

from export.models import Blocks, Collections, Documents, database
from pipeline import PipelineState
from pipeline_state_helpers import resume_from_latest
from schema.tiptap_models import TiptapNode

COLLECTION_NAME = "Williston Town Plan"


def extract_text(node: "TiptapNode") -> str:
    """Recursively extract text from a TiptapNode."""
    # The 'text' attribute is specific to 'text' type nodes
    if getattr(node, "type") == "text" and hasattr(node, "text"):
        return getattr(node, "text", "") or ""

    # For other node types, recurse through their content
    if not hasattr(node, "content") or not getattr(node, "content"):
        return ""

    return "".join(extract_text(child) for child in node.content)


def create_or_get_document(title: str, slug: str, collection_name: str) -> Documents:
    """
    Create a new document in the database, or get an existing one.
    If the document exists, its old blocks will be deleted.
    """
    collection, _ = Collections.get_or_create(name=collection_name)

    # Check if a document with this title and collection already exists
    existing_doc, created = Documents.get_or_create(
        title=title,
        slug=slug,
        collection=collection,
        defaults={
            "collection_index": (
                Documents.select(fn.Max(Documents.collection_index))
                .where(Documents.collection == collection)
                .scalar()
                or 0
            )
            + 1
        },
    )

    if not created:
        print(
            f"Document '{title}' already exists. Deleting its blocks before re-inserting."
        )
        Blocks.delete().where(Blocks.document == existing_doc).execute()
    else:
        print(f"Created new document: {existing_doc.title} (ID: {existing_doc.id})")

    return existing_doc


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export/save_latest.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    state_dict = resume_from_latest(pdf_path)
    if not state_dict:
        print(f"No saved state found for {pdf_path}")
        sys.exit(1)

    state = PipelineState(**state_dict)

    if not state.blocks:
        print("No blocks found in the pipeline state. Exiting.")
        sys.exit(0)

    database.connect()
    try:
        title = re.sub(r"^\d+", "", state.blocks[0].content[0].text)
        title = title.strip().title()

        slug_parts = title.split(" ")
        document = create_or_get_document(
            title=title,
            slug="-".join(slug_parts[0:3]).lower(),
            collection_name=COLLECTION_NAME,
        )

        prev_block_record = None
        for i, block_data in enumerate(state.blocks):
            print(f"  Inserting block {i + 1}/{len(state.blocks)}: {block_data.type}")

            attrs_json = block_data.attrs.model_dump() if block_data.attrs else None
            content_json = (
                [c.model_dump() for c in block_data.content]
                if block_data.content
                else None
            )

            block_record = Blocks.create(
                document=document,
                document_index=i,
                type=block_data.type,
                attrs=attrs_json,
                content=content_json,
                text=extract_text(block_data),
                prev_block=prev_block_record,
            )

            if prev_block_record:
                prev_block_record.next_block = block_record
                prev_block_record.save()

            prev_block_record = block_record

        print("✅ Done inserting blocks.")

    finally:
        if not database.is_closed():
            database.close()
