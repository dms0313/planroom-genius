"""
Data models for Fire Alarm PDF Analyzer
"""
from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass
class FireAlarmDevice:
    """Represents a detected fire alarm device"""
    device_type: str
    location: str
    page_number: int
    confidence: float
    x: int
    y: int
    width: int
    height: int
    notes: Optional[str] = None
    
    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class PageAnalysis:
    """Analysis results for a single PDF page"""
    page_number: int
    is_fire_alarm_page: bool
    page_type: str  # "special_systems", "power_plan", "mechanical", "other"
    devices: List[FireAlarmDevice]
    keyed_notes: List[str]
    specifications: List[str]
    
    def to_dict(self):
        """Convert to dictionary"""
        data = asdict(self)
        # Convert device objects to dicts
        data['devices'] = [d if isinstance(d, dict) else asdict(d) for d in self.devices]
        return data
