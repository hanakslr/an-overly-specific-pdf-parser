"""
Some helper functions for saving and resuming from previous state.
"""

import glob
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime

from langgraph.graph.state import CompiledStateGraph


def get_latest_output(pdf_path: str):
    """Get the latest output JSON file from the pipeline output directory for this specific PDF."""
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = f"output/pipeline/{pdf_name}"
    if not os.path.exists(output_dir):
        return None

    # Find all output JSON files for this PDF
    output_files = glob.glob(f"{output_dir}/output_*.json")
    if not output_files:
        return None

    # Sort by modification time and get the latest
    latest_file = max(output_files, key=os.path.getmtime)

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Could not load latest output: {e}")
        return None


def resume_from_latest(pdf_path: str):
    """Resume pipeline from the latest output for this specific PDF."""
    latest_state = get_latest_output(pdf_path)
    if latest_state:
        print(f"🔄 Resuming from latest output for: {pdf_path}")

        return latest_state
    else:
        print("🆕 Starting fresh pipeline")
        return {"pdf_path": pdf_path}


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        # Handle Pydantic models
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return super().default(obj)


def save_output(pdf_path, final_state):
    # Create PDF-specific output directory
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = f"output/pipeline/{pdf_name}"
    os.makedirs(output_dir, exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{output_dir}/output_{timestamp}.json"

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(
            final_state, f, indent=2, ensure_ascii=False, cls=DataclassJSONEncoder
        )

    return output_filename


def draw_pipeline(graph: CompiledStateGraph):
    # Generate pipeline visualization
    try:
        # Generate Mermaid PNG and save it
        png_bytes = graph.get_graph().draw_mermaid_png()
        png_path = "pipeline_diagram.png"
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        print(f"📊 Pipeline diagram saved to: {png_path}")
    except Exception as e:
        print(f"⚠️ Could not generate pipeline diagram: {e}")
