#!/usr/bin/env python3
"""
Table Processor Factory - Selects the best processor for a given table.

This factory implements a scoring system where each processor evaluates
how well it can handle a given table, then the highest-scoring processor
is selected to do the actual processing.
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
    """
    Factory that routes tables to the most appropriate processor.
    
    The factory maintains a list of available processors and uses a
    confidence-based routing system:
    
    1. Each processor scores the table (0.0 to 1.0 confidence)
    2. Highest-scoring processor is selected
    3. If no processor meets min_confidence, processing fails gracefully
    
    Attributes:
        processors: List of available processor instances
        min_confidence: Minimum score required to process (default 0.5)
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """
        Initialize factory with available processors.
        
        Args:
            min_confidence: Minimum confidence score (0.0-1.0) required
                          for a processor to be used. Default 0.5.
        """
        # The UniversalProcessor is our primary workhorse and should
        # handle most well-formed hierarchical tables.
        # The others are kept for potential future specialization.
        self.processors = [
            UniversalProcessor(),
            DataTableProcessor(),
            HierarchicalRowTableProcessor(),
            FormTableProcessor(),
            LayoutTableProcessor(),
        ]
        self.min_confidence = min_confidence

    def process_table(
        self, 
        grid: List[List[Dict]], 
        table_element
    ) -> ProcessingResult:
        """
        Score all processors and execute the best one.
        
        Process:
        1. Ask each processor to score the table
        2. Select the highest-scoring processor
        3. Verify it meets minimum confidence threshold
        4. Execute the processor on the table
        
        Args:
            grid: Logical 2D grid from parse_and_unmerge_table_bulletproof
            table_element: BeautifulSoup table element (for metadata)
            
        Returns:
            ProcessingResult with extracted rules and metadata
            
        Example:
            >>> grid = parse_and_unmerge_table_bulletproof(table)
            >>> factory = TableProcessorFactory(min_confidence=0.6)
            >>> result = factory.process_table(grid, table)
            >>> print(f"Generated {len(result.rules)} rules")
        """
        # Step 1: Score all available processors
        scores = {}
        for processor in self.processors:
            try:
                score = processor.can_process(grid, table_element)
                scores[processor] = score
                logger.debug(
                    f"{processor.__class__.__name__}: {score:.3f}"
                )
            except Exception as e:
                logger.error(
                    f"Error scoring {processor.__class__.__name__}: {e}",
                    exc_info=True
                )
                scores[processor] = 0.0

        # Step 2: Verify we have at least one processor
        if not scores:
            logger.warning("No processors available.")
            return ProcessingResult(
                rules=[], 
                confidence=0.0,
                processor_type="None"
            )

        # Step 3: Find the highest-scoring processor
        best_processor = max(scores, key=scores.get)
        best_score = scores[best_processor]
        
        # Log all scores for debugging
        score_summary = [
            f"{p.__class__.__name__}: {s:.3f}" 
            for p, s in sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ]
        logger.info(f"Processor scores: {score_summary}")
        logger.info(
            f"Selected: {best_processor.__class__.__name__} "
            f"(confidence: {best_score:.3f})"
        )

        # Step 4: Check minimum confidence threshold
        if best_score < self.min_confidence:
            logger.warning(
                f"Best processor scored {best_score:.3f}, "
                f"below minimum {self.min_confidence:.3f}"
            )
            return ProcessingResult(
                rules=[], 
                confidence=best_score, 
                processor_type=best_processor.__class__.__name__
            )

        # Step 5: Execute the selected processor
        try:
            result = best_processor.process(grid, table_element)
            logger.info(
                f"Successfully processed with {result.processor_type}: "
                f"{len(result.rules)} rules generated"
            )
            return result
        except Exception as e:
            logger.error(
                f"Error processing with {best_processor.__class__.__name__}: {e}",
                exc_info=True
            )
            return ProcessingResult(
                rules=[], 
                confidence=0.0, 
                processor_type=best_processor.__class__.__name__,
                metadata={"error": str(e)}
            )