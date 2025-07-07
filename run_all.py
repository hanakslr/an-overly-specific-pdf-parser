"""
Run pipeline and save for every file in the provided directory.
"""

import os
import sys

from pipeline import process
from pipeline_state_helpers import save_output

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_all.py <input_dir> [--resume-latest]")
        sys.exit(1)

    input_dir = sys.argv[1]
    resume_latest = "--resume-latest" in sys.argv

    # Iterate over every file in the input directory (non-recursive)
    for filename in os.listdir(input_dir):
        file_path = os.path.join(input_dir, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(".pdf"):
            print(f"Processing file: {file_path}")
            process(file_path, resume_latest)
            save_output(file_path)
