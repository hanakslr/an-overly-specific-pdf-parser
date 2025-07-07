import json
from collections import defaultdict

from etl.pymupdf_parse import TextItem
from schema.tiptap_models import CitationNode, HeadingNode, ParagraphNode, TextNode


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

            dominant_style_tuple = max(style_counts, key=style_counts.get)
            font, size = dominant_style_tuple
            current_style = {"font": font, "size": size}

            level = str(node.attrs.level)
            expected_styles = typography["headings"].get(level, [])

            if current_style in expected_styles:
                continue

            # Mismatch detected, try to find a matching level automatically
            matching_levels = []
            for lvl, styles in typography["headings"].items():
                if current_style in styles:
                    matching_levels.append(lvl)

            if len(matching_levels) == 1:
                new_level = matching_levels[0]
                print(
                    f'INFO: Auto-reclassifying text "{node.content[0].text}" from Heading {level} to {new_level}.'
                )
                state.blocks[i].attrs.level = int(new_level)
                continue

            # Could not auto-resolve, prompt user
            print("\n--- POTENTIAL TYPOGRAPHY MISMATCH ---")
            print(f'Text: "{node.content[0].text}"')
            print(f"  - Classified as: Heading {level}")
            print(f"  - Detected Style: font='{font}', size={size}")
            print(f"  - Expected Styles for Level {level}: {expected_styles}")

            if matching_levels:
                print(
                    f"  - This style is ambiguous and matches Heading Level(s): {', '.join(matching_levels)}"
                )

            new_level_str = input(
                "Enter the correct heading level, `p` to correct to a paragraph, or press Enter to keep current: "
            )
            if new_level_str.isdigit():
                new_level = int(new_level_str)
                state.blocks[i].attrs.level = new_level
                print(f"✅ Updated heading level to {new_level}.")

                # Append the new style to the registry for the corrected level
                level_styles = typography["headings"].get(str(new_level), [])
                if current_style not in level_styles:
                    level_styles.append(current_style)
                    typography["headings"][str(new_level)] = level_styles
                    with open("typography.json", "w") as f:
                        json.dump(typography, f, indent=2, sort_keys=True)
                    print(
                        f"✅ Added new style to Heading {new_level} in typography.json."
                    )
            elif new_level_str == "p":
                state.blocks[i] = ParagraphNode(content=state.blocks[i].content)
        elif isinstance(node, ParagraphNode):
            # Are there any citations?
            # Does the unified block fitz items include any
            fitz_items: list[TextItem] = block_id_to_fitz_items.get(
                node.attrs.unified_block_id, []
            )
            if not fitz_items:
                continue

            def get_paragraph_style(font, size):
                for style in typography["paragraphs"]:
                    if (font, size) in [
                        (combo["font"], combo["size"])
                        for combo in typography["paragraphs"][style]
                    ]:
                        return style
                raise Exception(f"Unexptected font style {font}, {size}")

            for item in fitz_items:
                style = get_paragraph_style(item.font, item.size)

                if style == "body":
                    continue
                elif style == "citation":
                    # Check to see if there is a citation block with this text. If there isn't we need to make one
                    if [
                        n
                        for n in node.content
                        if n.type == "citation" and n.attrs.label == item.text
                    ]:
                        print(f"Found matching citation for {item.text}")
                    else:
                        citation_data = [
                            c
                            for c in state.custom_extracted_data.citations
                            if c.label == item.text
                        ]
                        if not citation_data:
                            raise Exception(f"Could not find citation for {item.text}")
                        citation_data = citation_data[0]
                        citation_node = CitationNode(
                            content=[TextNode(text=citation_data.source)],
                            attrs=CitationNode.Attrs(label=item.text),
                        )

                        # Find where to put it.
                        new_children = []
                        for child_node in node.content:
                            # Can either be superscript OR just the number
                            if (
                                child_node.type == "text"
                                and f"<sup>{item.text}</sup>" in child_node.text
                            ):
                                parts = child_node.text.split(f"<sup>{item.text}</sup>")

                                if len(parts) != 2:
                                    raise Exception(
                                        f"Unexpected text format for citation, found {parts=}"
                                    )

                                new_children.extend(
                                    [
                                        TextNode(text=parts[0]),
                                        citation_node,
                                        TextNode(text=parts[1]),
                                    ]
                                )
                            else:
                                new_children.append(child_node)
                        print("Setting new children w citation")
                        node.content = new_children
                else:
                    raise Exception(f"Unexpected style: {style}")

    return {"blocks": state.blocks}
