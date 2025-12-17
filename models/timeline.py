from typing import List, Literal
from pydantic import BaseModel
from models.decision import VisualInsertion


class PositionCoordinates(BaseModel):
    """FFmpeg position coordinates"""
    x: str  # e.g., "W-w-20" or "20"
    y: str  # e.g., "H-h-20" or "20"


class Transition(BaseModel):
    """Fade transition settings"""
    fade_in: float = 0.3
    fade_out: float = 0.3


class TimelineInsertion(BaseModel):
    """Single insertion in timeline"""
    id: str
    timestamp: float
    duration: float
    asset_path: str
    asset_type: Literal["image", "video"]
    insertion_type: Literal["overlay", "cutaway"]
    position: PositionCoordinates
    scale: float = 0.4
    opacity: float = 0.85
    transition: Transition


class TimelineMetadata(BaseModel):
    """Timeline processing metadata"""
    total_insertions: int
    total_duration: float
    render_complexity: Literal["low", "medium", "high"]


class Timeline(BaseModel):
    """Complete video editing timeline"""
    base_video: str
    aspect_ratio: Literal["9:16", "16:9"]
    insertions: List[TimelineInsertion]
    metadata: TimelineMetadata
    
    @staticmethod
    def from_decisions(
        base_video: str,
        aspect_ratio: str,
        decisions: List[VisualInsertion],
        config: dict
    ) -> 'Timeline':
        """Build timeline from LLM decisions"""
        insertions = []
        
        for idx, decision in enumerate(decisions):
            if not decision.asset_path:
                continue
                
            # Calculate position based on aspect ratio and preference
            position = Timeline._calculate_position(
                decision.position or "top-right",
                aspect_ratio
            )
            
            insertion = TimelineInsertion(
                id=f"ins_{idx:03d}",
                timestamp=decision.timestamp,
                duration=decision.duration,
                asset_path=decision.asset_path,
                asset_type=decision.asset_type or "image",
                insertion_type=decision.insertion_type,
                position=position,
                scale=config.get("default_scale", 0.4),
                opacity=config.get("default_opacity", 0.85),
                transition=Transition(
                    fade_in=config.get("fade_in", 0.3),
                    fade_out=config.get("fade_out", 0.3)
                )
            )
            insertions.append(insertion)
        
        # Calculate complexity
        complexity = "low"
        if len(insertions) > 5:
            complexity = "medium"
        if len(insertions) > 10:
            complexity = "high"
        
        return Timeline(
            base_video=base_video,
            aspect_ratio=aspect_ratio,
            insertions=insertions,
            metadata=TimelineMetadata(
                total_insertions=len(insertions),
                total_duration=max([i.timestamp + i.duration for i in insertions]) if insertions else 0,
                render_complexity=complexity
            )
        )
    
    @staticmethod
    def _calculate_position(position: str, aspect_ratio: str) -> PositionCoordinates:
        """Calculate FFmpeg position coordinates"""
        positions_map = {
            "top-left": PositionCoordinates(x="20", y="20"),
            "top-right": PositionCoordinates(x="W-w-20", y="20"),
            "bottom-left": PositionCoordinates(x="20", y="H-h-20"),
            "bottom-right": PositionCoordinates(x="W-w-20", y="H-h-20"),
            "center": PositionCoordinates(x="(W-w)/2", y="(H-h)/2")
        }
        
        return positions_map.get(position, positions_map["top-right"])