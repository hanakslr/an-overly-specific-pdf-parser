#!/usr/bin/env python3
"""
Script to correct blocks in a document by chapter number.
Accepts --chapter argument and provides a menu of correction options.
"""

import argparse
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from peewee import fn
from supabase import Client, create_client

from export.models import Blocks, Collections, Documents, database
from schema.tiptap_models import ParagraphNode, TableheaderNode, TablerowNode, TextNode

# Load environment variables
load_dotenv()

# Supabase configuration (same as save_latest.py)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

COLLECTION_NAME = "Williston Town Plan"


def find_document_by_chapter(chapter_number: int) -> Optional[Documents]:
    """
    Find a document by chapter number in the label field.
    """
    try:
        database.connect()

        # Look for documents with label like "Chapter {chapter_number}"
        chapter_label = f"Chapter {chapter_number}"

        document = (
            Documents.select()
            .join(Collections)
            .where(
                (Documents.label == chapter_label)
                & (Collections.name == COLLECTION_NAME)
            )
            .first()
        )

        if document:
            print(f"✅ Found document: {document.title} (ID: {document.id})")
            return document
        else:
            print(
                f"❌ No document found with label '{chapter_label}' in collection '{COLLECTION_NAME}'"
            )
            return None

    except Exception as e:
        print(f"❌ Error finding document: {e}")
        return None
    finally:
        if not database.is_closed():
            database.close()


def list_blocks(document: Documents):
    """
    List all blocks in the document with their index and type.
    """
    try:
        database.connect(reuse_if_open=True)

        blocks = (
            Blocks.select()
            .where(Blocks.document == document)
            .order_by(Blocks.document_index)
        )

        print(f"\n📋 Blocks in document '{document.title}':")
        print("-" * 60)
        print(f"{'Index':<6} {'Type':<15} {'Text Preview':<35}")
        print("-" * 60)

        for block in blocks:
            text_preview = (block.text or "")[:35]
            if len(text_preview) > 35:
                text_preview = text_preview[:32] + "..."
            print(f"{block.document_index:<6} {block.type:<15} {text_preview}")

        print("-" * 60)
        return blocks

    except Exception as e:
        print(f"❌ Error listing blocks: {e}")
        return []


def get_db_block(document: Documents, block_index: int):
    block = (
        Blocks.select()
        .where((Blocks.document == document) & (Blocks.document_index == block_index))
        .first()
    )

    if not block:
        print(f"❌ No block found with index {block_index}")
        return None

    return block


def merge_blocks(document: Documents, block_index: int, second_block_index) -> bool:
    first_block = get_db_block(document, block_index)
    second_block = get_db_block(document, second_block_index)

    if not first_block or not second_block:
        print("Block not found")
        return False

    if first_block.type != second_block.type:
        print(
            f"Blocks are mismatched types: {first_block.type} and {second_block.type}"
        )
        return False

    if first_block.type == "paragraph":
        first_block.text = first_block.text + " " + second_block.text
        # Find the first text block in second_block. If it doens't begin with a space insert one.
        first_text_node = next(n for n in second_block.content if n.type == "text")
        first_text_node.text = f" {first_text_node}"
        first_block.content.extend(second_block.content)

        first_block.save()
        delete_block_by_index(document, second_block_index)
        return True
    else:
        print(f"Unhandled block type {first_block.type}")
    return False


def add_table_header_to_block(document: Documents, block_index: int) -> bool:
    try:
        block = get_db_block(document, block_index)
        header_text = input("Enter title for table: ").strip()
        colspan = input("Enter colspan: ").strip()

        header_row = TablerowNode(
            content=[
                TableheaderNode(
                    content=[ParagraphNode(content=[TextNode(text=header_text)])],
                    attrs=TableheaderNode.Attrs(colspan=int(colspan)),
                )
            ]
        )

        block.content.insert(0, header_row.model_dump())
        print(block.content)
        good = input("looks good? (y/n)")

        if good == "y":
            block.save()
            return True
        else:
            return False
    except Exception as e:
        print(f"Error inserting header: {e}")
        return False


def add_caption_to_block(document: Documents, block_index: int) -> bool:
    try:
        block = get_db_block(document, block_index)
        block.attrs = block.attrs or {}

        if block.attrs["caption"]:
            print(f"Block has caption: {block.attrs['caption']}")

        choice = input("Enter caption for block: ").strip()

        block.attrs["caption"] = choice
        block.save()

        return True
    except Exception as e:
        print(f"Error deleting block: {e}")
        return False


