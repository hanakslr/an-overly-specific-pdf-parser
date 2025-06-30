import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# === AST NODES ===
@dataclass
class NodeExpr:
    pass


@dataclass
class NamedNode(NodeExpr):
    name: str
    quantifier: Optional[str] = None


@dataclass
class Sequence(NodeExpr):
    elements: List[NodeExpr]


@dataclass
class Alternation(NodeExpr):
    options: List[NodeExpr]


@dataclass
class Group(NodeExpr):
    expr: NodeExpr
    quantifier: Optional[str] = None


# === TOKENIZER ===
TOKEN_RE = re.compile(r"\w+|[()*+?|]")


def tokenize(expr: str) -> List[str]:
    return TOKEN_RE.findall(expr)


# === PARSER ===
def parse_tokens(tokens: List[str]) -> NodeExpr:
    def parse_expr(index):
        seq = []
        while index < len(tokens):
            token = tokens[index]
            if token == ")":
                break
            elif token == "(":
                inner, index = parse_expr(index + 1)
                if index < len(tokens) and tokens[index] in "*+?":
                    inner = Group(expr=inner, quantifier=tokens[index])
                    index += 1
                seq.append(inner)
            elif token == "|":
                left = Sequence(seq) if len(seq) > 1 else seq[0]
                right, index = parse_expr(index + 1)
                return Alternation([left, right]), index
            else:
                quantifier = None
                if index + 1 < len(tokens) and tokens[index + 1] in "*+?":
                    quantifier = tokens[index + 1]
                    index += 1
                seq.append(NamedNode(name=token, quantifier=quantifier))
            index += 1
        return Sequence(seq) if len(seq) > 1 else seq[0], index + 1

    ast, _ = parse_expr(0)
    return ast


# === PYTHON TYPE TRANSLATION ===
def to_python_type(node: NodeExpr, group_map: dict) -> str:
    if isinstance(node, NamedNode):
        base_type = f"'{node.name.title()}Node'"
        if node.quantifier == "+":
            return f"List[{base_type}]"
        elif node.quantifier == "*":
            return f"Optional[List[{base_type}]]"
        elif node.quantifier == "?":
            return f"Optional[{base_type}]"
        else:
            return base_type
    elif isinstance(node, Group):
        inner = to_python_type(node.expr, group_map)
        if node.quantifier == "+":
            return f"List[{inner}]"
        elif node.quantifier == "*":
            return f"Optional[List[{inner}]]"
        elif node.quantifier == "?":
            return f"Optional[{inner}]"
        else:
            return inner
    elif isinstance(node, Sequence):
        types = [to_python_type(e, group_map) for e in node.elements]
        return f"Tuple[{', '.join(types)}]" if len(types) > 1 else types[0]
    elif isinstance(node, Alternation):
        return f"Union[{', '.join(to_python_type(opt, group_map) for opt in node.options)}]"
    else:
        raise TypeError(f"Unsupported node type: {node}")


# === MAIN ENTRY ===
def parse_content_expr(expr: str | None, group_map: dict) -> str | None:
    if not expr:
        return None
    tokens = tokenize(expr)
    ast = parse_tokens(tokens)
    base_type = to_python_type(ast, group_map)

    # In ProseMirror, content is always an array. Use Tuple for fixed-length sequences:
    if isinstance(ast, NamedNode) and not ast.quantifier:
        # Single node with no quantifier -> single-item Tuple
        return f"Tuple[{base_type}]"
    elif isinstance(ast, Sequence):
        # Check if sequence has any quantifiers (* or +)
        has_quantifiers = any(
            isinstance(elem, NamedNode) and elem.quantifier in ["*", "+"]
            for elem in ast.elements
        )
        if has_quantifiers:
            # Variable-length sequence (like "paragraph actionItem*") -> List[Union[...]]
            unique_types = set()
            for elem in ast.elements:
                if isinstance(elem, NamedNode):
                    unique_types.add(f"'{elem.name.title()}Node'")
            if len(unique_types) > 1:
                return f"List[Union[{', '.join(sorted(unique_types))}]]"
            elif len(unique_types) == 1:
                return f"List[{next(iter(unique_types))}]"
        else:
            # All elements are fixed (no quantifiers) -> keep as Tuple
            all_fixed = all(
                isinstance(elem, NamedNode) and not elem.quantifier
                for elem in ast.elements
            )
            if all_fixed:
                return base_type

    return base_type


# === CODE GENERATOR ===
def python_type_from_default(value):
    if isinstance(value, int):
        return "int"
    elif isinstance(value, str):
        return "str"
    elif value is None:
        return "Optional[str]"
    else:
        return "Optional[Any]"  # fallback, could be improved


