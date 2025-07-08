from typing import List, Optional, Tuple, Union

from pydantic import validator, BaseModel
from typing_extensions import Literal

from schema.block import BaseAttrs, Block


# Common parent class for all Tiptap nodes
class TiptapNode(Block):
    pass


BlockNode = Union[
    "BlockquoteNode",
    "BulletlistNode",
    "CodeblockNode",
    "HeadingNode",
    "HorizontalruleNode",
    "ImageNode",
    "ImageheaderNode",
    "OrderedlistNode",
    "ParagraphNode",
    "TableNode",
]
ListNode = Union["BulletlistNode", "OrderedlistNode"]
InlineNode = Union["HardbreakNode", "TextNode", "CitationNode"]


class ParagraphNode(Block):
    type: Literal["paragraph"] = "paragraph"
    content: List["InlineNode"]

    class Attrs(BaseAttrs):
        style: Optional[str] = None

    attrs: Attrs = Attrs()


class BlockquoteNode(Block):
    type: Literal["blockquote"] = "blockquote"
    content: List["BlockNode"]
    attrs: Optional[BaseAttrs] = None


class BulletlistNode(Block):
    type: Literal["bulletList"] = "bulletList"
    content: List["ListitemNode"]
    attrs: Optional[BaseAttrs] = None


class CodeblockNode(Block):
    type: Literal["codeBlock"] = "codeBlock"
    content: List["TextNode"]

    class Attrs(BaseAttrs):
        language: Optional[str] = None

    attrs: Attrs = Attrs()


class HardbreakNode(Block):
    type: Literal["hardBreak"] = "hardBreak"
    attrs: Optional[BaseAttrs] = None


class HeadingNode(Block):
    type: Literal["heading"] = "heading"
    content: List["InlineNode"]

    class Attrs(BaseAttrs):
        level: int = 1

    attrs: Attrs


class HorizontalruleNode(Block):
    type: Literal["horizontalRule"] = "horizontalRule"
    attrs: Optional[BaseAttrs] = None


class ListitemNode(Block):
    type: Literal["listItem"] = "listItem"
    content: List[Union["BlockNode", "ParagraphNode"]]

    @validator("content")
    def check_content(cls, v):
        if not v:
            return v
        if v[0].type != "paragraph":
            raise ValueError("First child must be a paragraph")
        for node in v[1:]:
            if node.type != "block":
                raise ValueError("Subsequent children must be blocks")
        return v

    attrs: Optional[BaseAttrs] = None


class OrderedlistNode(Block):
    type: Literal["orderedList"] = "orderedList"
    content: List["ListitemNode"]

    class Attrs(BaseAttrs):
        start: int = 1
        type: Optional[str] = None

    attrs: Attrs = Attrs()


class TextNode(Block):
    type: Literal["text"] = "text"
    text: str

    class Attrs(BaseModel):
        style: Optional[str] = None

    attrs: Attrs = Attrs()


class CitationNode(Block):
    type: Literal["citation"] = "citation"
    content: List[TextNode]  # This is the citation itself

    class Attrs(BaseAttrs):
        label: str  # This is how it appears inline

    attrs: Attrs


class ImageNode(Block):
    type: Literal["image"] = "image"

    class Attrs(BaseAttrs):
        src: str
        alt: Optional[str] = None
        title: Optional[str] = None
        caption: Optional[str] = None

    attrs: Attrs


class TableNode(Block):
    type: Literal["table"] = "table"
    content: List["TablerowNode"]

    class Attrs(BaseAttrs):
        caption: Optional[str] = None

    attrs: Attrs = Attrs()

    def get_text(self) -> Optional[str]:
        return "\n".join([child.get_text() for child in self.content])


class TablerowNode(Block):
    type: Literal["tableRow"] = "tableRow"
    content: List[Union["TablecellNode", "TableheaderNode"]]
    attrs: Optional[BaseAttrs] = None

    def get_text(self) -> Optional[str]:
        return " | ".join([child.get_text() for child in self.content])


class TablecellNode(Block):
    type: Literal["tableCell"] = "tableCell"
    content: List["BlockNode"]

    class Attrs(BaseAttrs):
        colspan: Optional[int] = 1
        rowspan: Optional[int] = 1
        colwidth: Optional[str] = None

    attrs: Attrs = Attrs()


class TableheaderNode(Block):
    type: Literal["tableHeader"] = "tableHeader"
    content: List["BlockNode"]

    class Attrs(BaseAttrs):
        colspan: Optional[int] = 1
        rowspan: Optional[int] = 1
        colwidth: Optional[str] = None

    attrs: Attrs = Attrs()


class ImageheaderNode(Block):
    type: Literal["imageHeader"] = "imageHeader"
    content: Tuple["ImageNode", "ImageNode", "ImageNode"]
    attrs: Optional[BaseAttrs] = None
