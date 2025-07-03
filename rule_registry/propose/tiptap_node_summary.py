from typing import ForwardRef, List, Literal, Union, get_args, get_origin

from pydantic import BaseModel

import schema.tiptap_models as tiptap_models
from schema.tiptap_models import TiptapNode


# === TYPE GROUP DEFINITIONS ===
def extract_type_group_definitions():
    type_groups = {}
    for name in ["InlineNode", "BlockNode", "ListNode"]:
        if hasattr(tiptap_models, name):
            group = getattr(tiptap_models, name)
            types = get_args(group)
            resolved = []
            for t in types:
                if isinstance(t, str):
                    resolved.append(t)
                elif isinstance(t, ForwardRef):
                    resolved.append(t.__forward_arg__)
                elif hasattr(t, "__name__"):
                    resolved.append(t.__name__)
            type_groups[name] = resolved
    return type_groups


def format_type(annotation) -> str:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is str:
        return "string"
    elif annotation is int:
        return "int"
    elif annotation is float:
        return "float"
    elif annotation is bool:
        return "bool"
    elif annotation is type(None):
        return "null"
    elif isinstance(annotation, ForwardRef):
        return annotation.__forward_arg__
    elif origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return f"Optional[{format_type(non_none[0])}]"
        return " | ".join(format_type(arg) for arg in args)
    elif origin in [list, List]:
        return f"{format_type(args[0])}[]"
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        # Recursively format nested models
        return format_model_fields(annotation)
    elif hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation)


def extract_literal_type(field) -> str:
    origin = get_origin(field.annotation)
    args = get_args(field.annotation)
    if origin is Literal and args:
        return str(args[0])
    return "unknown"


def format_model_fields(model: BaseModel) -> str:
    parts = []
    for field_name, field in model.model_fields.items():
        formatted_type = format_type(field.annotation)
        parts.append(f"{field_name}: {formatted_type}")
    return "{ " + ", ".join(parts) + " }"


def summarize_node_class(cls):
    fields = cls.model_fields
    type_value = "unknown"

    lines = []

    for name, field in fields.items():
        if name == "type":
            type_value = extract_literal_type(field)

    lines.append(f"- {type_value}: {{")

    for name, field in fields.items():
        if name == "type":
            lines.append(f'    type: "{type_value}",')
        else:
            field_type = format_type(field.annotation)
            lines.append(f"    {name}: {field_type},")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]  # Remove trailing comma

    lines.append("}")
    return "\n".join(lines)


# === OUTPUT GLUE ===
def generate_node_types_summary():
    # 1. Group definitions
    group_lines = ["Type groups:"]
    for name, types in extract_type_group_definitions().items():
        group_lines.append(f"- {name} = {' | '.join(types)}")
    group_section = "\n".join(group_lines)

    # 2. Node summaries
    summaries = []
    for cls in sorted(TiptapNode.__subclasses__(), key=lambda c: c.__name__):
        summaries.append(summarize_node_class(cls))
    nodes_section = "\n\n".join(summaries)

    return f"{group_section}\n\n{nodes_section}"


if __name__ == "__main__":
    print(generate_node_types_summary())
