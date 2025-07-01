from typing import List, Literal, Optional, Set, Type

from pydantic import BaseModel


def all_subclasses(cls: Type) -> Set[Type]:
    """Recursively find all subclasses of a class."""
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)]
    )


# class BaseModel(PyBaseModel, extra="forbid"):
#     __polymorphic__ = False

#     @classmethod
#     def __get_pydantic_core_schema__(
#         cls,
#         __source: type["PyBaseModel"],
#         __handler: Callable[[Any], core_schema.CoreSchema],
#     ) -> core_schema.CoreSchema:
#         schema = __handler(__source)
#         og_schema_ref = schema["ref"]
#         schema["ref"] += ":aux"

#         return core_schema.no_info_before_validator_function(
#             cls.__convert_to_real_type__, schema=schema, ref=og_schema_ref
#         )

#     @classmethod
#     def __convert_to_real_type__(cls, value: Any):
#         if not cls.__polymorphic__:
#             return value

#         if isinstance(value, dict) is False:
#             return value

#         value = value.copy()

#         subclass = value.pop("type", None)
#         if subclass is None:
#             raise ValueError(f"Missing 'type' in {cls.__name__}")

#         allowable = [dtype for dtype in cls.__subclasses__()]

#         print(f"{allowable=}. looking for {subclass=}")
#         try:
#             sub = next(
#                 dtype
#                 for dtype in all_subclasses(cls)
#                 if getattr(dtype.model_fields.get("type"), "default", None) == subclass
#             )
#         except StopIteration as e:
#             raise TypeError(f"Unsupported subclass: {subclass}") from e

#         return sub(**value)

#     def __init_subclass__(cls, polymorphic: bool = False, **kwargs):
#         cls.__polymorphic__ = polymorphic
#         super().__init_subclass__(**kwargs)


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
