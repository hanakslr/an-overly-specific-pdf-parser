from typing import List, Literal, Optional

from pydantic import BaseModel


class Block(BaseModel):
    def get_text(self) -> Optional[str]:
        """Get the text field"""
        # Leaf nodes usually store their textual value in the `text` attribute.
        text_val = getattr(self, "text", None)
        if isinstance(text_val, str):
            return text_val

        # If this node has children (the `content` field), recursively extract
        # their text values and concatenate them with spaces.  We purposefully
        # keep the implementation very tolerant so that it works for any node
        # structure produced by Tiptap.
        content = getattr(self, "content", None)
        if not content:
            return None

        # Ensure we are always working with an iterable of blocks.
        if not isinstance(content, (list, tuple)):
            content = [content]

        collected: List[str] = []

        for child in content:
            if child is None:
                continue

            # Recursively obtain text from child nodes.
            if isinstance(child, Block):
                child_text = child.get_text()
                if child_text:
                    collected.append(child_text)
            # Sometimes the list can be nested (e.g. tables). Handle that too.
            elif isinstance(child, (list, tuple)):
                for grand_child in child:
                    if isinstance(grand_child, Block):
                        grand_text = grand_child.get_text()
                        if grand_text:
                            collected.append(grand_text)

        if collected:
            return " ".join(collected)

        return None


# # Resolve forward references so that the `content` field properly recognises the
# # `Block` type within the Union definitions.
# Block.update_forward_refs()
# Base class for attributes, includes unified_block_id
class BaseAttrs(BaseModel):
    unified_block_id: Optional[str] = None


class DocNode(Block):
    type: Literal["doc"] = "doc"
    content: List[Block]
    attrs: Optional[BaseAttrs] = None
