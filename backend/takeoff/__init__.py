"""
Takeoff Module - Fire Alarm Takeoff Assistant integrated into Planroom Genius

This module provides PDF analysis capabilities using local YOLO detection
and Gemini AI for fire alarm system takeoffs.
"""

from .gemini_analyzer import GeminiFireAlarmAnalyzer as GeminiAnalyzer
from .pdf_processor import PDFProcessor
from .visualizer import DetectionVisualizer
from .history_store import HistoryStore
from .models import FireAlarmDevice, PageAnalysis

# Try to import local YOLO detector (may fail if PyTorch is not available)
LocalYOLODetector = None
LOCAL_YOLO_IMPORT_ERROR = None

try:
    from .local_yolo_detector import LocalYOLODetector
except Exception as exc:
    LOCAL_YOLO_IMPORT_ERROR = str(exc)


__all__ = [
    'GeminiAnalyzer',
    'PDFProcessor', 
    'DetectionVisualizer',
    'HistoryStore',
    'FireAlarmDevice',
    'PageAnalysis',
    'LocalYOLODetector',
    'LOCAL_YOLO_IMPORT_ERROR',
]
