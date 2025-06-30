# Multi-Chapter Pipeline Guide

This guide explains the new multi-chapter functionality that allows processing entire PDFs by automatically detecting and extracting individual chapters using a clean separation of concerns architecture.

## Overview

The multi-chapter system consists of two main components:

1. **`pipeline.py`** - The original single-document pipeline (unchanged)
2. **`multi_chapter_pipeline.py`** - New orchestrator script that handles:
   - **Automatic chapter detection** using PyMuPDF to find chapter headers with specific font criteria
   - **Interactive chapter approval** allowing users to review and approve detected chapters
   - **Individual chapter processing** by calling `pipeline.py` for each chapter
   - **Chapter rerun capability** to reprocess specific chapters
   - **Combined output** merging all processed chapters into a final document

## Architecture Benefits

- **Clean separation of concerns**: `pipeline.py` stays focused on single document processing
- **No complexity added to core pipeline**: Multi-chapter logic is completely isolated
- **Independent chapter processing**: Each chapter runs in its own pipeline instance
- **Easy testing and debugging**: Can test single chapters or the orchestrator separately
- **Backward compatibility**: Existing single-document workflows unchanged

## Chapter Detection Criteria

The system detects chapter headers by looking for text with:
- **Font**: `BumperSticker`
- **Size**: `28`
- **Content**: Text containing a number and string pattern (e.g., "1 Introduction", "Chapter 2: Title")

## Usage

### Single Document Processing (Original)

```bash
# Process a single document or chapter
python pipeline.py your_document.pdf

# Resume from latest saved state
python pipeline.py your_document.pdf --resume-latest
```

### Multi-Chapter Processing (New)

```bash
# Detect and process all chapters
python multi_chapter_pipeline.py your_document.pdf

# List existing chapters and outputs
python multi_chapter_pipeline.py your_document.pdf --list-chapters

# Process only a specific chapter
python multi_chapter_pipeline.py your_document.pdf --chapter-only chapter_1_Introduction

# Resume existing pipeline states
python multi_chapter_pipeline.py your_document.pdf --resume
```

### Chapter Approval Process

When using `multi_chapter_pipeline.py`, you'll see an interactive prompt:

```
📖 Chapter Detection Results for: your_document.pdf
Total pages: 150
Detected chapters: 5
------------------------------------------------------------
1. Introduction
   Pages: 1 - 25
   Header text: '1 Introduction'
   Status: ⏳ Pending

2. Methods
   Pages: 26 - 50
   Header text: '2 Methods'
   Status: ⏳ Pending

[... more chapters ...]

📝 Chapter Approval
Commands:
  - 'a' or 'all': Approve all chapters
  - '1,2,3': Approve specific chapters by number
  - 'q' or 'quit': Quit without approval

Enter your choice:
```

**Approval options:**
- `a` or `all`: Approve all detected chapters
- `1,2,3`: Approve specific chapters by number (comma-separated)
- `q` or `quit`: Exit without processing chapters

## Multi-Chapter Processing Flow

1. **Chapter Detection**: `multi_chapter_pipeline.py` analyzes PDF for chapter headers
2. **Chapter Approval**: User reviews and approves detected chapters
3. **Chapter Extraction**: Individual chapter PDFs are created
4. **Chapter Processing**: For each approved chapter:
   - `pipeline.py` is called with the chapter PDF
   - Complete single-document pipeline runs
   - Output is saved independently
5. **Output Combination**: All chapter outputs are merged into a combined document

## New Components

### Chapter Detection (`etl/chapter_detection.py`)
- Detects chapter headers using PyMuPDF
- Analyzes font, size, and text patterns
- Provides interactive approval interface

### PDF Chapter Extractor (`etl/pdf_chapter_extractor.py`)
- Extracts page ranges as separate PDF files
- Organizes extracted chapters in `output/chapters/`

### Multi-Chapter Orchestrator (`multi_chapter_pipeline.py`)
- Main orchestrator script
- Manages the entire multi-chapter workflow
- Calls `pipeline.py` for individual chapters
- Combines and organizes results

### File Organization

Extracted chapters and outputs are organized as:

```
output/
├── chapters/
│   └── your_document.pdf/
│       ├── chapter_1_Introduction.pdf
│       ├── chapter_2_Methods.pdf
│       └── chapter_3_Results.pdf
└── pipeline/
    └── your_document.pdf/
        ├── output_timestamp.json  # Combined output
        ├── chapter_1_Introduction_timestamp.json
        ├── chapter_2_Methods_timestamp.json
        └── chapter_3_Results_timestamp.json
```

