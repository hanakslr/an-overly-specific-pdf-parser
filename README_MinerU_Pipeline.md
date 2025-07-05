# MinerU PDF Processing Pipeline

This is an advanced PDF parsing pipeline that combines multiple state-of-the-art tools for comprehensive document understanding and structured data extraction.

## Architecture Overview

The pipeline integrates the following tools:

- **MinerU**: Vision-based PDF parsing with layout analysis, reading order detection, and structure recognition
- **PyMuPDF**: Extracts style metadata including fonts, bounding boxes, colors, and formatting information
- **spaCy + SpanRuler**: Applies NLP processing and rule-based span recognition for structure refinement
- **LangChain**: Optional LLM orchestration for intelligent span generation and enhancement
- **Prodigy**: Human-in-the-loop annotation and correction interface

## Pipeline Flow

```
PDF Input → MinerU → PyMuPDF → Combine → spaCy+SpanRuler → LLM Enhancement → Prodigy Correction → Structured Output
```

### Processing Steps

1. **MinerU Extraction**: Vision-based block detection, reading order analysis, table/image extraction
2. **PyMuPDF Style Extraction**: Font information, colors, bounding boxes, and layout metadata
3. **Output Combination**: Merge MinerU content with PyMuPDF style information into unified blocks
4. **spaCy Processing**: NLP analysis with custom SpanRuler patterns for document structure
5. **LLM Enhancement** (Optional): AI-powered span generation and entity enhancement
6. **Prodigy Correction** (Optional): Human review and correction of annotations
7. **Final Output**: Structured JSON with all extracted information

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements_mineru.txt
```

### 2. Install spaCy Model

```bash
python -m spacy download en_core_web_sm
```

### 3. Optional: Install Prodigy (requires license)

Prodigy requires a commercial license for human-in-the-loop features:
```bash
pip install prodigy -f https://XXXX-XXXX-XXXX-XXXX@download.prodi.gy
```

### 4. Optional: Set up LLM API Key

For LLM enhancement features, set your OpenAI API key:
```bash
export OPENAI_API_KEY="your_api_key_here"
```

## Usage

### Basic Usage

Process a PDF with default settings:
```bash
python mineru_pipeline.py document.pdf
```

### With LLM Enhancement

Enable AI-powered span generation:
```bash
python mineru_pipeline.py document.pdf --use-llm
```

### With Human-in-the-Loop

Enable Prodigy for human correction:
```bash
python mineru_pipeline.py document.pdf --use-human-correction
```

### Full Pipeline

Run with all features enabled:
```bash
python mineru_pipeline.py document.pdf --use-llm --use-human-correction
```

## Output Format

The pipeline generates a comprehensive JSON output with the following structure:

```json
{
  "document_info": {
    "source": "path/to/document.pdf",
    "total_blocks": 45,
    "pipeline": "MinerU + PyMuPDF + spaCy + SpanRuler",
    "processing_steps": "complete"
  },
  "content": {
    "blocks": [
      {
        "id": "block_0",
        "content": "Document text content",
        "block_type": "heading",
        "bbox": [x0, y0, x1, y1],
        "style_info": {
          "font": "Arial-Bold",
          "size": 14,
          "page": 0
        },
        "reading_order": 0,
        "confidence": 0.95
      }
    ],
    "entities": [
      {
        "text": "Company Name",
        "label": "ORG",
        "start": 10,
        "end": 22,
        "block_id": "block_0"
      }
    ],
    "spans": [
      {
        "text": "Table 1",
        "label": "TABLE_CAPTION",
        "start": 0,
        "end": 7,
        "block_id": "block_5"
      }
    ]
  },
  "style_info": {
    "fonts": ["Arial", "Times-Roman", "Arial-Bold"],
    "colors": [0, 255, 16777215]
  },
  "enhancements": {
    "llm_generated": [],
    "human_corrections": []
  },
  "metadata": {
    "mineru_metadata": {},
    "processing_quality": 0.85
  }
}
```

## Key Features

### Vision-Based Processing
- **Layout Analysis**: Intelligent detection of document structure (headings, paragraphs, tables, images)
- **Reading Order**: Proper sequencing of content blocks for coherent text extraction
- **Table Recognition**: Accurate extraction of tabular data with structure preservation

### Style Preservation
- **Font Information**: Complete font family, size, and style details
- **Spatial Layout**: Precise bounding box coordinates for all elements
- **Color Information**: Text and background color extraction

### Intelligent Enhancement
- **Rule-Based Patterns**: Custom SpanRuler patterns for document-specific entities
- **NLP Analysis**: Part-of-speech tagging, named entity recognition, sentence segmentation
- **LLM Augmentation**: AI-powered identification of complex semantic structures

### Quality Assurance
- **Human Review**: Prodigy integration for annotation correction and validation
- **Confidence Scoring**: Quality metrics for each extracted element
- **Error Handling**: Graceful degradation when individual components fail

## Configuration

### Custom SpanRuler Patterns

You can extend the SpanRuler patterns in the `spacy_process` function:

```python
patterns = [
    {"label": "CUSTOM_ENTITY", "pattern": [{"LOWER": "custom"}, {"IS_ALPHA": True}]},
    {"label": "DATE_RANGE", "pattern": [{"SHAPE": "dddd"}, {"ORTH": "-"}, {"SHAPE": "dddd"}]},
    # Add more patterns as needed
]
```

### LLM Enhancement

Customize the LLM prompts in the `llm_enhance` function to target specific extraction needs:

```python
prompt = f"""
Custom prompt for your specific use case:
Block Type: {block.block_type}
Content: {block.content}

Extract: [specific instructions for your domain]
"""
```

### Prodigy Integration

For production use with Prodigy, implement the actual annotation workflow:

1. Export data to Prodigy format
2. Launch annotation interface
3. Collect human feedback
4. Import corrections back into pipeline

## Performance Considerations

### Processing Speed
- **MinerU**: ~1-3 pages/second on CPU, faster with GPU support
- **PyMuPDF**: Very fast style extraction
- **spaCy**: Efficient NLP processing with pre-trained models
- **Overall**: Expect ~1-5 minutes per document depending on length and complexity

### Memory Usage
- Minimum 4GB RAM recommended
- 8GB+ recommended for large documents (>50 pages)
- GPU memory requirements for LLM features: 2-8GB depending on model

### Quality Factors
- **Document Quality**: Higher resolution PDFs yield better results
- **Layout Complexity**: Simple layouts process more accurately
- **Language Support**: Best results with English, expandable to other languages

## Comparison with Original Pipeline

| Feature | Original Pipeline | MinerU Pipeline |
|---------|------------------|-----------------|
| **Vision Processing** | Basic layout detection | Advanced vision-based analysis |
| **Reading Order** | Simple rules | AI-powered sequencing |
| **Style Preservation** | Limited | Comprehensive font/color info |
| **Human-in-the-Loop** | No | Prodigy integration |
| **LLM Enhancement** | Basic conversion rules | AI-powered span generation |
| **Processing Speed** | Fast | Moderate (more comprehensive) |
| **Accuracy** | Good for simple docs | Better for complex layouts |

## Troubleshooting

### Common Issues

1. **MinerU Installation**: Ensure compatible Python version (3.8+)
2. **GPU Support**: MinerU works on CPU but benefits from GPU acceleration
3. **spaCy Model**: Download the English model manually if auto-download fails
4. **Prodigy License**: Human-in-the-loop features require valid Prodigy license
5. **LLM API Limits**: OpenAI API has rate limits and costs per request

### Error Recovery

The pipeline includes robust error handling:
- Failed components don't crash the entire pipeline
- Partial results are saved if processing is interrupted
- Quality scores help identify processing issues

## Extension Points

### Adding New Tools
- Replace MinerU with other vision-based extractors
- Integrate additional NLP models (transformers, etc.)
- Add support for other annotation tools beyond Prodigy

### Domain Adaptation
- Train custom spaCy models for specific domains
- Create domain-specific SpanRuler patterns
- Customize LLM prompts for specialized extraction needs

### Integration
- Connect to document management systems
- Integrate with workflow orchestration tools
- Add API endpoints for service deployment

## Contributing

When extending this pipeline:

1. Maintain the modular architecture
2. Add comprehensive error handling
3. Include quality metrics for new components
4. Update documentation and examples
5. Test with diverse document types

## License

This pipeline combines multiple tools with different licenses:
- MinerU: Check MinerU licensing terms
- PyMuPDF: GNU GPL v3
- spaCy: MIT License
- LangChain: MIT License
- Prodigy: Commercial license required

Ensure compliance with all component licenses for your use case.