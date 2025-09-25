#!/usr/bin/env python3
"""
Table Processor Factory - Selects the best processor for a given table.
"""
import logging
from typing import List, Dict
from models import ProcessingResult
from table_processors import (
    UniversalProcessor,
    DataTableProcessor,
    HierarchicalRowTableProcessor,
    FormTableProcessor,
    LayoutTableProcessor
)

logger = logging.getLogger(__name__)

class TableProcessorFactory:
    def __init__(self, min_confidence=0.5):
        # The UniversalProcessor is our new default and most powerful tool.
        # The others are kept for potential future specialization.
        self.processors = [
            UniversalProcessor(),
            DataTableProcessor(),
            HierarchicalRowTableProcessor(),
            FormTableProcessor(),
            LayoutTableProcessor(),
        ]
        self.min_confidence = min_confidence

    def process_table(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """
        Scores all available processors and executes the best one.
        """
        scores = {}
        for processor in self.processors:
            try:
                score = processor.can_process(grid, table_element)
                scores[processor] = score
            except Exception as e:
                logger.error(f"Error scoring processor {processor.__class__.__name__}: {e}")
                scores[processor] = 0.0

        # Find the processor with the highest score
        if not scores:
            logger.warning("No processors available.")
            return ProcessingResult(rules=[], confidence=0.0)

        best_processor = max(scores, key=scores.get)
        best_score = scores[best_processor]
        
        logger.info(f"Scores: {[ (p.__class__.__name__, f'{s:.3f}') for p, s in scores.items() ]}")
        logger.info(f"Best processor: {best_processor.__class__.__name__} (confidence: {best_score:.3f})")

        if best_score < self.min_confidence:
            logger.warning("No processor reached minimum confidence threshold.")
            return ProcessingResult(rules=[], confidence=best_score, processor_type="None")

        # Execute the best processor
        try:
            result = best_processor.process(grid, table_element)
            logger.info(f"Successfully processed with {result.processor_type}.")
            return result
        except Exception as e:
            logger.error(f"Error processing with {best_processor.__class__.__name__}: {e}", exc_info=True)
            return ProcessingResult(rules=[], confidence=0.0, processor_type=best_processor.__class__.__name__)