#!/usr/bin/env python3
"""
Example usage script for the MinerU PDF Processing Pipeline

This script demonstrates various ways to use the MinerU pipeline:
1. Basic document processing
2. Batch processing multiple PDFs
3. Custom configuration options
4. Integration with existing workflows
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import the MinerU pipeline components
from mineru_pipeline import (
    MinerUPipelineState,
    build_mineru_pipeline,
    save_output
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_single_document(pdf_path: str, use_llm: bool = False, use_human: bool = False) -> Dict[str, Any]:
    """
    Process a single PDF document through the MinerU pipeline
    
    Args:
        pdf_path: Path to the PDF file
        use_llm: Enable LLM enhancement
        use_human: Enable human-in-the-loop correction
        
    Returns:
        Structured data extracted from the document
    """
    logger.info(f"Processing single document: {pdf_path}")
    
    # Check if file exists
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Initialize pipeline state
    initial_state = MinerUPipelineState(
        pdf_path=pdf_path,
        use_llm_enhancement=use_llm,
        use_human_correction=use_human
    )
    
    # Build and run pipeline
    pipeline = build_mineru_pipeline()
    
    final_state = None
    for state in pipeline.stream(initial_state, stream_mode="values"):
        final_state = state
    
    if final_state and final_state.structured_data:
        return final_state.structured_data
    else:
        raise RuntimeError("Pipeline failed to produce output")


def batch_process_documents(pdf_directory: str, output_directory: str = "output") -> List[str]:
    """
    Process multiple PDF documents in a directory
    
    Args:
        pdf_directory: Directory containing PDF files
        output_directory: Directory to save outputs
        
    Returns:
        List of output file paths
    """
    logger.info(f"Starting batch processing of PDFs in: {pdf_directory}")
    
    pdf_dir = Path(pdf_directory)
    output_dir = Path(output_directory)
    output_dir.mkdir(exist_ok=True)
    
    # Find all PDF files
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF files found in {pdf_directory}")
        return []
    
    logger.info(f"Found {len(pdf_files)} PDF files to process")
    
    output_files = []
    successful = 0
    failed = 0
    
    for pdf_file in pdf_files:
        try:
            logger.info(f"Processing: {pdf_file.name}")
            
            # Process the document
            result = process_single_document(str(pdf_file))
            
            # Save output
            output_file = output_dir / f"{pdf_file.stem}_extracted.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            output_files.append(str(output_file))
            successful += 1
            logger.info(f"✅ Successfully processed: {pdf_file.name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to process {pdf_file.name}: {str(e)}")
            failed += 1
    
    logger.info(f"Batch processing complete: {successful} successful, {failed} failed")
    return output_files


def extract_specific_information(pdf_path: str, target_entities: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """
    Extract specific types of information from a document
    
    Args:
        pdf_path: Path to the PDF file
        target_entities: List of entity types to extract (e.g., ['PERSON', 'ORG', 'DATE'])
        
    Returns:
        Dictionary mapping entity types to lists of found entities
    """
    if target_entities is None:
        target_entities = ['PERSON', 'ORG', 'GPE', 'DATE', 'MONEY']
    
    logger.info(f"Extracting specific entities: {target_entities}")
    
    # Process the document
    result = process_single_document(pdf_path)
    
    # Filter entities by type
    extracted_info = {entity_type: [] for entity_type in target_entities}
    
    for entity in result.get('content', {}).get('entities', []):
        entity_type = entity.get('label', '')
        entity_text = entity.get('text', '')
        
        if entity_type in target_entities and entity_text not in extracted_info[entity_type]:
            extracted_info[entity_type].append(entity_text)
    
    return extracted_info


def analyze_document_structure(pdf_path: str) -> Dict[str, Any]:
    """
    Analyze the structure of a document (headings, sections, etc.)
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Document structure analysis
    """
    logger.info(f"Analyzing document structure: {pdf_path}")
    
    result = process_single_document(pdf_path)
    
    # Analyze block types
    blocks = result.get('content', {}).get('blocks', [])
    block_type_counts = {}
    headings = []
    tables = []
    images = []
    
    for block in blocks:
        block_type = block.get('block_type', 'unknown')
        block_type_counts[block_type] = block_type_counts.get(block_type, 0) + 1
        
        if block_type == 'heading':
            headings.append({
                'text': block.get('content', ''),
                'page': block.get('style_info', {}).get('page', 0),
                'order': block.get('reading_order', 0)
            })
        elif block_type == 'table':
            tables.append({
                'id': block.get('id', ''),
                'page': block.get('style_info', {}).get('page', 0)
            })
        elif block_type == 'image':
            images.append({
                'id': block.get('id', ''),
                'page': block.get('style_info', {}).get('page', 0)
            })
    
    # Analyze spans for document elements
    spans = result.get('content', {}).get('spans', [])
    table_captions = [s for s in spans if s.get('label') == 'TABLE_CAPTION']
    figure_captions = [s for s in spans if s.get('label') == 'FIGURE_CAPTION']
    
    structure_analysis = {
        'total_blocks': len(blocks),
        'block_type_distribution': block_type_counts,
        'headings': headings,
        'tables': {
            'count': len(tables),
            'captions': len(table_captions)
        },
        'images': {
            'count': len(images),
            'captions': len(figure_captions)
        },
        'quality_score': result.get('metadata', {}).get('processing_quality', 0.0),
        'fonts_used': result.get('style_info', {}).get('fonts', [])
    }
    
    return structure_analysis


def compare_processing_methods(pdf_path: str) -> Dict[str, Any]:
    """
    Compare different processing configurations
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Comparison results
    """
    logger.info(f"Comparing processing methods for: {pdf_path}")
    
    # Process with different configurations
    basic_result = process_single_document(pdf_path, use_llm=False, use_human=False)
    llm_result = process_single_document(pdf_path, use_llm=True, use_human=False)
    
    comparison = {
        'basic_processing': {
            'entities_found': len(basic_result.get('content', {}).get('entities', [])),
            'spans_found': len(basic_result.get('content', {}).get('spans', [])),
            'quality_score': basic_result.get('metadata', {}).get('processing_quality', 0.0)
        },
        'llm_enhanced': {
            'entities_found': len(llm_result.get('content', {}).get('entities', [])),
            'spans_found': len(llm_result.get('content', {}).get('spans', [])),
            'quality_score': llm_result.get('metadata', {}).get('processing_quality', 0.0),
            'llm_generated_spans': len(llm_result.get('enhancements', {}).get('llm_generated', []))
        }
    }
    
    return comparison


def create_processing_report(results: Dict[str, Any], output_path: str = "processing_report.html"):
    """
    Create an HTML report of processing results
    
    Args:
        results: Processing results from the pipeline
        output_path: Path to save the HTML report
    """
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MinerU Processing Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .section { margin: 20px 0; }
            .entity { background-color: #e6f3ff; padding: 2px 5px; border-radius: 3px; margin: 2px; }
            .heading { color: #333; border-bottom: 2px solid #ddd; padding-bottom: 5px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h1>Document Processing Report</h1>
        
        <div class="section">
            <h2 class="heading">Document Information</h2>
            <table>
                <tr><td><strong>Source:</strong></td><td>{source}</td></tr>
                <tr><td><strong>Total Blocks:</strong></td><td>{total_blocks}</td></tr>
                <tr><td><strong>Quality Score:</strong></td><td>{quality_score:.2f}</td></tr>
                <tr><td><strong>Pipeline:</strong></td><td>{pipeline}</td></tr>
            </table>
        </div>
        
        <div class="section">
            <h2 class="heading">Extracted Entities</h2>
            <p>Found {entity_count} entities:</p>
            <div>{entities_html}</div>
        </div>
        
        <div class="section">
            <h2 class="heading">Document Structure</h2>
            <table>
                <tr><th>Block Type</th><th>Count</th></tr>
                {structure_table}
            </table>
        </div>
        
        <div class="section">
            <h2 class="heading">Style Information</h2>
            <p><strong>Fonts used:</strong> {fonts}</p>
            <p><strong>Colors found:</strong> {color_count}</p>
        </div>
    </body>
    </html>
    """
    
    # Extract data for template
    doc_info = results.get('document_info', {})
    content = results.get('content', {})
    style_info = results.get('style_info', {})
    metadata = results.get('metadata', {})
    
    # Create entities HTML
    entities = content.get('entities', [])
    entities_html = ""
    for entity in entities[:50]:  # Limit to first 50 entities
        entities_html += f'<span class="entity" title="{entity.get("label", "")}">{entity.get("text", "")}</span>'
    
    # Create structure table
    blocks = content.get('blocks', [])
    block_types = {}
    for block in blocks:
        block_type = block.get('block_type', 'unknown')
        block_types[block_type] = block_types.get(block_type, 0) + 1
    
    structure_table = ""
    for block_type, count in block_types.items():
        structure_table += f"<tr><td>{block_type}</td><td>{count}</td></tr>"
    
    # Fill template
    html_content = html_template.format(
        source=doc_info.get('source', 'Unknown'),
        total_blocks=doc_info.get('total_blocks', 0),
        quality_score=metadata.get('processing_quality', 0.0),
        pipeline=doc_info.get('pipeline', 'Unknown'),
        entity_count=len(entities),
        entities_html=entities_html,
        structure_table=structure_table,
        fonts=', '.join(style_info.get('fonts', [])[:10]),  # First 10 fonts
        color_count=len(style_info.get('colors', []))
    )
    
    # Save report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"Processing report saved to: {output_path}")


