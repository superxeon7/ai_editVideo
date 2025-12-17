from typing import List, Optional, Literal
from pydantic import BaseModel, Field


EntityType = Literal[
    "supernatural_being",
    "location",
    "person",
    "object",
    "concept",
    "event"
]

VisualStyle = Literal[
    "horror_atmospheric",
    "neutral_cultural",
    "educational",
    "cinematic",
    "documentary"
]

InsertionType = Literal["overlay", "cutaway"]

Position = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]


class VisualInsertion(BaseModel):
    """AI decision for visual insertion"""
    word: str
    timestamp: float
    confidence: float = Field(ge=0.0, le=1.0)
    entity_type: EntityType
    visual_style: VisualStyle
    search_query: str
    duration: float = Field(default=1.5, ge=0.5, le=5.0)
    insertion_type: InsertionType = "overlay"
    position: Optional[Position] = "top-right"
    reasoning: str
    
    # Runtime fields (populated after asset fetch)
    asset_path: Optional[str] = None
    asset_type: Optional[Literal["image", "video"]] = None


class RejectedInsertion(BaseModel):
    """AI decision to reject insertion"""
    word: str
    timestamp: float
    confidence: float
    reasoning: str


class LLMDecisions(BaseModel):
    """Complete AI analysis output"""
    insertions: List[VisualInsertion]
    rejected: List[RejectedInsertion] = []
    metadata: dict = {}
    
    def filter_by_confidence(self, threshold: float) -> List[VisualInsertion]:
        """Filter insertions by confidence threshold"""
        return [
            insertion for insertion in self.insertions
            if insertion.confidence >= threshold
        ]
    
    def get_insertion_at_time(self, timestamp: float) -> Optional[VisualInsertion]:
        """Get insertion at specific timestamp"""
        for insertion in self.insertions:
            if insertion.timestamp <= timestamp <= insertion.timestamp + insertion.duration:
                return insertion
        return None