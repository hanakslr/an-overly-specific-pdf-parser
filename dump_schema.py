import importlib
import os
import pkgutil
from typing import Union
from uuid import UUID

from dotenv import load_dotenv
from pydantic import TypeAdapter
from supabase import Client, create_client

import schema
from export.models import BlockSchemas, Collections, database
from schema.block import Block

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

COLLECTION_NAME = "Williston Town Plan"


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

    def remove_titles(s: dict) -> dict:
        """
        our typescript parser doesn't like titles - it make it thing the fields are
        special and assigns them their own redundant values
        """
        if isinstance(s, dict):
            return {k: remove_titles(v) for k, v in s.items() if k != "title"}
        elif isinstance(s, list):
            return [remove_titles(item) for item in s]
        else:
            return s

    def replace_prefixItems(s: dict) -> dict:
        """
        our typescript parser doesn't handle this well, instead we need
        to convert to `items`
        """
        if isinstance(s, dict):
            result = {}
            for k, v in s.items():
                new_key = "items" if k == "prefixItems" else k
                result[new_key] = replace_prefixItems(v)
            return result
        elif isinstance(s, list):
            return [replace_prefixItems(item) for item in s]
        else:
            return s

    # Generate a single schema for a Union of all block types
    if not block_classes:
        return
    union_type = Union[tuple(block_classes)]
    adapter = TypeAdapter(union_type)
    combined_schema = adapter.json_schema()
    combined_schema = remove_titles(combined_schema)
    combined_schema = replace_prefixItems(combined_schema)

    # Use get_or_create to avoid duplicates for (collection, "combined")
    block_schema_record, created = BlockSchemas.get_or_create(
        collection=collection,
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
    database.connect()
    collection, _ = Collections.get_or_create(name=COLLECTION_NAME)

    print("🔍 Dumping block schemas...")
    dump_block_schema(collection.id)
    print("✅ Done dumping block schemas.")

    if not database.is_closed():
        database.close()
