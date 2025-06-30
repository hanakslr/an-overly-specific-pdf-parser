# Multi-Chapter Pipeline Guide

This guide explains the new multi-chapter functionality that allows the pipeline to process entire PDFs by automatically detecting and extracting individual chapters.

## Overview

The enhanced pipeline now supports:
- **Automatic chapter detection** using PyMuPDF to find chapter headers with specific font criteria
- **Interactive chapter approval** allowing users to review and approve detected chapters
- **Individual chapter processing** where each chapter is processed independently
- **Chapter rerun capability** to reprocess specific chapters
- **Combined output** merging all processed chapters into a final document

## Chapter Detection Criteria

The system detects chapter headers by looking for text with:
- **Font**: `BumperSticker`
- **Size**: `28`
- **Content**: Text containing a number and string pattern (e.g., "1 Introduction", "Chapter 2: Title")

## Usage

### Basic Multi-Chapter Processing

```bash
python pipeline.py your_document.pdf
```

This will:
1. Detect chapters automatically
2. Present detected chapters for approval
3. Extract approved chapters as separate PDFs
4. Process each chapter through the full pipeline
5. Combine outputs into a final document

### Command Line Options

```bash
# Force single-chapter mode (skip chapter detection)
python pipeline.py your_document.pdf --single-chapter

# Resume from latest saved state
python pipeline.py your_document.pdf --resume-latest

# List available chapters from previous runs
python pipeline.py your_document.pdf --list-chapters

# Process only a specific chapter
python pipeline.py your_document.pdf --chapter chapter_1_Introduction

# Combine options
python pipeline.py your_document.pdf --resume-latest --chapter chapter_2_Methods
```

### Chapter Approval Process

When chapters are detected, you'll see an interactive prompt:

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

## Architecture Changes

### New State Structure

The pipeline now uses a hierarchical state structure:

```python
class ChapterPipelineState(BaseModel):
    """State for processing a single chapter"""
    chapter: ChapterRange
    chapter_pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None
    # ... other chapter-specific fields

class PipelineState(BaseModel):
    """Main pipeline state"""
    pdf_path: str
    
    # Multi-chapter support
    chapter_detection_result: Optional[ChapterDetectionResult] = None
    chapters: Dict[str, ChapterPipelineState] = {}
    current_chapter_id: Optional[str] = None
    processing_mode: str = "single"  # "single" or "multi"
    
    # Legacy single-chapter fields (for backward compatibility)
    # ... existing fields
```

### New Pipeline Flow

1. **Chapter Detection**: Analyze PDF for chapter headers
2. **Chapter Approval**: User reviews and approves chapters
3. **Chapter Extraction**: Extract approved chapters as separate PDFs
4. **Chapter Processing Loop**: For each approved chapter:
   - LlamaParse
   - PyMuPDF extraction
   - Content zipping
   - Block processing
   - Image insertion
   - Custom extraction
5. **Output Combination**: Merge all chapter outputs

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
# List available chapters
python pipeline.py document.pdf --list-chapters

# Reprocess a specific chapter
python pipeline.py document.pdf --chapter chapter_2_Methods
```

### Backward Compatibility

The system maintains full backward compatibility:
- Single-chapter PDFs are processed normally
- Existing command-line options work unchanged
- Legacy state files can be resumed

### Error Handling

- If no chapters are detected, processing falls back to single-chapter mode
- If chapter detection fails, the user can force single-chapter mode with `--single-chapter`
- Individual chapter failures don't affect other chapters

### Performance Benefits

- **Parallel processing potential**: Chapters can be processed independently
- **Incremental progress**: Complete chapters are saved, allowing partial resume
- **Targeted reprocessing**: Only specific chapters need to be rerun when needed

## Troubleshooting

### No Chapters Detected

If the system doesn't detect chapters:

1. Check if your PDF uses the expected font (`BumperSticker`) and size (`28`) for chapter headers
2. Verify chapter headers follow expected patterns (number + text)
3. Use `--single-chapter` to process as a single document

### Chapter Detection Issues

If chapters are detected incorrectly:

1. Review the detected chapters in the approval prompt
2. Approve only the correct chapters
3. Manually adjust chapter ranges if needed (future enhancement)

### Processing Errors

If a chapter fails to process:

1. Check the specific chapter PDF in `output/chapters/`
2. Try reprocessing just that chapter: `--chapter chapter_id`
3. Check for font or content issues in that specific chapter

## Development Notes

### Extending Chapter Detection

To customize chapter detection criteria, modify `etl/chapter_detection.py`:

- Update `is_chapter_header_text()` for different text patterns
- Modify font/size criteria in `detect_chapter_headers()`
- Adjust `parse_chapter_text()` for different title formats

### Adding New Chapter Processing Features

The modular design allows easy extension:

- Add new processing steps in the pipeline
- Extend `ChapterPipelineState` for chapter-specific data
- Implement chapter-specific rules or extraction logic

### Testing

Test the multi-chapter functionality with:

1. PDFs with clear chapter headers using `BumperSticker` font
2. Various chapter numbering schemes (1, 2, 3 vs Chapter 1, Chapter 2)
3. Complex documents with multiple fonts and sizes
4. Single-chapter documents (should fall back gracefully)

## Future Enhancements

Potential improvements include:

- **Manual chapter range editing**: Allow users to adjust detected page ranges
- **Custom detection criteria**: Configure font/size requirements per document
- **Parallel chapter processing**: Process multiple chapters simultaneously
- **Chapter templates**: Save and reuse chapter detection patterns
- **Visual chapter review**: Show thumbnails of detected chapter start pages