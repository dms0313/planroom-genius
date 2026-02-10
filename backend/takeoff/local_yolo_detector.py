"""Local detection module that runs object detection using a YOLO model."""
# --- PyTorch 2.6 Safe Loading Patch for YOLO & Core Torch Modules ---
import torch.serialization
from ultralytics.nn import tasks
from ultralytics.nn.modules import conv as yconv, head as yhead, block as yblock
from ultralytics.nn.modules.conv import Concat
from ultralytics.nn.modules.block import DFL  # 👈 add this new one
import torch.nn as nn
import torch.nn.modules.container as container

torch.serialization.add_safe_globals([
    # Ultralytics YOLO architecture
    tasks.DetectionModel,
    yconv.Conv,
    yhead.Detect,
    yblock.C2f,
    yblock.Bottleneck,
    yblock.C3,
    yblock.SPPF,
    Concat,
    DFL,  # 👈 this is the last missing module

    # PyTorch core layers
    container.Sequential,
    container.ModuleList,
    container.ModuleDict,
    nn.Conv2d,
    nn.BatchNorm2d,
    nn.SiLU,
    nn.ReLU,
    nn.LeakyReLU,
    nn.Identity,
    nn.Upsample,
    nn.MaxPool2d,
    nn.AvgPool2d,
    nn.AdaptiveAvgPool2d,
    nn.Dropout,
    nn.Flatten,
])
# --- End Safe Loading Patch ---

import copy
import logging
import os
import time
import threading
import hashlib
from typing import Optional, Dict, List, Tuple
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from ultralytics import YOLO

from .takeoff_config import (
    DEFAULT_CONFIDENCE,
    LOCAL_MODEL_PATH,
    MAX_WORKERS,
    MAX_CACHE_SIZE,
    TILE_SIZE,
)

try:
    import torch
except Exception:  # pragma: no cover - torch is optional at import time
    torch = None

logger = logging.getLogger(__name__)


