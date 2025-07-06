import os

import fitz  # PyMuPDF


def split_pdf_by_segments(
    pdf_path, segments: list[int], output_dir="input_files/split_chapters"
):
    # Open the PDF
    pdf_document = fitz.open(pdf_path)
    total_pages = pdf_document.page_count

    # Make sure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Add an artificial end marker for the last segment
    for i, segment in enumerate(segments):
        start_page = segment - 1
        if i < len(segments) - 1:
            end_page = segments[i + 1] - 1
        else:
            end_page = total_pages - 1  # PyMuPDF is 0-indexed

        # Create a new PDF for this segment
        output_pdf = fitz.open()
        for page_num in range(start_page, end_page):
            output_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)

        # Save it
        output_filename = os.path.join(output_dir, f"chapter_{i + 1}.pdf")
        output_pdf.save(output_filename)
        output_pdf.close()

    pdf_document.close()
    print(f"Split into {len(segments)} segments in '{output_dir}'")


if __name__ == "__main__":
    segments = [
        22,
        32,
        44,
        52,
        63,
        76,
        92,
        100,
        113,
        125,
        140,
        151,
        163,
        176,
        192,
        203,
        215,
        224,
    ]

    pdf_path = "input_files/whole_plan.pdf"  # replace with your PDF filename
    split_pdf_by_segments(pdf_path, segments)
