import argparse
import sys

from fixme import find_document_by_chapter
from export.models import Blocks, database

CHAPTER_NUMBER = 6
NEW_ORDER = [14, 13, 15, 16, 18, 19, 17, 21, 20, 22, 23, 24, 25, 27, 26]


def reorder_blocks(document, new_order):
    """
    Reorder blocks in a document according to the new_order list.
    Only reorders the blocks specified in new_order, leaving other blocks in place.
    The new_order contains the document_index values in the desired order.
    """
    try:
        database.connect()

        # Get all blocks for the document
        all_blocks = (
            Blocks.select()
            .where(Blocks.document == document)
            .order_by(Blocks.document_index)
        ).execute()

        # Create a mapping of current document_index to block
        block_map = {block.document_index: block for block in all_blocks}

        # Validate that all blocks in new_order exist
        missing_blocks = [idx for idx in new_order if idx not in block_map]
        if missing_blocks:
            raise ValueError(
                f"Blocks with indices {missing_blocks} not found in document"
            )

        print(f"✅ Validated {len(new_order)} blocks for reordering")

        # Find the range of indices we're working with
        min_index = min(new_order)
        max_index = max(new_order)

        # Get blocks that come before and after our reorder range
        blocks_before = [
            block for block in all_blocks if block.document_index < min_index
        ]
        blocks_after = [
            block for block in all_blocks if block.document_index > max_index
        ]

        # Find the blocks that will be immediately before and after our reordered section
        block_before_range = blocks_before[-1] if blocks_before else None
        block_after_range = blocks_after[0] if blocks_after else None

        print(f"📋 Reordering blocks {min_index} to {max_index}")
        if block_before_range:
            print(f"  Block before range: {block_before_range.document_index}")
        if block_after_range:
            print(f"  Block after range: {block_after_range.document_index}")

        # Create a mapping from old index to new index within the range
        # We'll place the reordered blocks starting at min_index
        old_to_new_index = {}
        for new_pos, old_index in enumerate(new_order):
            new_index = min_index + new_pos
            old_to_new_index[old_index] = new_index

        # Update document_index for blocks being reordered
        for old_index, new_index in old_to_new_index.items():
            block = block_map[old_index]
            block.document_index = new_index
            block.save()
            print(f"  Moved block {old_index} to position {new_index}")

        # Update document_index for blocks that come after our range
        # They need to shift to make room for the reordered blocks
        if blocks_after:
            shift_amount = len(new_order) - (max_index - min_index + 1)
            if shift_amount != 0:
                for block in blocks_after:
                    block.document_index += shift_amount
                    block.save()
                    print(
                        f"  Shifted block {block.document_index - shift_amount} to {block.document_index}"
                    )

        # Rebuild the linked list connections for the entire document
        # First, clear all prev_block and next_block references
        Blocks.update(prev_block=None, next_block=None).where(
            Blocks.document == document
        ).execute()

        # Get all blocks again in the new order
        all_blocks_updated = (
            Blocks.select()
            .where(Blocks.document == document)
            .order_by(Blocks.document_index)
        ).execute()

        # Rebuild the linked list
        prev_block = None
        for block in all_blocks_updated:
            block.prev_block = prev_block
            block.save()

            if prev_block:
                prev_block.next_block = block
                prev_block.save()

            prev_block = block

        print("✅ Successfully reordered blocks and rebuilt linked list")
        return True

    except Exception as e:
        print(f"❌ Error reordering blocks: {e}")
        return False
    finally:
        if not database.is_closed():
            database.close()


def main():
    parser = argparse.ArgumentParser(
        description="Correct blocks in a document by chapter number"
    )

    # Find the document by chapter
    document = find_document_by_chapter(CHAPTER_NUMBER)
    if not document:
        sys.exit(1)

    # Reorder the blocks
    if reorder_blocks(document, NEW_ORDER):
        print(f"✅ Successfully reordered blocks for Chapter {CHAPTER_NUMBER}")
    else:
        print(f"❌ Failed to reorder blocks for Chapter {CHAPTER_NUMBER}")
        sys.exit(1)


if __name__ == "__main__":
    main()