def delete_block_by_index(document: Documents, block_index: int) -> bool:
    """
    Delete a block by its document_index.
    """
    try:
        # Find the block to delete
        block_to_delete = get_db_block(document, block_index)

        if not block_to_delete:
            return False

        # Get the previous and next blocks
        prev_block = block_to_delete.prev_block
        next_block = block_to_delete.next_block

        # Update the linked list
        if prev_block and next_block:
            # Connect prev to next
            prev_block.next_block = next_block
            prev_block.save()
            # Connect next to prev
            next_block.prev_block = prev_block
            next_block.save()
        elif prev_block:
            # This was the last block, remove next reference from prev
            prev_block.next_block = None
            prev_block.save()
        elif next_block:
            # This was the first block, remove prev reference from next
            next_block.prev_block = None
            next_block.save()

        # Delete the block
        block_to_delete.delete_instance()

        # Update document_index for all subsequent blocks
        Blocks.update(document_index=Blocks.document_index - 1).where(
            (Blocks.document == document) & (Blocks.document_index > block_index)
        ).execute()

        print(f"✅ Deleted block at index {block_index}")
        return True

    except Exception as e:
        print(f"❌ Error deleting block: {e}")
        return False


def show_menu():
    """
    Display the correction menu options.
    """
    print("\n🔧 Block Correction Menu")
    print("=" * 30)
    print("1. Delete a block by document_index")
    print("2. Add caption to image or table")
    print("3. Add table header to table")
    print("4. Merge blocks")
    print("0. Exit")
    print("=" * 30)


def get_block_index_from_user(blocks):
    block_index = int(input("Enter the document_index of the block: "))

    # Validate the index exists
    if not any(block.document_index == block_index for block in blocks):
        print(f"❌ No block found with index {block_index}")
        return None
    return block_index


def main():
    parser = argparse.ArgumentParser(
        description="Correct blocks in a document by chapter number"
    )
    parser.add_argument(
        "--chapter", type=int, required=True, help="Chapter number to find the document"
    )
    args = parser.parse_args()

    # Find the document by chapter
    document = find_document_by_chapter(args.chapter)
    if not document:
        sys.exit(1)

    # List current blocks
    blocks = list_blocks(document)
    if not blocks:
        print("No blocks found in document")
        sys.exit(1)

    # Main menu loop
    while True:
        show_menu()

        try:
            database.connect(reuse_if_open=True)
            choice = input("Enter your choice (0-4): ").strip()

            if choice == "0":
                print("👋 Goodbye!")
                break
            elif choice == "1":
                # Delete block by index
                try:
                    block_index = get_block_index_from_user(blocks)

                    if not block_index:
                        continue

                    # Confirm deletion
                    confirm = (
                        input(
                            f"Are you sure you want to delete block at index {block_index}? (y/N): "
                        )
                        .strip()
                        .lower()
                    )
                    if confirm in ["y", "yes"]:
                        if delete_block_by_index(document, block_index):
                            # Refresh the blocks list
                            blocks = list_blocks(document)
                    else:
                        print("❌ Deletion cancelled")

                except ValueError:
                    print("❌ Please enter a valid number")
            elif choice == "2":
                block_index = get_block_index_from_user(blocks)
                if not block_index:
                    continue

                if add_caption_to_block(document, block_index):
                    blocks = list_blocks(document)
            elif choice == "3":
                block_index = get_block_index_from_user(blocks)
                if not block_index:
                    continue
                if add_table_header_to_block(document, block_index):
                    blocks = list_blocks(document)
            elif choice == "4":
                print("First block: ")
                block_index = get_block_index_from_user(blocks)
                print("Second block")
                second_block_index = get_block_index_from_user(blocks)

                if not block_index or not second_block_index:
                    continue

                if merge_blocks(document, block_index, second_block_index):
                    blocks = list_blocks(document)

            else:
                print("❌ Invalid choice. Please enter a number between 0-4")

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except EOFError:
            print("\n👋 Goodbye!")
            break
        finally:
            if not database.is_closed():
                database.close()


if __name__ == "__main__":
    main()
