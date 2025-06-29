from tiptap.tiptap_models import ImageNode


def insert_images(state):
    """
    After all blocks have been processed, iterate through the pages and insert images
    in the correct positions without reordering the entire document.
    """
    print("🖼️ Inserting images...")
    content = list(state.prose_mirror_doc.content)

    # First, get the src of all existing images in the document
    existing_image_srcs = {
        node.attrs.src
        for node in content
        if node.type == "image" and node.attrs and node.attrs.src
    }

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
                    node_y0 = block.fitz_items[0].bbox[1]

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

    return {
        "prose_mirror_doc": state.prose_mirror_doc.model_copy(
            update={"content": content}
        )
    }
