# Multi-Chapter Architecture Overview

This document provides a high-level overview of the multi-chapter processing architecture and how to use it.

## 🏗️ Architecture

The multi-chapter functionality uses a **clean separation of concerns** approach:

```
┌─────────────────────────────────────────────────────────┐
│                Original PDF Document                   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│         multi_chapter_pipeline.py                      │
│         (Orchestrator Script)                          │
│                                                         │
│  1. 🔍 Detect chapters using PyMuPDF                  │
│  2. 👤 Get user approval                               │
│  3. ✂️  Extract individual chapter PDFs               │
│  4. 🔄 For each chapter:                               │
│      └── Call pipeline.py chapter.pdf                 │
│  5. 📖 Combine results                                 │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                 pipeline.py                            │
│             (Original Pipeline)                        │
│                                                         │
│  • Unchanged single-document processing                │
│  • No multi-chapter complexity                         │
│  • Clean, focused, maintainable                        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Individual Chapter Outputs                │
│                                                         │
│  📄 chapter_1_Introduction.json                       │
│  📄 chapter_2_Methods.json                            │
│  📄 chapter_3_Results.json                            │
│  📖 combined_output.json                               │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Single Document (Original)
```bash
# Process any single document or chapter
python pipeline.py document.pdf
```

### Multi-Chapter Processing (New)
```bash
# Detect and process all chapters interactively
python multi_chapter_pipeline.py document.pdf

# List existing chapters
python multi_chapter_pipeline.py document.pdf --list-chapters

# Process only specific chapter
python multi_chapter_pipeline.py document.pdf --chapter-only chapter_1_Introduction
```

## 💡 Key Benefits

### 🧩 Clean Separation
- **`pipeline.py`**: Stays focused on single document processing
- **`multi_chapter_pipeline.py`**: Handles orchestration, detection, and coordination
- **No complexity added to core pipeline**

### 🔄 Independent Processing
- Each chapter runs in its own pipeline instance
- Failures are isolated to individual chapters
- Easy to debug and test individual chapters

### ⚡ Performance & Flexibility
- **Parallel processing ready**: Chapters are completely independent
- **Selective reprocessing**: Only rerun specific chapters
- **Zero overhead**: Single documents have no multi-chapter complexity

### 🛠️ Easy Maintenance
- Test single chapters with `pipeline.py` directly
- Orchestrator logic is completely separate
- Easy to extend either component independently

## 📁 File Organization

```
project/
├── pipeline.py                           # Original pipeline (unchanged)
├── multi_chapter_pipeline.py            # New orchestrator script
├── etl/
│   ├── chapter_detection.py             # Chapter detection logic
│   └── pdf_chapter_extractor.py         # PDF splitting utilities
├── output/
│   ├── chapters/                        # Extracted chapter PDFs
│   │   └── document.pdf/
│   │       ├── chapter_1_Introduction.pdf
│   │       └── chapter_2_Methods.pdf
│   └── pipeline/                        # Processing outputs
│       └── document.pdf/
│           ├── chapter_1_Introduction_timestamp.json
│           ├── chapter_2_Methods_timestamp.json
│           └── combined_output_timestamp.json
└── MULTI_CHAPTER_GUIDE.md              # Detailed documentation
```

## 🎯 Use Cases

### ✅ When to Use Multi-Chapter Pipeline
- PDFs with clear chapter divisions
- Documents using `BumperSticker` font size 28 for chapter headers
- Need to process different chapters independently
- Want combined output from multiple chapters

### ✅ When to Use Single Pipeline
- Single documents or articles
- Documents without clear chapter structure
- Quick processing of individual files
- Testing and development

## 🔧 Chapter Detection

The system automatically detects chapters by finding text with:
- **Font**: `BumperSticker`
- **Size**: `28`
- **Pattern**: Number + text (e.g., "1 Introduction", "Chapter 2: Methods")

## 📖 Getting Started

1. **Try single document first**:
   ```bash
   python pipeline.py sample.pdf
   ```

2. **Test multi-chapter detection**:
   ```bash
   python multi_chapter_pipeline.py full_document.pdf --list-chapters
   ```

3. **Process all chapters**:
   ```bash
   python multi_chapter_pipeline.py full_document.pdf
   ```

4. **Process specific chapter**:
   ```bash
   python multi_chapter_pipeline.py full_document.pdf --chapter-only chapter_1_Introduction
   ```

## 🆘 Troubleshooting

- **No chapters detected**: Use `pipeline.py` directly for single documents
- **Chapter processing fails**: Test individual chapter PDFs with `pipeline.py`
- **Detection issues**: Check font/size requirements in the PDF
- **Need help**: See `MULTI_CHAPTER_GUIDE.md` for detailed documentation

## 🚀 Future Extensions

The clean architecture makes it easy to add:
- Parallel processing of multiple chapters
- Different chapter detection algorithms
- Custom output combination strategies
- API interfaces for programmatic access

---

**Ready to get started?** Check out `MULTI_CHAPTER_GUIDE.md` for detailed usage instructions and examples!