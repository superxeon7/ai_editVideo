from typing import List, Optional
from pydantic import BaseModel, Field


class Word(BaseModel):
    """Individual word with timestamp"""
    word: str
    start: float
    end: float
    confidence: Optional[float] = None


class Segment(BaseModel):
    """Speech segment containing multiple words"""
    start: float
    end: float
    text: str
    words: List[Word]


class Transcript(BaseModel):
    """Complete transcript of video audio"""
    segments: List[Segment]
    language: str
    duration: float
    
    def get_all_words(self) -> List[Word]:
        """Get flat list of all words"""
        words = []
        for segment in self.segments:
            words.extend(segment.words)
        return words
    
    def get_words_in_range(self, start: float, end: float) -> List[Word]:
        """Get words within time range"""
        return [
            word for segment in self.segments
            for word in segment.words
            if start <= word.start <= end
        ]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for LLM input"""
        return {
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "words": [
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end
                        }
                        for w in seg.words
                    ]
                }
                for seg in self.segments
            ],
            "language": self.language,
            "duration": self.duration
        }