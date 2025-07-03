import json
from collections import defaultdict

from etl.pymupdf_parse import TextItem
from schema.tiptap_models import HeadingNode


def typography_check(state):
    """
    Analyzes heading nodes to build a typography registry and flags inconsistencies.
    """
    print("🔬 Running Typography Check...")

    # Load existing typography rules
    try:
        with open("typography.json", "r") as f:
            typography = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        typography = {"headings": {}, "paragraphs": {}}

    # Create a map of unified_block_id to fitz_items for quick lookup
    block_id_to_fitz_items = {}
    for page in state.zipped_pages:
        for block in page.unified_blocks:
            block_id_to_fitz_items[block.id] = block.fitz_items

    # # Analyze styles of existing heading nodes
    # heading_styles = defaultdict(lambda: defaultdict(int))
    # for node in state.blocks:
    #     if isinstance(node, HeadingNode):
    #         fitz_items = block_id_to_fitz_items.get(node.attrs.unified_block_id, [])
    #         if not fitz_items:
    #             continue

    #         style_counts = defaultdict(int)
    #         for item in fitz_items:
    #             if isinstance(item, TextItem):
    #                 style = (item.font, item.size)
    #                 style_counts[style] += len(item.text)

    #         if style_counts:
    #             dominant_style = max(style_counts, key=style_counts.get)
    #             heading_styles[node.attrs.level][dominant_style] += 1

    # # Update typography registry with the most common style for each level
    # for level, styles in heading_styles.items():
    #     if styles:
    #         most_common_style = max(styles, key=styles.get)
    #         typography["headings"][str(level)] = {
    #             "font": most_common_style[0],
    #             "size": most_common_style[1],
    #         }

    # # Save the updated registry
    # with open("typography.json", "w") as f:
    #     json.dump(typography, f, indent=2, sort_keys=True)
    # print("✅ Typography registry updated.")

    # Re-check nodes against the new registry and flag inconsistencies
    for i, node in enumerate(state.blocks):
        if isinstance(node, HeadingNode):
            fitz_items = block_id_to_fitz_items.get(node.attrs.unified_block_id, [])
            if not fitz_items:
                continue

            style_counts = defaultdict(int)
            for item in fitz_items:
                if isinstance(item, TextItem):
                    style = (item.font, item.size)
                    style_counts[style] += len(item.text)

            if not style_counts:
                continue

            dominant_style = max(style_counts, key=style_counts.get)
            font, size = dominant_style

            level = str(node.attrs.level)
            expected_style = typography["headings"].get(level)

            if expected_style and (
                expected_style["font"] != font or expected_style["size"] != size
            ):
                print("\n--- POTENTIAL TYPOGRAPHY MISMATCH ---")
                print(f'Text: "{node.content[0].text}"')
                print(f"  - Classified as: Heading {level}")
                print(f"  - Detected Style: font='{font}', size={size}")
                print(
                    f"  - Expected Style: font='{expected_style['font']}', size={expected_style['size']}"
                )

                # Find potential matching levels
                matching_levels = []
                for lvl, style in typography["headings"].items():
                    if style["font"] == font and style["size"] == size:
                        matching_levels.append(lvl)

                if matching_levels:
                    print(
                        f"  - This style matches Heading Level(s): {', '.join(matching_levels)}"
                    )

                new_level_str = input(
                    "Enter the correct heading level, or press Enter to keep current: "
                )
                if new_level_str.isdigit():
                    state.blocks[i].attrs.level = int(new_level_str)
                    print(f"✅ Updated heading level to {new_level_str}.")

    return {"blocks": state.blocks}
