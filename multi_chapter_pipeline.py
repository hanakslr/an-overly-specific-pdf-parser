#!/usr/bin/env python3
"""
Multi-Chapter Pipeline Orchestrator

This script handles the detection and processing of multi-chapter PDFs by:
1. Detecting chapters using PyMuPDF font/size criteria
2. Getting user approval for detected chapters
3. Extracting individual chapter PDFs
4. Running the main pipeline.py for each chapter
5. Combining and organizing the results

Usage:
    python multi_chapter_pipeline.py document.pdf
    python multi_chapter_pipeline.py document.pdf --chapter-only chapter_1_Introduction
    python multi_chapter_pipeline.py document.pdf --list-chapters
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from etl.chapter_detection import (
    detect_chapter_headers, 
    get_user_approval, 
    ChapterDetectionResult,
    ChapterRange
)
from etl.pdf_chapter_extractor import extract_all_approved_chapters
from tiptap.tiptap_models import DocNode


@dataclass
class ChapterResult:
    """Result of processing a single chapter"""
    chapter: ChapterRange
    chapter_pdf_path: str
    output_file: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None


@dataclass
class MultiChapterResult:
    """Result of processing all chapters"""
    original_pdf: str
    chapters: List[ChapterResult]
    combined_output_file: Optional[str] = None
    detection_result: Optional[ChapterDetectionResult] = None


def run_single_chapter_pipeline(chapter_pdf_path: str, resume: bool = False) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Run the main pipeline.py for a single chapter PDF.
    
    Returns:
        tuple: (success, output_file_path, error_message)
    """
    try:
        cmd = ["python", "pipeline.py", chapter_pdf_path]
        if resume:
            cmd.append("--resume-latest")
        
        print(f"🔄 Running pipeline for: {chapter_pdf_path}")
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        # Parse output to find the output file path
        output_file = None
        for line in result.stdout.split('\n'):
            if 'Output saved to:' in line:
                output_file = line.split('Output saved to:')[-1].strip()
                break
        
        return True, output_file, None
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Pipeline failed: {e.stderr}"
        print(f"❌ Pipeline failed for {chapter_pdf_path}: {error_msg}")
        return False, None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ Unexpected error for {chapter_pdf_path}: {error_msg}")
        return False, None, error_msg


def combine_chapter_outputs(chapter_results: List[ChapterResult], output_dir: str) -> Optional[str]:
    """
    Combine all chapter outputs into a single document.
    
    Args:
        chapter_results: List of successfully processed chapters
        output_dir: Directory to save combined output
    
    Returns:
        Path to combined output file
    """
    successful_chapters = [c for c in chapter_results if c.success and c.output_file]
    
    if not successful_chapters:
        print("❌ No successful chapters to combine")
        return None
    
    print(f"📖 Combining {len(successful_chapters)} chapter outputs...")
    
    combined_content = []
    combined_metadata = {
        "chapters": [],
        "original_pdf": chapter_results[0].chapter.header.text if chapter_results else "unknown",
        "total_chapters": len(successful_chapters)
    }
    
    for chapter_result in successful_chapters:
        try:
            # Load chapter output
            if not chapter_result.output_file:
                continue
            
            with open(chapter_result.output_file, 'r') as f:
                chapter_data = json.load(f)
            
            # Extract prose mirror content
            if 'prose_mirror_doc' in chapter_data and chapter_data['prose_mirror_doc']:
                doc_content = chapter_data['prose_mirror_doc'].get('content', [])
                combined_content.extend(doc_content)
            
            # Add chapter metadata
            combined_metadata["chapters"].append({
                "title": chapter_result.chapter.title,
                "chapter_number": chapter_result.chapter.chapter_number,
                "pages": f"{chapter_result.chapter.start_page}-{chapter_result.chapter.end_page}",
                "output_file": chapter_result.output_file
            })
            
        except Exception as e:
            print(f"⚠️ Failed to load output for {chapter_result.chapter.title}: {e}")
    
    # Create combined document
    combined_doc = {
        "prose_mirror_doc": {
            "type": "doc",
            "content": combined_content
        },
        "metadata": combined_metadata
    }
    
    # Save combined output
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_filename = f"combined_output_{timestamp}.json"
    combined_path = os.path.join(output_dir, combined_filename)
    
    with open(combined_path, 'w') as f:
        json.dump(combined_doc, f, indent=2)
    
    print(f"✅ Combined output saved to: {combined_path}")
    return combined_path


