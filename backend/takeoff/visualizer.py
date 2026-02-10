"""
Detection Visualization Module - Draws bounding boxes and performs NMS
"""
import logging
from typing import List, Dict, Union

from PIL import Image, ImageDraw

from .models import FireAlarmDevice

logger = logging.getLogger(__name__)


class DetectionVisualizer:
    """Visualize detections and perform Non-Maximum Suppression"""
    
    @staticmethod
    def calculate_iou(box1: Dict, box2: Dict) -> float:
        """
        Calculate Intersection over Union between two boxes
        
        Args:
            box1, box2: Dictionaries with 'x', 'y', 'width', 'height' keys
        
        Returns:
            IoU score (0.0 to 1.0)
        """
        # Get box coordinates (center format to corner format)
        x1_1, y1_1 = box1['x'] - box1['width']/2, box1['y'] - box1['height']/2
        x2_1, y2_1 = box1['x'] + box1['width']/2, box1['y'] + box1['height']/2
        
        x1_2, y1_2 = box2['x'] - box2['width']/2, box2['y'] - box2['height']/2
        x2_2, y2_2 = box2['x'] + box2['width']/2, box2['y'] + box2['height']/2
        
        # Calculate intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i < x1_i or y2_i < y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Calculate union
        area1 = box1['width'] * box1['height']
        area2 = box2['width'] * box2['height']
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def remove_overlapping_detections(detections: List[Dict], 
                                    iou_threshold: float = 0.5) -> List[Dict]:
        """
        Remove overlapping detections using Non-Maximum Suppression
        Keep highest confidence detections
        
        Args:
            detections: List of detection dictionaries
            iou_threshold: IoU threshold for considering boxes as overlapping
        
        Returns:
            List of filtered detections
        """
        if not detections:
            return []
        
        # Sort by confidence (highest first)
        detections = sorted(detections, key=lambda x: x['confidence'], reverse=True)
        
        kept_detections = []
        
        for detection in detections:
            # Check if this detection overlaps with any kept detection
            overlap = False
            for kept in kept_detections:
                # Only compare same class
                if detection.get('class') == kept.get('class'):
                    iou = DetectionVisualizer.calculate_iou(detection, kept)
                    if iou > iou_threshold:
                        overlap = True
                        break
            
            if not overlap:
                kept_detections.append(detection)
        
        logger.info(f"NMS: Kept {len(kept_detections)} of {len(detections)} detections")
        return kept_detections
    
    @staticmethod
    def draw_detections(image: Image.Image, 
                    detections: List[Union[Dict, FireAlarmDevice]]) -> Image.Image:
        """
        Draw bounding boxes and labels on image
        
        Args:
            image: PIL Image to draw on
            detections: List of detections (dict or FireAlarmDevice objects)
        
        Returns:
            Annotated PIL Image
        """
        # Create copy for drawing
        img_draw = image.copy()
        draw = ImageDraw.Draw(img_draw)
        
        # Color map for different classes
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']
        class_colors = {}
        color_idx = 0
        
        for det in detections:
            try:
                # Handle both dictionary and FireAlarmDevice objects
                if isinstance(det, FireAlarmDevice):
                    device_type = det.device_type
                    x = det.x
                    y = det.y
                    width = det.width
                    height = det.height
                    confidence = det.confidence
                elif isinstance(det, dict):
                    device_type = det.get('device_type') or det.get('class', 'Unknown')
                    x = det['x']
                    y = det['y']
                    width = det['width']
                    height = det['height']
                    confidence = det['confidence']
                else:
                    continue
                
                # Get or assign color
                if device_type not in class_colors:
                    class_colors[device_type] = colors[color_idx % len(colors)]
                    color_idx += 1
                color = class_colors[device_type]
                
                # Ensure positive dimensions
                width = abs(width)
                height = abs(height)
                
                # Convert center coords to corner coords
                x1 = max(0, int(x - width/2))
                y1 = max(0, int(y - height/2))
                x2 = min(image.width, int(x + width/2))
                y2 = min(image.height, int(y + height/2))
                
                # Validate coordinates
                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)
                
                # Skip invalid boxes
                if x1 >= image.width or y1 >= image.height or x2 <= 0 or y2 <= 0 or x1 >= x2 or y1 >= y2:
                    logger.debug(f"Skipping invalid box: ({x1},{y1},{x2},{y2})")
                    continue
                
                # Draw rectangle
                draw.rectangle([x1, y1, x2, y2], outline=color, width=1)
                
                # Create compact label
                conf_pct = int(confidence * 100)
                short_type = device_type[:2]
                label = f"{short_type}{conf_pct}%"
                
                # Position label above box
                label_y = max(2, y1 - 14)
                label_x = x1 + 2
                
                # Get text dimensions
                left, top, right, bottom = draw.textbbox((0, 0), label)
                text_width = right - left
                text_height = bottom - top
                
                # Calculate background coordinates
                bg_x1 = label_x - 2
                bg_y1 = label_y - 1
                bg_x2 = label_x + text_width + 2
                bg_y2 = label_y + text_height + 1
                
                # Ensure label stays in bounds
                if bg_x2 > image.width:
                    offset = bg_x2 - image.width + 4
                    bg_x1 = max(0, bg_x1 - offset)
                    bg_x2 = min(image.width, bg_x2 - offset)
                    label_x = bg_x1 + 2
                
                # Draw label
                if 0 <= bg_x1 < bg_x2 <= image.width and 0 <= bg_y1 < bg_y2 <= image.height:
                    draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=color)
                    draw.text((label_x, label_y), label, fill='white')
            
            except Exception as e:
                logger.error(f"Error drawing detection: {e}")
                continue
        
        return img_draw