class TileCache:
    """Cache for tile processing results to avoid reprocessing identical tiles (LRU with max size)"""
    
    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.lock = threading.Lock()
    
    def get_tile_hash(self, tile_image: Image.Image) -> str:
        """Generate MD5 hash for a tile image"""
        img_bytes = tile_image.tobytes()
        return hashlib.md5(img_bytes).hexdigest()
    
    def get(self, tile_hash: str) -> Optional[Dict]:
        """Get cached result for a tile and update LRU order"""
        with self.lock:
            if tile_hash in self.cache:
                self.hits += 1
                self.cache.move_to_end(tile_hash)  # Mark as recently used
                return copy.deepcopy(self.cache[tile_hash])
            self.misses += 1
            return None

    def set(self, tile_hash: str, result: Dict):
        """Cache result for a tile, evict LRU if over max size"""
        with self.lock:
            self.cache[tile_hash] = copy.deepcopy(result)
            self.cache.move_to_end(tile_hash)
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)  # Remove least recently used
    
    def clear(self):
        """Clear the cache"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                'hits': self.hits,
                'misses': self.misses,
                'total': total,
                'hit_rate': hit_rate,
                'size': len(self.cache)
            }


class LocalYOLODetector:
    """Local detection wrapper with caching and parallel processing."""

    def __init__(self, model_path: str = LOCAL_MODEL_PATH, device: Optional[str] = None):
        self.model_path = model_path
        self.device = device or self._select_device()
        self.model = None
        self.cache = TileCache()
        self.class_names: Dict[int, str] = {}
        self._initialize_model()

    def _select_device(self) -> str:
        """Select the best available device for inference."""
        requested_device = os.environ.get("DETECTOR_DEVICE")
        if requested_device:
            normalized_device = requested_device.strip().lower()
            if normalized_device in {"cpu", "cuda", "mps"} or normalized_device.startswith("cuda:"):
                logger.info("Using detector device from environment: %s", requested_device)
                return normalized_device
            logger.warning(
                "Invalid DETECTOR_DEVICE '%s'. Falling back to automatic device selection.",
                requested_device,
            )

        if torch is not None:
            try:
                if torch.cuda.is_available():
                    return "cuda"
                if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    return "mps"
            except Exception:
                logger.warning(
                    "Torch available but device query failed. Falling back to CPU.",
                    exc_info=True,
                )

        if requested_device and requested_device.strip():
            logger.warning(
                "Falling back to CPU after failing to use requested device '%s'.",
                requested_device,
            )
        elif torch is not None:
            logger.warning("No CUDA/MPS device available. Using CPU for detection.")
        else:
            logger.info("Torch is not installed. Using CPU for detection.")

        return "cpu"

    def _initialize_model(self):
        """Load the local YOLO model from disk."""
        if not self.model_path:
            raise ValueError("Model path must be provided for local detection")

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at {self.model_path}")

        logger.info("Loading local detection model from %s", self.model_path)

        try:
            self.model = YOLO(self.model_path)
            self.class_names = self.model.names or {}
            logger.info("✅ Local detection model loaded successfully (%s)", self.device)
        except Exception as exc:
            logger.error("❌ Failed to load local detection model: %s", exc, exc_info=True)
            raise

    def detect_on_tile(
        self,
        tile_image: Image.Image,
        confidence: float = DEFAULT_CONFIDENCE,
        use_cache: bool = True,
    ) -> Optional[Dict]:
        """
        Run detection on a single tile with optional caching

        Args:
            tile_image: PIL Image tile
            confidence: Detection confidence threshold
            use_cache: Whether to use cached results

        Returns:
            Predictions dict or None if error
        """
        # Check cache first
        if use_cache:
            tile_hash = self.cache.get_tile_hash(tile_image)
            cached_result = self.cache.get(tile_hash)
            if cached_result is not None:
                return cached_result

        if not tile_image or not isinstance(tile_image, Image.Image):
            logger.error("Invalid tile image provided")
            return None

        try:
            if not self.model:
                raise RuntimeError("Detection model is not initialized")

            confidence = self._sanitize_confidence(confidence)
            result = {'predictions': self._predict(tile_image, confidence)}

            if use_cache:
                tile_hash = self.cache.get_tile_hash(tile_image)
                self.cache.set(tile_hash, result)

            return copy.deepcopy(result)

        except Exception as e:
            logger.error(f"Error during detection: {str(e)}")
            return None

    def _sanitize_confidence(self, confidence: Optional[float]) -> float:
        raw_confidence = confidence if confidence is not None else DEFAULT_CONFIDENCE
        if not (0.0 <= raw_confidence <= 1.0):
            logger.warning(
                "Confidence value %s is out of bounds [0, 1]. Clamping to valid range.",
                raw_confidence,
            )
        return max(0.0, min(1.0, raw_confidence))

    def _predict(self, tile_image: Image.Image, confidence: float) -> List[Dict]:
        results = self.model.predict(
            tile_image,
            conf=confidence,
            device=self.device,
            verbose=False,
        )
        return self._parse_results(results)

    def _parse_results(self, results) -> List[Dict]:
        predictions: List[Dict] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue

            xywh = boxes.xywh.cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            classes = boxes.cls.cpu().tolist()

            for (x, y, w, h), conf_score, cls_idx in zip(xywh, confidences, classes):
                class_id = int(cls_idx)
                predictions.append(
                    {
                        'x': float(x),
                        'y': float(y),
                        'width': float(w),
                        'height': float(h),
                        'confidence': float(conf_score),
                        'class': self.class_names.get(class_id, str(class_id)),
                        'class_id': class_id,
                    }
                )

        return predictions
    
    def process_all_tiles_parallel(
        self,
        tiles: List[Dict],
        confidence: float = DEFAULT_CONFIDENCE,
        max_workers: int = MAX_WORKERS,
        use_cache: bool = True,
        early_stop_count: Optional[int] = None,
    ) -> Tuple[List[Dict], Dict]:
        """Process tiles in parallel with optional early stopping."""
        all_detections = []
        start_time = time.time()
        processed = 0
        early_stopped = False

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_tile = {
                executor.submit(self.detect_on_tile, tile['image'], confidence, use_cache): tile
                for tile in tiles
            }

            # Process completed tasks
            for future in as_completed(future_to_tile):
                tile = future_to_tile[future]
                processed += 1

                try:
                    predictions = future.result()

                    if predictions and 'predictions' in predictions:
                        for pred in predictions['predictions']:

                            # --- START: CORRECTED COORDINATE LOGIC ---

                            # Your desired scale factor for "tighter" boxes
                            scale_factor = 1.0

                            # The YOLO model returns *pixel coordinates* relative
                            # to the tile image (e.g., 640x640).
                            # NO normalization (/ 100.0) or ( * TILE_SIZE) is needed here.

                            # These are the center (x,y) and dimensions (w,h) *within the tile*
                            tile_center_x = pred['x']
                            tile_center_y = pred['y']
                            tile_width = pred['width']
                            tile_height = pred['height']

                            # Apply your desired 0.6 scaling to the *pixel dimensions*
                            scaled_width = max(20, int(tile_width * scale_factor))
                            scaled_height = max(20, int(tile_height * scale_factor))

                            # Adjust to full image space by adding the tile's offset
                            # to the box's center coordinate within the tile.
                            pred['x'] = tile['x'] + tile_center_x
                            pred['y'] = tile['y'] + tile_center_y
                            pred['width'] = scaled_width
                            pred['height'] = scaled_height

                            # --- END: CORRECTED COORDINATE LOGIC ---

                            pred['tile_id'] = tile['id']
                            all_detections.append(pred)

                    # Check early stopping
                    if early_stop_count and len(all_detections) >= early_stop_count:
                        logger.info(f"Early stopping: Found {len(all_detections)} objects")
                        early_stopped = True
                        for f in future_to_tile:
                            if not f.done():
                                f.cancel()
                        break

                except Exception as e:
                    logger.warning(f"Error processing tile {tile['id']}: {str(e)}")

        processing_time = time.time() - start_time
        cache_stats = self.cache.get_stats()

        stats = {
            'processed': processed,
            'total_time': processing_time,
            'cache_hits': cache_stats['hits'],
            'cache_misses': cache_stats['misses'],
            'cache_hit_rate': cache_stats['hit_rate'],
            'early_stopped': early_stopped,
            'objects_found': len(all_detections)
        }

        return all_detections, stats
    
    def process_all_tiles_sequential(self, tiles: List[Dict], confidence: float = DEFAULT_CONFIDENCE,
                                    use_cache: bool = True,
                                    early_stop_count: Optional[int] = None) -> Tuple[List[Dict], Dict]:
        """
        Process tiles sequentially with optional early stopping
        
        Args:
            tiles: List of tile dictionaries
            confidence: Detection confidence threshold
            use_cache: Whether to use cached results
            early_stop_count: Stop after finding this many objects
        
        Returns:
            Tuple of (all_detections, processing_stats)
        """
        all_detections = []
        start_time = time.time()
        processed = 0
        early_stopped = False
        
        for tile in tiles:
            try:
                predictions = self.detect_on_tile(tile['image'], confidence, use_cache)
                processed += 1
                
                if predictions and 'predictions' in predictions:
                    for pred in predictions['predictions']:
                        # Adjust coordinates to full image space
                        pred['x'] += tile['x']
                        pred['y'] += tile['y']
                        pred['tile_id'] = tile['id']
                        all_detections.append(pred)
                
                # Check early stopping
                if early_stop_count and len(all_detections) >= early_stop_count:
                    logger.info(f"Early stopping: Found {len(all_detections)} objects")
                    early_stopped = True
                    break
            
            except Exception as e:
                logger.warning(f"Error processing tile {tile['id']}: {str(e)}")
        
        processing_time = time.time() - start_time
        cache_stats = self.cache.get_stats()
        
        stats = {
            'processed': processed,
            'total_time': processing_time,
            'cache_hits': cache_stats['hits'],
            'cache_misses': cache_stats['misses'],
            'cache_hit_rate': cache_stats['hit_rate'],
            'early_stopped': early_stopped,
            'objects_found': len(all_detections)
        }
        
        return all_detections, stats