## Key Features

### Chapter Reprocessing

You can reprocess individual chapters without affecting others:

```bash
# List available chapters and outputs
python multi_chapter_pipeline.py document.pdf --list-chapters

# Reprocess a specific chapter
python multi_chapter_pipeline.py document.pdf --chapter-only chapter_2_Methods

# Reprocess with resume
python multi_chapter_pipeline.py document.pdf --chapter-only chapter_2_Methods --resume
```

### Single Document Processing

For single documents or when you don't need chapter detection:

```bash
# Process normally (original workflow)
python pipeline.py document.pdf

# Resume previous processing
python pipeline.py document.pdf --resume-latest
```

### Error Handling

- **No chapters detected**: The orchestrator will inform you to use `pipeline.py` directly
- **Individual chapter failures**: Don't affect other chapters; failed chapters are clearly reported
- **Pipeline errors**: Each chapter runs in isolation, so errors are contained

### Performance Benefits

- **True parallel processing potential**: Chapters are completely independent
- **Incremental progress**: Complete chapters are saved, allowing selective reprocessing
- **Targeted reprocessing**: Only specific chapters need to be rerun
- **No complexity overhead**: Single documents run with zero multi-chapter overhead

## Troubleshooting

### No Chapters Detected

If `multi_chapter_pipeline.py` doesn't detect chapters:

1. Check if your PDF uses the expected font (`BumperSticker`) and size (`28`) for chapter headers
2. Verify chapter headers follow expected patterns (number + text)
3. Use `pipeline.py` directly to process as a single document

### Chapter Detection Issues

If chapters are detected incorrectly:

1. Review the detected chapters in the approval prompt
2. Approve only the correct chapters
3. Use `--chapter-only` to process individual chapters manually

### Processing Errors

If a chapter fails to process:

1. Check the specific chapter PDF in `output/chapters/`
2. Try reprocessing just that chapter: `--chapter-only chapter_id`
3. Test the chapter PDF directly with `pipeline.py chapter.pdf`
4. Check orchestrator output for specific error messages

### Pipeline vs Orchestrator Issues

- **Pipeline errors**: Test individual chapter PDFs with `pipeline.py` directly
- **Orchestrator errors**: Check chapter detection and PDF extraction steps
- **Combined output issues**: Verify individual chapter outputs are valid JSON

## Development Notes

### Extending Chapter Detection

To customize chapter detection criteria, modify `etl/chapter_detection.py`:

- Update `is_chapter_header_text()` for different text patterns
- Modify font/size criteria in `detect_chapter_headers()`
- Adjust `parse_chapter_text()` for different title formats

### Adding New Orchestrator Features

The clean separation allows easy extension:

- Modify `multi_chapter_pipeline.py` for new orchestration logic
- Add new command-line options for different processing modes
- Implement parallel processing for multiple chapters
- Add new output combination strategies

### Testing

Test the multi-chapter functionality with:

1. **Chapter Detection**: PDFs with clear chapter headers using `BumperSticker` font
2. **Pipeline Integration**: Ensure individual chapters process correctly
3. **Output Combination**: Verify combined outputs are properly structured
4. **Single-document fallback**: Test with non-chapter documents

## Future Enhancements

The clean architecture enables many potential improvements:

### Orchestrator Enhancements
- **Parallel chapter processing**: Process multiple chapters simultaneously using multiprocessing
- **Progress tracking**: Real-time progress bars for long-running multi-chapter processing
- **Smart resume**: Automatically detect and resume incomplete chapter processing
- **Batch processing**: Process multiple PDFs with similar chapter structures

### Chapter Detection Improvements
- **Manual chapter range editing**: Interactive editor for adjusting detected page ranges
- **Custom detection criteria**: Configuration files for different document types
- **Machine learning detection**: Train models on document-specific chapter patterns
- **Visual chapter review**: Show thumbnails of detected chapter start pages
- **Chapter templates**: Save and reuse chapter detection patterns

### Output and Integration
- **Advanced output formats**: Export to different formats (HTML, Markdown, etc.)
- **Chapter cross-references**: Maintain links between chapters in combined output
- **Incremental updates**: Update only changed chapters in large documents
- **API integration**: REST API for programmatic multi-chapter processing

### Performance and Scalability
- **Distributed processing**: Process chapters across multiple machines
- **Caching**: Smart caching of intermediate results
- **Resource optimization**: Memory and disk usage optimization for large documents
- **Cloud integration**: Support for cloud-based processing pipelines