def main():
    """
    Example usage of the MinerU pipeline
    """
    # Example PDF path (replace with your actual PDF)
    pdf_path = "example_document.pdf"
    
    if not Path(pdf_path).exists():
        logger.error(f"Example PDF not found: {pdf_path}")
        logger.info("Please replace 'example_document.pdf' with a real PDF file path")
        return
    
    try:
        # Example 1: Basic document processing
        logger.info("=== Example 1: Basic Processing ===")
        result = process_single_document(pdf_path)
        logger.info(f"Extracted {len(result['content']['entities'])} entities")
        
        # Example 2: Extract specific information
        logger.info("=== Example 2: Specific Information Extraction ===")
        specific_info = extract_specific_information(pdf_path, ['PERSON', 'ORG', 'DATE'])
        for entity_type, entities in specific_info.items():
            logger.info(f"{entity_type}: {entities[:5]}")  # Show first 5
        
        # Example 3: Document structure analysis
        logger.info("=== Example 3: Structure Analysis ===")
        structure = analyze_document_structure(pdf_path)
        logger.info(f"Document has {structure['total_blocks']} blocks")
        logger.info(f"Block types: {structure['block_type_distribution']}")
        
        # Example 4: Processing comparison
        logger.info("=== Example 4: Processing Comparison ===")
        comparison = compare_processing_methods(pdf_path)
        logger.info(f"Basic: {comparison['basic_processing']['entities_found']} entities")
        logger.info(f"LLM Enhanced: {comparison['llm_enhanced']['entities_found']} entities")
        
        # Example 5: Create processing report
        logger.info("=== Example 5: Creating HTML Report ===")
        create_processing_report(result, "example_report.html")
        
        # Example 6: Batch processing (if directory exists)
        batch_dir = "example_pdfs"
        if Path(batch_dir).exists():
            logger.info("=== Example 6: Batch Processing ===")
            output_files = batch_process_documents(batch_dir, "batch_output")
            logger.info(f"Processed {len(output_files)} files")
        
        logger.info("✅ All examples completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Example failed: {str(e)}")


if __name__ == "__main__":
    main()