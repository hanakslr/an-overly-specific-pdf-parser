import re

from schema.tiptap_models import ImageNode


def insert_images(state):
    """
    After all blocks have been processed, iterate through the pages and insert images
    in the correct positions without reordering the entire document.
    """
    print("🖼️  Inserting images...")
    content = list(state.blocks)

    # First, get the src of all existing images in the document
    existing_image_srcs = {
        node.attrs.src
        for node in content
        if node.type == "image" and node.attrs and node.attrs.src
    }

    image_header = [b for b in content if b.type == "imageHeader"]

    if image_header:
        image_header = image_header[0]
        for img in image_header.content:
            existing_image_srcs.add(img.attrs.src)

    # Create lookups for block information
    block_id_to_page_num = {
        block.id: page.page
        for page in state.zipped_pages
        for block in page.unified_blocks
    }
    block_id_to_block = {
        block.id: block for page in state.zipped_pages for block in page.unified_blocks
    }

    # Gather all images to be inserted that are not already present
    images_to_insert = []
    for page in state.zipped_pages:
        for item in page.pymupdf_page.content:
            if item.type == "image" and item.src not in existing_image_srcs:
                images_to_insert.append(item)

    # Sort images by page and then by vertical position to ensure correct insertion order
    images_to_insert.sort(key=lambda img: (img.page, img.bbox[1]))

    if not images_to_insert:
        print("👍 No new images to insert.")
        return {}  # Return early if there's nothing to do

    for image_item in images_to_insert:
        image_page = image_item.page
        image_y0 = image_item.bbox[1]

        # Find the correct insertion index in the content list
        insertion_index = -1
        for i, node in enumerate(content):
            node_page = -1
            # Check for existing images we may have just inserted
            if node.type == "image" and node.attrs and node.attrs.title:
                try:
                    # e.g., "Page 1 image"
                    node_page = int(node.attrs.title.split(" ")[1])
                except (ValueError, IndexError):
                    pass  # Not an image title we can parse
            elif node.attrs and node.attrs.unified_block_id:
                node_page = block_id_to_page_num.get(node.attrs.unified_block_id, -1)

            if node_page == -1:
                continue  # Cannot determine page for this node

            # If node is on a later page, we've found our insertion spot
            if node_page > image_page:
                insertion_index = i
                break

            if node_page < image_page:
                continue  # Image goes on a later page, so keep searching

            # On the same page, compare vertical position
            # We only use bboxes from fitz items for reliable positioning
            node_y0 = float("inf")  # Default to bottom of page
            if node.attrs and node.attrs.unified_block_id:
                block = block_id_to_block.get(node.attrs.unified_block_id)
                if block and block.fitz_items:
                    node_y0 = block.fitz_items[-1].bbox[1]

            if image_y0 < node_y0:
                insertion_index = i
                break

        image_node = ImageNode(
            attrs=ImageNode.Attrs(
                src=image_item.src,
                alt="An image from the PDF",
                title=f"Page {image_item.page} image",
            )
        )

        if insertion_index != -1:
            content.insert(insertion_index, image_node)
        else:
            # If no spot was found, it belongs at the end
            content.append(image_node)
            insertion_index = len(content) - 1

        # Look ahead for a markdown-style image description and remove it.
        # We check the next few nodes to find any paragraph nodes that match the pattern.
        indices_to_delete = []
        lookahead_distance = 3  # Check the next 3 nodes

        for i in range(1, lookahead_distance + 1):
            check_idx = insertion_index + i
            if check_idx >= len(content):
                break

            node = content[check_idx]
            if node.type == "paragraph":
                if (
                    node.content
                    and hasattr(node.content[0], "text")
                    and node.content[0].text
                ):
                    original_text = node.content[0].text
                    # Find and remove all markdown-style descriptions.
                    # This handles descriptions at the start, middle, or end of text,
                    # as well as multiple descriptions in one block.
                    cleaned_text = re.sub(r"\[.*?\]", "", original_text).strip()

                    # Check if a change was actually made
                    if cleaned_text != original_text.strip():
                        if not cleaned_text:
                            # The entire text consisted of descriptions, so mark the node for deletion.
                            if check_idx not in indices_to_delete:
                                indices_to_delete.append(check_idx)
                        else:
                            # Only part of the text was a description, so update the node.
                            print(
                                f"INFO: Removing image description from text. Original: '{original_text.strip()}', New: '{cleaned_text}'"
                            )
                            node.content[0].text = cleaned_text

        # Remove the nodes marked for deletion.
        if indices_to_delete:
            for idx in sorted(indices_to_delete, reverse=True):
                removed_text = content[idx].content[0].text.strip()
                print(
                    f"INFO: Found and removed potential image description: '{removed_text}'"
                )
                content.pop(idx)

    print(f"Images inserted. {len(content)} blocks total.")
    return {"blocks": content}
