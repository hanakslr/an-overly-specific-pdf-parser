"""
Given a file name, get the latest output for it, and dump its blocks to postgres

Need to have dumped models from pg
PGPASSWORD=postgres uv run -m pwiz -e postgresql -H localhost -p 54322 -u postgres postgres > export/models.py

"""

import importlib
import json
import os
import pkgutil
import re
import sys
from pathlib import Path
from typing import Union
from uuid import UUID

from dotenv import load_dotenv
from peewee import fn
from pydantic import TypeAdapter
from supabase import Client, create_client

import schema
from export.models import Blocks, BlockSchemas, Collections, Documents, database
from pipeline import PipelineState
from pipeline_state_helpers import resume_from_latest
from schema.block import Block

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

COLLECTION_NAME = "Williston Town Plan"


def dump_images(file_name: str, document_id: str):
    """
    We have images in output/images/pymupdf/{file_name} that we want to upload.
    Everything here should get added to bucket - images/{document.id}/{file_name}/{image_name}
    using the supabase client
    """
    # Construct the local path where images are stored
    local_images_path = Path(f"output/images/pymupdf/{file_name}")

    if not local_images_path.exists():
        print(f"Warning: No images directory found at {local_images_path}")
        return

    # Get all image files in the directory
    image_files = (
        list(local_images_path.glob("*.png"))
        + list(local_images_path.glob("*.jpg"))
        + list(local_images_path.glob("*.jpeg"))
    )

    if not image_files:
        print(f"No image files found in {local_images_path}")
        return

    print(f"Found {len(image_files)} images to upload for document {document_id}")

    uploaded_count = 0
    for image_file in image_files:
        try:
            # Construct the bucket path: images/{document_id}/{file_name}/{image_name}
            bucket_path = f"{document_id}/{file_name}/{image_file.name}"

            # Read the image file
            with open(image_file, "rb") as f:
                image_data = f.read()

            # Upload to Supabase storage
            supabase.storage.from_("images").upload(
                path=bucket_path,
                file=image_data,
                file_options={
                    "content-type": "image/png"
                    if image_file.suffix == ".png"
                    else "image/jpeg"
                },
            )

            print(f"  ✅ Uploaded {image_file.name} to {bucket_path}")
            uploaded_count += 1

        except Exception as e:
            print(f"  ❌ Failed to upload {image_file.name}: {str(e)}")

    print(
        f"Successfully uploaded {uploaded_count}/{len(image_files)} images for document {document_id}"
    )


def update_image_src_attributes(block_data, document_id: str):
    """
    Update image src attributes to include document ID prefix.
    Handles both 'image' blocks and 'imageHeader' blocks with image content.
    """
    if (
        block_data.type == "image"
        and block_data.attrs
        and hasattr(block_data.attrs, "src")
    ):
        # For image blocks, update the src attribute directly
        if block_data.attrs.src and not block_data.attrs.src.startswith(
            f"images/{document_id}/"
        ):
            block_data.attrs.src = f"images/{document_id}/{block_data.attrs.src}"

    elif block_data.type == "imageHeader" and block_data.content:
        # For imageHeader blocks, update src attributes in all image content
        for content_item in block_data.content:
            if (
                content_item.type == "image"
                and hasattr(content_item, "attrs")
                and hasattr(content_item.attrs, "src")
            ):
                if content_item.attrs.src and not content_item.attrs.src.startswith(
                    f"images/{document_id}/"
                ):
                    content_item.attrs.src = (
                        f"images/{document_id}/{content_item.attrs.src}"
                    )


def extract_text(node: "Block") -> str:
    """Recursively extract text from a TiptapNode."""
    # The 'text' attribute is specific to 'text' type nodes

    if isinstance(node, str):
        return node

    if getattr(node, "type") == "text" and hasattr(node, "text"):
        return getattr(node, "text", "") or ""

    # For other node types, recurse through their content
    if not hasattr(node, "content") or not getattr(node, "content"):
        return ""

    return "".join(extract_text(child) for child in node.content)


def create_or_get_document(
    title: str, slug: str, collection_name: str, label: str
) -> Documents:
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
        label=label,
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


def get_all_subclasses(cls):
    """Recursively find all subclasses of a given class."""
    all_subclasses = []
    for subclass in cls.__subclasses__():
        all_subclasses.append(subclass)
        all_subclasses.extend(get_all_subclasses(subclass))
    return all_subclasses


def dump_block_schema(collection_id: UUID):
    """
    Dump our blocks to the block_schema table so that the frontend can get types
    """
    try:
        collection = Collections.get_by_id(collection_id)
    except Collections.DoesNotExist:
        print(f"Collection with id {collection_id} not found.")
        return

    # Dynamically import all modules in the 'schema' package to register all Block subclasses.
    for _, module_name, _ in pkgutil.walk_packages(
        schema.__path__, schema.__name__ + "."
    ):
        importlib.import_module(module_name)

    # Now get all subclasses recursively
    all_blocks = get_all_subclasses(Block)

    # We only want concrete block types that have a 'type' literal.
    block_classes = [
        cls
        for cls in all_blocks
        if "type" in cls.model_fields and cls.model_fields["type"].default
    ]

    print(f"Found {len(block_classes)} block types to process.")

    # Generate a single schema for a Union of all block types
    if not block_classes:
        return
    union_type = Union[tuple(block_classes)]
    adapter = TypeAdapter(union_type)
    combined_schema = adapter.json_schema()

    block_type = "combined"

    # Use get_or_create to avoid duplicates for (collection, "combined")
    block_schema_record, created = BlockSchemas.get_or_create(
        collection=collection,
        block_type=block_type,
        defaults={"schema": combined_schema},
    )

    if created:
        print("  ✅ Created combined schema for block types")
    else:
        # If it exists, check if the schema has changed and update it.
        if block_schema_record.schema != combined_schema:
            block_schema_record.schema = combined_schema
            block_schema_record.save()
            print("  🔄 Updated combined schema for block types")
        else:
            print("  👌 Combined schema is already up-to-date.")


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
        matches = re.match(r"^(\d+)(?:\s+\|)?\s+(.*)$", state.blocks[0].content[0].text)

        title = matches.group(2)

        def titlecase(s: str):
            return " ".join(x.capitalize() for x in s.split())

        title = titlecase(title.strip())

        label = f"Chapter {matches.group(1)}"

        slug = re.sub(r"\s", "-", title.lower())
        slug = re.sub(r"[^a-z|-]", "", slug)

        document = create_or_get_document(
            title=title, slug=slug, collection_name=COLLECTION_NAME, label=label
        )

        prev_block_record = None
        for i, block_data in enumerate(state.blocks):
            print(f"  Inserting block {i + 1}/{len(state.blocks)}: {block_data.type}")

            # Update image src attributes to include document ID prefix
            update_image_src_attributes(block_data, str(document.id))

            attrs_json = block_data.attrs.model_dump() if block_data.attrs else None
            if hasattr(block_data, "content"):
                if isinstance(block_data.content, dict):
                    content_json = block_data.content
                else:
                    content_json = (
                        [c.model_dump() for c in block_data.content]
                        if block_data.content
                        else None
                    )
            else:
                content_json = {}

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

        print("🔍 Dumping block schemas...")
        dump_block_schema(document.collection.id)
        print("✅ Done dumping block schemas.")

        # Extract file name from pdf_path for image upload
        file_name = Path(pdf_path).stem
        print(f"📸 Uploading images for file: {file_name}")
        dump_images(file_name, str(document.id))

    finally:
        if not database.is_closed():
            database.close()
