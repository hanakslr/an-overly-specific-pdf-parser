import os
import tempfile
from typing import List
import pymupdf
from etl.chapter_detection import ChapterRange


def extract_chapter_pages(pdf_path: str, chapter: ChapterRange, output_dir: str | None = None) -> str:
    """
    Extract pages for a specific chapter from the PDF and save as a new PDF file.
    
    Args:
        pdf_path: Path to the original PDF
        chapter: ChapterRange object defining the pages to extract
        output_dir: Directory to save extracted chapter (defaults to temp dir)
    
    Returns:
        Path to the extracted chapter PDF
    """
    if output_dir is None:
        output_dir = tempfile.gettempdir()
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename
    safe_title = "".join(c for c in chapter.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title.replace(' ', '_')
    
    output_filename = f"chapter_{chapter.chapter_number or 'unknown'}_{safe_title}.pdf"
    output_path = os.path.join(output_dir, output_filename)
    
    # Open source PDF
    doc = pymupdf.open(pdf_path)
    
    # Create new document with only the chapter pages
    chapter_doc = pymupdf.open()
    
    # Insert pages (PyMuPDF uses 0-based indexing, but our pages are 1-based)
    start_idx = chapter.start_page - 1
    end_idx = chapter.end_page - 1
    
    chapter_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx)
    
    # Save the chapter PDF
    chapter_doc.save(output_path)
    
    # Close documents
    chapter_doc.close()
    doc.close()
    
    return output_path


def extract_all_approved_chapters(pdf_path: str, chapters: List[ChapterRange], base_output_dir: str | None = None) -> List[tuple[ChapterRange, str]]:
    """
    Extract all approved chapters from a PDF.
    
    Args:
        pdf_path: Path to the original PDF
        chapters: List of ChapterRange objects
        base_output_dir: Base directory for outputs
    
    Returns:
        List of tuples (chapter, extracted_pdf_path) for approved chapters
    """
    if base_output_dir is None:
        base_output_dir = f"output/chapters/{os.path.basename(pdf_path)}"
    
    os.makedirs(base_output_dir, exist_ok=True)
    
    extracted_chapters = []
    
    for chapter in chapters:
        if chapter.approved:
            try:
                chapter_pdf_path = extract_chapter_pages(pdf_path, chapter, base_output_dir)
                extracted_chapters.append((chapter, chapter_pdf_path))
                print(f"✅ Extracted: {chapter.title} -> {chapter_pdf_path}")
            except Exception as e:
                print(f"❌ Failed to extract {chapter.title}: {e}")
    
    return extracted_chapters


if __name__ == "__main__":
    import sys
    from etl.chapter_detection import detect_chapter_headers, get_user_approval
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_chapter_extractor.py <pdf_path> [output_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Detect chapters
    result = detect_chapter_headers(pdf_path)
    result = get_user_approval(result)
    
    # Extract approved chapters
    extracted = extract_all_approved_chapters(pdf_path, result.detected_chapters, output_dir)
    
    print(f"\n🎉 Successfully extracted {len(extracted)} chapters")