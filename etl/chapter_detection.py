import re
from typing import List, Optional
import pymupdf
from pydantic import BaseModel
from etl.pymupdf_parse import TextItem, extract_structured_content


class ChapterHeader(BaseModel):
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    chapter_number: Optional[int] = None
    chapter_title: str = ""


class ChapterRange(BaseModel):
    chapter_number: Optional[int]
    title: str
    start_page: int
    end_page: int
    header: ChapterHeader
    approved: bool = False


class ChapterDetectionResult(BaseModel):
    pdf_path: str
    total_pages: int
    detected_chapters: List[ChapterRange]


def detect_chapter_headers(pdf_path: str) -> ChapterDetectionResult:
    """
    Detect chapter headers by finding text with font='BumperSticker', size=28,
    and containing a number and string pattern.
    """
    # Extract structured content to get text items with font information
    pages = extract_structured_content(pdf_path)
    
    # Get total pages
    doc = pymupdf.open(pdf_path)
    total_pages = doc.page_count
    doc.close()
    
    chapter_headers = []
    
    for page in pages:
        for item in page.content:
            if (isinstance(item, TextItem) and 
                item.font == "BumperSticker" and 
                item.size == 28):
                
                # Check if text contains a number and string pattern
                text = item.text.strip()
                if is_chapter_header_text(text):
                    header = ChapterHeader(
                        page=item.page,
                        text=text,
                        bbox=item.bbox
                    )
                    
                    # Try to extract chapter number and title
                    chapter_number, chapter_title = parse_chapter_text(text)
                    header.chapter_number = chapter_number
                    header.chapter_title = chapter_title
                    
                    chapter_headers.append(header)
    
    # Convert headers to chapter ranges
    chapter_ranges = create_chapter_ranges(chapter_headers, total_pages)
    
    return ChapterDetectionResult(
        pdf_path=pdf_path,
        total_pages=total_pages,
        detected_chapters=chapter_ranges
    )


def is_chapter_header_text(text: str) -> bool:
    """
    Check if text matches the pattern of a chapter header (contains number and string).
    """
    # Look for patterns like "1 Introduction", "Chapter 2: Title", "2. Some Title", etc.
    patterns = [
        r'\d+\s+\w+',  # "1 Introduction"
        r'Chapter\s+\d+',  # "Chapter 1"
        r'\d+\.\s*\w+',  # "1. Title"
        r'\d+:\s*\w+',  # "1: Title"
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def parse_chapter_text(text: str) -> tuple[Optional[int], str]:
    """
    Parse chapter text to extract chapter number and title.
    """
    # Try to extract chapter number
    number_match = re.search(r'\d+', text)
    chapter_number = int(number_match.group()) if number_match else None
    
    # Extract title by removing common chapter prefixes
    title = text
    title = re.sub(r'^Chapter\s+\d+[:\-\s]*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^\d+[:\.\-\s]*', '', title)
    title = title.strip()
    
    return chapter_number, title


def create_chapter_ranges(headers: List[ChapterHeader], total_pages: int) -> List[ChapterRange]:
    """
    Convert detected headers into chapter ranges with start and end pages.
    """
    if not headers:
        return []
    
    # Sort headers by page number
    headers.sort(key=lambda h: h.page)
    
    ranges = []
    for i, header in enumerate(headers):
        start_page = header.page
        
        # End page is the page before the next chapter starts, or the last page
        if i + 1 < len(headers):
            end_page = headers[i + 1].page - 1
        else:
            end_page = total_pages
        
        chapter_range = ChapterRange(
            chapter_number=header.chapter_number,
            title=header.chapter_title or f"Chapter {header.chapter_number or i + 1}",
            start_page=start_page,
            end_page=end_page,
            header=header
        )
        ranges.append(chapter_range)
    
    return ranges


def print_chapter_detection_summary(result: ChapterDetectionResult):
    """
    Print a summary of detected chapters for user review.
    """
    print(f"\n📖 Chapter Detection Results for: {result.pdf_path}")
    print(f"Total pages: {result.total_pages}")
    print(f"Detected chapters: {len(result.detected_chapters)}")
    print("-" * 60)
    
    for i, chapter in enumerate(result.detected_chapters):
        status = "✅ Approved" if chapter.approved else "⏳ Pending"
        print(f"{i + 1}. {chapter.title}")
        print(f"   Pages: {chapter.start_page} - {chapter.end_page}")
        print(f"   Header text: '{chapter.header.text}'")
        print(f"   Status: {status}")
        print()


def get_user_approval(result: ChapterDetectionResult) -> ChapterDetectionResult:
    """
    Interactive function to get user approval for detected chapters.
    """
    print_chapter_detection_summary(result)
    
    print("📝 Chapter Approval")
    print("Commands:")
    print("  - 'a' or 'all': Approve all chapters")
    print("  - '1,2,3': Approve specific chapters by number")
    print("  - 'q' or 'quit': Quit without approval")
    print()
    
    while True:
        user_input = input("Enter your choice: ").strip().lower()
        
        if user_input in ['q', 'quit']:
            print("❌ Exiting without approval")
            return result
        
        if user_input in ['a', 'all']:
            for chapter in result.detected_chapters:
                chapter.approved = True
            print("✅ All chapters approved")
            break
        
        # Parse comma-separated chapter numbers
        try:
            chapter_nums = [int(x.strip()) for x in user_input.split(',')]
            valid_nums = []
            
            for num in chapter_nums:
                if 1 <= num <= len(result.detected_chapters):
                    result.detected_chapters[num - 1].approved = True
                    valid_nums.append(num)
                else:
                    print(f"❌ Invalid chapter number: {num}")
            
            if valid_nums:
                print(f"✅ Approved chapters: {', '.join(map(str, valid_nums))}")
                break
            
        except ValueError:
            print("❌ Invalid input. Please enter numbers separated by commas, 'all', or 'quit'")
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python chapter_detection.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    result = detect_chapter_headers(pdf_path)
    result = get_user_approval(result)
    
    approved_chapters = [c for c in result.detected_chapters if c.approved]
    print(f"\n🎉 {len(approved_chapters)} chapters approved for processing")