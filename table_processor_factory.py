#!/usr/bin/env python3
"""
Table Processor Factory - Routes tables to appropriate processors
"""

from typing import List, Dict, Any
import logging
from table_processors import TableProcessor, DataTableProcessor, FormTableProcessor, LayoutTableProcessor, HierarchicalRowTableProcessor, ProcessingResult
logger = logging.getLogger(__name__)


class TableProcessorFactory:
    """Factory that routes tables to the most appropriate processor"""
    
    def __init__(self):
        # Order processors by specificity - most specific first
        self.processors = [
            HierarchicalRowTableProcessor(),  # Most specific - complex hierarchical tables
            FormTableProcessor(),             # Specific - form-like structures  
            DataTableProcessor(),             # General - standard data tables
            LayoutTableProcessor()            # Fallback - basic content extraction
        ]
        self.min_confidence_threshold = 0.5  # Raised from 0.3 for better quality
    
    def process_table(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Route table to best processor and return results"""
        if not grid or not grid[0]:
            return self._create_empty_result("Empty grid provided")
        
        # Get confidence scores
        processor_scores = []
        for processor in self.processors:
            try:
                confidence = processor.can_process(grid, table_element)
                processor_scores.append((processor, confidence))
                logger.info(f"{processor.__class__.__name__}: {confidence:.3f}")
            except Exception as e:
                logger.warning(f"Error in {processor.__class__.__name__}.can_process: {e}")
                processor_scores.append((processor, 0.0))
        
        # Sort by confidence
        processor_scores.sort(key=lambda x: x[1], reverse=True)
        best_processor, best_confidence = processor_scores[0]
        
        logger.info(f"Best processor: {best_processor.__class__.__name__} (confidence: {best_confidence:.3f})")
        
        # Check confidence threshold
        if best_confidence < self.min_confidence_threshold:
            logger.warning("No processor reached minimum confidence threshold")
        
        # Process with best processor
        try:
            result = best_processor.process(grid, table_element)
            logger.info(f"Successfully processed: {len(result.rules)} rules")
            return result
        except Exception as e:
            logger.error(f"Error in processing: {e}")
            return self._create_empty_result(f"Processing failed: {e}")
    
    def _create_empty_result(self, reason: str) -> ProcessingResult:
        """Create empty result for failed processing"""
        return ProcessingResult(
            rules=[],
            confidence=0.0,
            metadata={'error': reason},
            processor_type='none'
        )