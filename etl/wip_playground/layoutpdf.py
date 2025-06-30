import argparse
import json
from pathlib import Path

from llmsherpa.readers import LayoutPDFReader


def main():
    parser = argparse.ArgumentParser(
        description="Process a PDF with LayoutPDFReader and save the output as JSON."
    )
    parser.add_argument("input_pdf", help="Path to the input PDF file.")
    args = parser.parse_args()

    output_dir = Path("output/layoutpdf")
    output_dir.mkdir(parents=True, exist_ok=True)

    llmsherpa_api_url = "http://localhost:5010/api/parseDocument?renderFormat=all"
    reader = LayoutPDFReader(llmsherpa_api_url)

    print(f"Processing {args.input_pdf}...")
    doc = reader.read_pdf(args.input_pdf)

    input_filename = Path(args.input_pdf).name
    output_filename = Path(input_filename).stem + ".json"
    output_path = output_dir / output_filename

    print(f"Writing output to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(doc.json, f, indent=4)

    print(f"Successfully processed {args.input_pdf} and saved output to {output_path}")


if __name__ == "__main__":
    main()
