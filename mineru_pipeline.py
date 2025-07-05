import sys
from typing import Optional, Dict, List, Any
import logging
from pathlib import Path

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, computed_field

# Core processing imports
try:
    import mineru
    from mineru import MinerU
except ImportError:
    print("MinerU not installed. Install with: pip install mineru")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF not installed. Install with: pip install PyMuPDF")
    sys.exit(1)

try:
    import spacy
    from spacy.tokens import Span
except ImportError:
    print("spaCy not installed. Install with: pip install spacy")
    sys.exit(1)

try:
    from langchain.llms import OpenAI
    from langchain.schema import Document
except ImportError:
    print("LangChain not installed. Install with: pip install langchain")
    sys.exit(1)

# Optional Prodigy import (for human-in-the-loop)
try:
    import prodigy
    PRODIGY_AVAILABLE = True
except ImportError:
    PRODIGY_AVAILABLE = False
    print("Prodigy not available. Install for human-in-the-loop features.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MinerUOutput(BaseModel):
    """Output structure from MinerU processing"""
    content: str
    layout_blocks: List[Dict]
    reading_order: List[int]
    tables: List[Dict]
    images: List[Dict]
    metadata: Dict


class PyMuPDFOutput(BaseModel):
    """Output structure from PyMuPDF processing"""
    pages: List[Dict]
    fonts: List[Dict]
    colors: List[str]
    styles: Dict[str, Any]
    bounding_boxes: List[Dict]


class ProcessedBlock(BaseModel):
    """Unified block after combining MinerU and PyMuPDF outputs"""
    id: str
    content: str
    block_type: str  # text, table, image, heading, etc.
    bbox: List[float]  # [x0, y0, x1, y1]
    style_info: Dict[str, Any]
    reading_order: int
    confidence: float = 1.0


class SpacyAnalysis(BaseModel):
    """Output from spaCy + SpanRuler processing"""
    entities: List[Dict]
    spans: List[Dict]
    tokens: List[Dict]
    sentences: List[Dict]
    refined_blocks: List[ProcessedBlock]


class LLMEnhancement(BaseModel):
    """Optional LLM enhancement results"""
    generated_spans: List[Dict]
    enhanced_entities: List[Dict]
    reasoning: str
    confidence_scores: Dict[str, float]


class ProdigyAnnotations(BaseModel):
    """Human annotations from Prodigy"""
    corrections: List[Dict]
    accepted_spans: List[Dict]
    rejected_spans: List[Dict]
    human_feedback: str


class MinerUPipelineState(BaseModel):
    """State object for the MinerU-based pipeline"""
    pdf_path: str
    
    # Processing outputs
    mineru_output: Optional[MinerUOutput] = None
    pymupdf_output: Optional[PyMuPDFOutput] = None
    processed_blocks: List[ProcessedBlock] = []
    
    # Analysis outputs
    spacy_analysis: Optional[SpacyAnalysis] = None
    llm_enhancement: Optional[LLMEnhancement] = None
    prodigy_annotations: Optional[ProdigyAnnotations] = None
    
    # Final output
    structured_data: Dict[str, Any] = {}
    
    # Processing flags
    use_llm_enhancement: bool = False
    use_human_correction: bool = False
    current_step: str = "initialized"


def mineru_extract(state: MinerUPipelineState):
    """Extract content using MinerU's vision-based approach"""
    if state.mineru_output:
        logger.info("⏭️  MinerU extraction already completed, skipping...")
        return {}
    
    logger.info("🔄 Running MinerU extraction...")
    
    try:
        # Initialize MinerU
        miner = MinerU()
        
        # Process the PDF
        result = miner.extract(state.pdf_path)
        
        # Structure the output
        mineru_output = MinerUOutput(
            content=result.get('content', ''),
            layout_blocks=result.get('layout_blocks', []),
            reading_order=result.get('reading_order', []),
            tables=result.get('tables', []),
            images=result.get('images', []),
            metadata=result.get('metadata', {})
        )
        
        logger.info(f"✅ MinerU extracted {len(mineru_output.layout_blocks)} blocks")
        return {"mineru_output": mineru_output, "current_step": "mineru_complete"}
        
    except Exception as e:
        logger.error(f"❌ MinerU extraction failed: {str(e)}")
        # Create empty output to continue pipeline
        mineru_output = MinerUOutput(
            content="", layout_blocks=[], reading_order=[],
            tables=[], images=[], metadata={}
        )
        return {"mineru_output": mineru_output, "current_step": "mineru_failed"}


def pymupdf_extract(state: MinerUPipelineState):
    """Extract style metadata using PyMuPDF"""
    if state.pymupdf_output:
        logger.info("⏭️  PyMuPDF extraction already completed, skipping...")
        return {}
    
    logger.info("🔄 Running PyMuPDF style extraction...")
    
    try:
        doc = fitz.open(state.pdf_path)
        
        pages = []
        fonts = []
        colors = set()
        styles = {}
        bboxes = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Extract text with style information
            blocks = page.get_text("dict")
            
            page_info = {
                "page_num": page_num,
                "blocks": blocks,
                "width": page.rect.width,
                "height": page.rect.height
            }
            pages.append(page_info)
            
            # Collect fonts and colors
            for block in blocks.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_info = {
                                "font": span.get("font", ""),
                                "size": span.get("size", 0),
                                "flags": span.get("flags", 0),
                                "color": span.get("color", 0)
                            }
                            fonts.append(font_info)
                            colors.add(span.get("color", 0))
                            
                            # Store bounding box
                            bbox = span.get("bbox", [])
                            if bbox:
                                bboxes.append({
                                    "page": page_num,
                                    "bbox": bbox,
                                    "text": span.get("text", ""),
                                    "font": span.get("font", ""),
                                    "size": span.get("size", 0)
                                })
        
        doc.close()
        
        pymupdf_output = PyMuPDFOutput(
            pages=pages,
            fonts=fonts,
            colors=list(colors),
            styles=styles,
            bounding_boxes=bboxes
        )
        
        logger.info(f"✅ PyMuPDF extracted style info from {len(pages)} pages")
        return {"pymupdf_output": pymupdf_output, "current_step": "pymupdf_complete"}
        
    except Exception as e:
        logger.error(f"❌ PyMuPDF extraction failed: {str(e)}")
        # Create empty output to continue pipeline
        pymupdf_output = PyMuPDFOutput(
            pages=[], fonts=[], colors=[], styles={}, bounding_boxes=[]
        )
        return {"pymupdf_output": pymupdf_output, "current_step": "pymupdf_failed"}


def combine_outputs(state: MinerUPipelineState):
    """Combine MinerU and PyMuPDF outputs into unified blocks"""
    if state.processed_blocks:
        logger.info("⏭️  Output combination already completed, skipping...")
        return {}
    
    logger.info("🔄 Combining MinerU and PyMuPDF outputs...")
    
    processed_blocks = []
    
    if not state.mineru_output or not state.pymupdf_output:
        logger.warning("⚠️  Missing required outputs for combination")
        return {"processed_blocks": processed_blocks, "current_step": "combination_failed"}
    
    # Match MinerU blocks with PyMuPDF style information
    for i, block in enumerate(state.mineru_output.layout_blocks):
        # Find corresponding style info from PyMuPDF
        style_info = {}
        
        block_bbox = block.get('bbox', [])
        if block_bbox:
            # Find matching bounding boxes in PyMuPDF output
            for bbox_info in state.pymupdf_output.bounding_boxes:
                pymupdf_bbox = bbox_info.get('bbox', [])
                # Simple overlap detection (can be made more sophisticated)
                if pymupdf_bbox and _boxes_overlap(block_bbox, pymupdf_bbox):
                    style_info = {
                        'font': bbox_info.get('font', ''),
                        'size': bbox_info.get('size', 0),
                        'page': bbox_info.get('page', 0)
                    }
                    break
        
        processed_block = ProcessedBlock(
            id=f"block_{i}",
            content=block.get('content', ''),
            block_type=block.get('type', 'text'),
            bbox=block_bbox,
            style_info=style_info,
            reading_order=block.get('reading_order', i),
            confidence=block.get('confidence', 1.0)
        )
        
        processed_blocks.append(processed_block)
    
    logger.info(f"✅ Combined into {len(processed_blocks)} processed blocks")
    return {"processed_blocks": processed_blocks, "current_step": "combination_complete"}


def _boxes_overlap(box1: List[float], box2: List[float], threshold: float = 0.5) -> bool:
    """Check if two bounding boxes overlap with given threshold"""
    if len(box1) != 4 or len(box2) != 4:
        return False
    
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # Calculate intersection
    x_overlap = max(0, min(x2_1, x2_2) - max(x1_1, x1_2))
    y_overlap = max(0, min(y2_1, y2_2) - max(y1_1, y1_2))
    intersection = x_overlap * y_overlap
    
    # Calculate union
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return (intersection / union) > threshold if union > 0 else False


def spacy_process(state: MinerUPipelineState):
    """Process with spaCy and SpanRuler for structure refinement"""
    if state.spacy_analysis:
        logger.info("⏭️  spaCy processing already completed, skipping...")
        return {}
    
    logger.info("🔄 Running spaCy + SpanRuler processing...")
    
    try:
        # Load spaCy model
        nlp = spacy.load("en_core_web_sm")
        
        # Add SpanRuler for custom patterns
        if "span_ruler" not in nlp.pipe_names:
            ruler = nlp.add_pipe("span_ruler")
            
            # Define patterns for document structure
            patterns = [
                {"label": "HEADING", "pattern": [{"IS_TITLE": True}]},
                {"label": "TABLE_CAPTION", "pattern": [{"LOWER": "table"}, {"IS_DIGIT": True}]},
                {"label": "FIGURE_CAPTION", "pattern": [{"LOWER": "figure"}, {"IS_DIGIT": True}]},
                {"label": "PAGE_NUMBER", "pattern": [{"IS_DIGIT": True, "LENGTH": {"<=": 3}}]},
            ]
            ruler.add_patterns(patterns)
        
        entities = []
        spans = []
        tokens = []
        sentences = []
        refined_blocks = []
        
        for block in state.processed_blocks:
            if not block.content.strip():
                continue
                
            # Process the block content
            doc = nlp(block.content)
            
            # Extract entities
            for ent in doc.ents:
                entities.append({
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "block_id": block.id
                })
            
            # Extract custom spans
            for span_key in doc.spans:
                for span in doc.spans[span_key]:
                    spans.append({
                        "text": span.text,
                        "label": span.label_,
                        "start": span.start_char,
                        "end": span.end_char,
                        "block_id": block.id,
                        "span_key": span_key
                    })
            
            # Extract tokens with linguistic features
            for token in doc:
                tokens.append({
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "tag": token.tag_,
                    "is_alpha": token.is_alpha,
                    "is_stop": token.is_stop,
                    "block_id": block.id
                })
            
            # Extract sentences
            for sent in doc.sents:
                sentences.append({
                    "text": sent.text,
                    "start": sent.start_char,
                    "end": sent.end_char,
                    "block_id": block.id
                })
            
            # Refine block classification based on spaCy analysis
            refined_block = _refine_block_with_spacy(block, doc)
            refined_blocks.append(refined_block)
        
        spacy_analysis = SpacyAnalysis(
            entities=entities,
            spans=spans,
            tokens=tokens,
            sentences=sentences,
            refined_blocks=refined_blocks
        )
        
        logger.info(f"✅ spaCy found {len(entities)} entities and {len(spans)} spans")
        return {"spacy_analysis": spacy_analysis, "current_step": "spacy_complete"}
        
    except Exception as e:
        logger.error(f"❌ spaCy processing failed: {str(e)}")
        # Create empty analysis to continue pipeline
        spacy_analysis = SpacyAnalysis(
            entities=[], spans=[], tokens=[], sentences=[], refined_blocks=state.processed_blocks
        )
        return {"spacy_analysis": spacy_analysis, "current_step": "spacy_failed"}


def _refine_block_with_spacy(block: ProcessedBlock, doc) -> ProcessedBlock:
    """Refine block type based on spaCy analysis"""
    refined_block = block.model_copy()
    
    # Check for headings
    if any(ent.label_ == "HEADING" for ent in doc.ents):
        refined_block.block_type = "heading"
        refined_block.confidence = 0.9
    
    # Check for table/figure captions
    elif any(ent.label_ in ["TABLE_CAPTION", "FIGURE_CAPTION"] for ent in doc.ents):
        refined_block.block_type = "caption"
        refined_block.confidence = 0.8
    
    # Check if it's mostly numeric (could be data/table)
    elif _is_mostly_numeric(doc):
        refined_block.block_type = "data"
        refined_block.confidence = 0.7
    
    return refined_block


def _is_mostly_numeric(doc) -> bool:
    """Check if document content is mostly numeric"""
    if len(doc) == 0:
        return False
    
    numeric_tokens = sum(1 for token in doc if token.like_num or token.is_digit)
    return numeric_tokens / len(doc) > 0.5


def llm_enhance(state: MinerUPipelineState):
    """Optional LLM enhancement for span generation"""
    if not state.use_llm_enhancement:
        logger.info("⏭️  LLM enhancement disabled, skipping...")
        return {"current_step": "llm_skipped"}
    
    if state.llm_enhancement:
        logger.info("⏭️  LLM enhancement already completed, skipping...")
        return {}
    
    logger.info("🔄 Running LLM enhancement...")
    
    try:
        # Initialize LLM (would need API key in practice)
        llm = OpenAI(temperature=0.1)
        
        generated_spans = []
        enhanced_entities = []
        reasoning = ""
        confidence_scores = {}
        
        # Process each refined block with LLM
        for block in state.spacy_analysis.refined_blocks:
            if not block.content.strip():
                continue
            
            # Create prompt for LLM
            prompt = f"""
            Analyze the following text block and identify any additional semantic spans or entities that might be missed by rule-based extraction:
            
            Block Type: {block.block_type}
            Content: {block.content}
            
            Please identify:
            1. Key concepts or terms
            2. Relationships between entities
            3. Important phrases or spans
            4. Document structure elements
            
            Return your analysis in a structured format.
            """
            
            try:
                response = llm.invoke(prompt)
                # Parse LLM response (simplified - would need better parsing)
                generated_spans.append({
                    "block_id": block.id,
                    "llm_response": response,
                    "confidence": 0.6  # LLM-generated spans get lower confidence
                })
                
            except Exception as llm_error:
                logger.warning(f"⚠️  LLM processing failed for block {block.id}: {llm_error}")
                continue
        
        llm_enhancement = LLMEnhancement(
            generated_spans=generated_spans,
            enhanced_entities=enhanced_entities,
            reasoning=reasoning,
            confidence_scores=confidence_scores
        )
        
        logger.info(f"✅ LLM enhanced {len(generated_spans)} blocks")
        return {"llm_enhancement": llm_enhancement, "current_step": "llm_complete"}
        
    except Exception as e:
        logger.error(f"❌ LLM enhancement failed: {str(e)}")
        # Create empty enhancement to continue pipeline
        llm_enhancement = LLMEnhancement(
            generated_spans=[], enhanced_entities=[], reasoning="", confidence_scores={}
        )
        return {"llm_enhancement": llm_enhancement, "current_step": "llm_failed"}


def prodigy_correct(state: MinerUPipelineState):
    """Human-in-the-loop correction using Prodigy"""
    if not state.use_human_correction:
        logger.info("⏭️  Human correction disabled, skipping...")
        return {"current_step": "prodigy_skipped"}
    
    if not PRODIGY_AVAILABLE:
        logger.warning("⚠️  Prodigy not available, skipping human correction...")
        return {"current_step": "prodigy_unavailable"}
    
    if state.prodigy_annotations:
        logger.info("⏭️  Prodigy correction already completed, skipping...")
        return {}
    
    logger.info("🔄 Starting Prodigy human-in-the-loop correction...")
    logger.info("📝 Please use Prodigy interface to review and correct annotations...")
    
    # In a real implementation, this would:
    # 1. Export data to Prodigy format
    # 2. Launch Prodigy annotation interface
    # 3. Wait for human annotation
    # 4. Import corrected annotations
    
    # For now, simulate human corrections
    corrections = []
    accepted_spans = []
    rejected_spans = []
    
    # Simulate some corrections based on confidence scores
    if state.spacy_analysis:
        for entity in state.spacy_analysis.entities:
            # Simulate human review - accept high confidence, reject low confidence
            if entity.get("confidence", 1.0) > 0.8:
                accepted_spans.append(entity)
            else:
                corrections.append({
                    "original": entity,
                    "corrected": {**entity, "label": "CORRECTED_" + entity["label"]},
                    "reason": "Low confidence annotation corrected by human"
                })
    
    prodigy_annotations = ProdigyAnnotations(
        corrections=corrections,
        accepted_spans=accepted_spans,
        rejected_spans=rejected_spans,
        human_feedback="Automated simulation of human corrections"
    )
    
    logger.info(f"✅ Prodigy completed with {len(corrections)} corrections")
    return {"prodigy_annotations": prodigy_annotations, "current_step": "prodigy_complete"}


def finalize_output(state: MinerUPipelineState):
    """Create final structured output"""
    logger.info("🔄 Finalizing structured output...")
    
    structured_data = {
        "document_info": {
            "source": state.pdf_path,
            "processing_steps": state.current_step,
            "total_blocks": len(state.processed_blocks),
            "pipeline": "MinerU + PyMuPDF + spaCy + SpanRuler"
        },
        "content": {
            "blocks": [block.model_dump() for block in state.processed_blocks],
            "entities": state.spacy_analysis.entities if state.spacy_analysis else [],
            "spans": state.spacy_analysis.spans if state.spacy_analysis else [],
        },
        "style_info": {
            "fonts": state.pymupdf_output.fonts if state.pymupdf_output else [],
            "colors": state.pymupdf_output.colors if state.pymupdf_output else [],
        },
        "enhancements": {
            "llm_generated": state.llm_enhancement.generated_spans if state.llm_enhancement else [],
            "human_corrections": state.prodigy_annotations.corrections if state.prodigy_annotations else [],
        },
        "metadata": {
            "mineru_metadata": state.mineru_output.metadata if state.mineru_output else {},
            "processing_quality": _calculate_quality_score(state),
        }
    }
    
    logger.info("✅ Pipeline completed successfully!")
    return {"structured_data": structured_data, "current_step": "complete"}


def _calculate_quality_score(state: MinerUPipelineState) -> float:
    """Calculate overall processing quality score"""
    score = 0.0
    
    # Base score for successful extraction
    if state.mineru_output and state.pymupdf_output:
        score += 0.4
    
    # Score for successful combination
    if state.processed_blocks:
        score += 0.2
    
    # Score for spaCy analysis
    if state.spacy_analysis:
        score += 0.2
    
    # Bonus for LLM enhancement
    if state.llm_enhancement:
        score += 0.1
    
    # Bonus for human correction
    if state.prodigy_annotations:
        score += 0.1
    
    return min(score, 1.0)


def build_mineru_pipeline():
    """Build the MinerU-based pipeline"""
    builder = StateGraph(state_schema=MinerUPipelineState)
    
    # Add nodes
    builder.add_node("MinerUExtract", RunnableLambda(mineru_extract))
    builder.add_node("PyMuPDFExtract", RunnableLambda(pymupdf_extract))
    builder.add_node("CombineOutputs", RunnableLambda(combine_outputs))
    builder.add_node("SpacyProcess", RunnableLambda(spacy_process))
    builder.add_node("LLMEnhance", RunnableLambda(llm_enhance))
    builder.add_node("ProdigyCorrect", RunnableLambda(prodigy_correct))
    builder.add_node("FinalizeOutput", RunnableLambda(finalize_output))
    
    # Set entry point
    builder.set_entry_point("MinerUExtract")
    
    # Add edges
    builder.add_edge("MinerUExtract", "PyMuPDFExtract")
    builder.add_edge("PyMuPDFExtract", "CombineOutputs")
    builder.add_edge("CombineOutputs", "SpacyProcess")
    builder.add_edge("SpacyProcess", "LLMEnhance")
    builder.add_edge("LLMEnhance", "ProdigyCorrect")
    builder.add_edge("ProdigyCorrect", "FinalizeOutput")
    builder.add_edge("FinalizeOutput", END)
    
    return builder.compile()


def save_output(pdf_path: str, final_state: dict) -> str:
    """Save the final output to a JSON file"""
    import json
    from datetime import datetime
    
    # Create output filename
    pdf_name = Path(pdf_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{pdf_name}_mineru_output_{timestamp}.json"
    
    # Save to file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(final_state, f, indent=2, ensure_ascii=False)
    
    return output_filename


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mineru_pipeline.py <pdf_path> [--use-llm] [--use-human-correction]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    use_llm = "--use-llm" in sys.argv
    use_human_correction = "--use-human-correction" in sys.argv
    
    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"Error: PDF file '{pdf_path}' not found")
        sys.exit(1)
    
    # Initialize state
    initial_state = MinerUPipelineState(
        pdf_path=pdf_path,
        use_llm_enhancement=use_llm,
        use_human_correction=use_human_correction
    )
    
    # Build and run pipeline
    pipeline = build_mineru_pipeline()
    
    print(f"🚀 Starting MinerU-based PDF processing pipeline...")
    print(f"📄 Processing: {pdf_path}")
    print(f"🤖 LLM Enhancement: {'Enabled' if use_llm else 'Disabled'}")
    print(f"👤 Human Correction: {'Enabled' if use_human_correction else 'Disabled'}")
    print("-" * 60)
    
    memory = MemorySaver()
    final_state = None
    
    try:
        for state in pipeline.stream(
            initial_state,
            config={"memory": memory, "recursion_limit": 100},
            stream_mode="values",
        ):
            final_state = state
    
    except Exception as e:
        print(f"❌ Pipeline error: {e}")
        if final_state:
            output_filename = save_output(pdf_path, final_state.model_dump())
            print(f"💾 Partial results saved to: {output_filename}")
    
    else:
        if final_state and final_state.structured_data:
            output_filename = save_output(pdf_path, final_state.structured_data)
            print(f"✅ Pipeline completed successfully!")
            print(f"💾 Output saved to: {output_filename}")
            
            # Print summary
            data = final_state.structured_data
            print(f"📊 Summary:")
            print(f"   - Total blocks: {data['document_info']['total_blocks']}")
            print(f"   - Entities found: {len(data['content']['entities'])}")
            print(f"   - Spans found: {len(data['content']['spans'])}")
            print(f"   - Quality score: {data['metadata']['processing_quality']:.2f}")
        else:
            print("❌ Pipeline completed but no output generated")