def process_multi_chapter_pdf(
    pdf_path: str, 
    chapter_only: Optional[str] = None,
    resume: bool = False
) -> MultiChapterResult:
    """
    Main orchestrator function for multi-chapter PDF processing.
    
    Args:
        pdf_path: Path to the original PDF
        chapter_only: If specified, only process this specific chapter
        resume: Whether to resume existing pipeline states
    
    Returns:
        MultiChapterResult with processing results
    """
    result = MultiChapterResult(
        original_pdf=pdf_path,
        chapters=[],
        detection_result=None
    )
    
    try:
        # Step 1: Detect chapters
        print("🔍 Detecting chapters...")
        detection_result = detect_chapter_headers(pdf_path)
        result.detection_result = detection_result
        
        if not detection_result.detected_chapters:
            print("❌ No chapters detected. Consider using single-chapter pipeline.py directly.")
            return result
        
        # Step 2: Get user approval (unless processing specific chapter)
        if not chapter_only:
            detection_result = get_user_approval(detection_result)
        
        approved_chapters = [c for c in detection_result.detected_chapters if c.approved]
        if not approved_chapters:
            print("❌ No chapters approved for processing.")
            return result
        
        # Step 3: Extract chapter PDFs
        print("📄 Extracting chapter PDFs...")
        extracted_chapters = extract_all_approved_chapters(pdf_path, approved_chapters)
        
        # Step 4: Process each chapter (or just the specified one)
        for chapter_range, chapter_pdf_path in extracted_chapters:
            chapter_id = f"chapter_{chapter_range.chapter_number or 'unknown'}_{chapter_range.title.replace(' ', '_')}"
            
            # Skip if processing only specific chapter
            if chapter_only and chapter_only != chapter_id:
                continue
            
            chapter_result = ChapterResult(
                chapter=chapter_range,
                chapter_pdf_path=chapter_pdf_path
            )
            
            # Run pipeline for this chapter
            success, output_file, error = run_single_chapter_pipeline(
                chapter_pdf_path, 
                resume=resume
            )
            
            chapter_result.success = success
            chapter_result.output_file = output_file
            chapter_result.error_message = error
            
            result.chapters.append(chapter_result)
            
            if success:
                print(f"✅ Completed chapter: {chapter_range.title}")
            else:
                print(f"❌ Failed chapter: {chapter_range.title}")
        
        # Step 5: Combine outputs (if not processing single chapter)
        if not chapter_only and result.chapters:
            output_dir = f"output/pipeline/{Path(pdf_path).stem}"
            combined_output = combine_chapter_outputs(result.chapters, output_dir)
            result.combined_output_file = combined_output
        
        return result
        
    except Exception as e:
        print(f"❌ Multi-chapter processing failed: {e}")
        return result


def list_existing_chapters(pdf_path: str):
    """List existing chapter PDFs and outputs for a given PDF."""
    base_name = Path(pdf_path).stem
    chapters_dir = f"output/chapters/{base_name}"
    pipeline_dir = f"output/pipeline/{base_name}"
    
    print(f"📚 Existing chapters for: {pdf_path}")
    print("-" * 60)
    
    # List extracted chapter PDFs
    if os.path.exists(chapters_dir):
        chapter_files = [f for f in os.listdir(chapters_dir) if f.endswith('.pdf')]
        print(f"📄 Extracted chapter PDFs ({len(chapter_files)}):")
        for chapter_file in sorted(chapter_files):
            print(f"  - {chapter_file}")
    else:
        print("📄 No extracted chapter PDFs found")
    
    print()
    
    # List pipeline outputs
    if os.path.exists(pipeline_dir):
        output_files = [f for f in os.listdir(pipeline_dir) if f.endswith('.json')]
        print(f"📊 Pipeline outputs ({len(output_files)}):")
        for output_file in sorted(output_files):
            print(f"  - {output_file}")
    else:
        print("📊 No pipeline outputs found")


def main():
    if len(sys.argv) < 2:
        print("Usage: python multi_chapter_pipeline.py <pdf_path> [options]")
        print("Options:")
        print("  --chapter-only <id>     Process only the specified chapter")
        print("  --list-chapters         List existing chapters and outputs")
        print("  --resume                Resume existing pipeline states")
        print()
        print("Examples:")
        print("  python multi_chapter_pipeline.py document.pdf")
        print("  python multi_chapter_pipeline.py document.pdf --chapter-only chapter_1_Introduction")
        print("  python multi_chapter_pipeline.py document.pdf --list-chapters")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    chapter_only = None
    list_chapters = "--list-chapters" in sys.argv
    resume = "--resume" in sys.argv
    
    if "--chapter-only" in sys.argv:
        idx = sys.argv.index("--chapter-only")
        if idx + 1 < len(sys.argv):
            chapter_only = sys.argv[idx + 1]
    
    # Handle list chapters
    if list_chapters:
        list_existing_chapters(pdf_path)
        return
    
    # Process multi-chapter PDF
    print(f"🚀 Starting multi-chapter processing for: {pdf_path}")
    
    if chapter_only:
        print(f"🎯 Processing only chapter: {chapter_only}")
    
    result = process_multi_chapter_pdf(
        pdf_path=pdf_path,
        chapter_only=chapter_only,
        resume=resume
    )
    
    # Print summary
    print("\n" + "="*60)
    print("📊 PROCESSING SUMMARY")
    print("="*60)
    
    successful = [c for c in result.chapters if c.success]
    failed = [c for c in result.chapters if not c.success]
    
    print(f"✅ Successful chapters: {len(successful)}")
    print(f"❌ Failed chapters: {len(failed)}")
    
    if successful:
        print("\n✅ Successful chapters:")
        for chapter in successful:
            print(f"  - {chapter.chapter.title} -> {chapter.output_file}")
    
    if failed:
        print("\n❌ Failed chapters:")
        for chapter in failed:
            print(f"  - {chapter.chapter.title}: {chapter.error_message}")
    
    if result.combined_output_file:
        print(f"\n📖 Combined output: {result.combined_output_file}")
    
    print("\n🎉 Multi-chapter processing complete!")


if __name__ == "__main__":
    main()