def generate_content_validator(content_expr: str) -> str | None:
    """Generate a validator for constrained content expressions like 'paragraph actionItem*'"""
    if not content_expr:
        return None

    tokens = tokenize(content_expr)
    ast = parse_tokens(tokens)

    # Check if this is a sequence with quantifiers
    if isinstance(ast, Sequence):
        has_quantifiers = any(
            isinstance(elem, NamedNode) and elem.quantifier in ["*", "+"]
            for elem in ast.elements
        )
        if has_quantifiers:
            # Generate validator for patterns like "paragraph actionItem*"
            fixed_parts = []
            variable_parts = []

            for elem in ast.elements:
                if isinstance(elem, NamedNode):
                    if not elem.quantifier:
                        fixed_parts.append(elem.name)
                    elif elem.quantifier in ["*", "+"]:
                        variable_parts.append((elem.name, elem.quantifier))

            if len(fixed_parts) == 1 and len(variable_parts) == 1:
                fixed_type = fixed_parts[0]
                var_type, quantifier = variable_parts[0]

                validator_lines = [
                    "    @validator('content')",
                    "    def check_content(cls, v):",
                    "        if not v:",
                ]

                if quantifier == "+":
                    validator_lines.append(
                        '            raise ValueError("content must have at least one child")'
                    )
                else:
                    validator_lines.append("            return v")

                validator_lines.extend(
                    [
                        f"        if v[0].type != '{fixed_type}':",
                        f"            raise ValueError('First child must be a {fixed_type}')",
                        "        for node in v[1:]:",
                        f"            if node.type != '{var_type}':",
                        f"                raise ValueError('Subsequent children must be {var_type}s')",
                        "        return v",
                    ]
                )

                return "\n".join(validator_lines)

    return None


def generate_node_types(schema_json: dict) -> str:
    nodes = schema_json["nodes"]
    group_map: dict[str, List[str]] = {}
    for node_name, spec in nodes.items():
        print(f"Generating {node_name}")
        groups = spec.get("group", None)
        if groups:
            for group in groups.split():
                if group:
                    group_map.setdefault(group, []).append(node_name)

    # Generate base and group types
    lines = [
        "# DO NOT EDIT. This file was automatically generated by generate_prose_mirror_classes.py.",
        "from typing import List, Optional, Union, Tuple, Any",
        "from pydantic import BaseModel, validator",
        "from typing_extensions import Literal",
        "",
    ]
    lines.append("# Common parent class for all Tiptap nodes")
    lines.append("class TiptapNode(BaseModel):\n    pass\n")

    lines.append("# Base class for attributes, includes unified_block_id")
    lines.append("class BaseAttrs(BaseModel):")
    lines.append("    unified_block_id: Optional[str] = None")
    lines.append("")

    for group, names in group_map.items():
        lines.append(
            f"{group.title()}Node = Union["
            + ", ".join(f"'{n.title()}Node'" for n in sorted(names))
            + "]"
        )
    lines.append("")

    # Generate node classes
    for node_name, spec in nodes.items():
        typename = f"{node_name.title()}Node"
        content_expr = spec.get("content")
        content_type = parse_content_expr(content_expr, group_map)

        lines.append(f"class {typename}(TiptapNode):")
        lines.append(f'    type: Literal["{node_name}"] = "{node_name}"')
        if content_type:
            lines.append(f"    content: {content_type}")

        # Generate content validator for constrained sequences
        content_validator = generate_content_validator(content_expr)
        if content_validator:
            lines.append("")
            lines.append(content_validator)

        # This is a special case.
        if node_name == "text":
            lines.append("    text: str")

        attrs = spec.get("attrs", {})
        if attrs:
            lines.append("")
            lines.append("    class Attrs(BaseAttrs):")
            for attr_name, attr_info in attrs.items():
                default_val = attr_info.get("default")
                py_type = python_type_from_default(default_val)
                if default_val is None:
                    # The default is None, so the type should be Optional.
                    # python_type_from_default returns Optional[str] for None.
                    lines.append(f"        {attr_name}: {py_type} = None")
                else:
                    repr_val = repr(default_val)
                    # For other defaults, we can still allow the attribute to be None.
                    lines.append(
                        f"        {attr_name}: Optional[{py_type}] = {repr_val}"
                    )
            lines.append("")
            lines.append("    attrs: Optional[Attrs] = None")
        else:
            lines.append("    attrs: Optional[BaseAttrs] = None")

        lines.append("")

    return "\n".join(lines)


# === USAGE EXAMPLE ===
if __name__ == "__main__":
    schema_path = Path("tiptap/editor_schema.json")
    schema = json.loads(schema_path.read_text())
    output = generate_node_types(schema)
    with open("tiptap/tiptap_models.py", "w") as f:
        f.write(output)
    print("✅ Type definitions written to tiptap_models.py")
