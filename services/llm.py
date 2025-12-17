import os
import json
import logging
from typing import Optional
from anthropic import Anthropic
from models.transcript import Transcript
from models.decision import LLMDecisions, VisualInsertion, RejectedInsertion
from utils.validators import validate_insertions_frequency, validate_insertion_bounds

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Custom exception for LLM errors"""
    pass


def load_system_prompt(prompt_path: str) -> str:
    """Load system prompt from file"""
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def analyze(
    transcript: Transcript,
    prompt_path: str,
    threshold: float = 0.75,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    aspect_ratio: str = "9:16"
) -> LLMDecisions:
    """
    Analyze transcript using Claude LLM to generate visual insertion decisions
    
    Args:
        transcript: Transcript object
        prompt_path: Path to system prompt file
        threshold: Confidence threshold for filtering
        api_key: Anthropic API key (optional, uses env var if not provided)
        model: Claude model to use
        aspect_ratio: Video aspect ratio
        
    Returns:
        LLMDecisions object with insertions and rejections
        
    Raises:
        LLMError: If LLM analysis fails
    """
    logger.info("Starting LLM analysis of transcript")
    
    try:
        # Load system prompt
        system_prompt = load_system_prompt(prompt_path)
        
        # Prepare input for LLM
        llm_input = {
            "transcript": transcript.to_dict()["segments"],
            "video_duration": transcript.duration,
            "aspect_ratio": aspect_ratio,
            "language": transcript.language
        }
        
        # Initialize Anthropic client
        api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY not found in environment")
        
        client = Anthropic(api_key=api_key)
        
        logger.info(f"Calling Claude API with model: {model}")
        
        # Call Claude API
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(llm_input, ensure_ascii=False, indent=2)
                }
            ]
        )
        
        # Extract response
        response_text = message.content[0].text
        
        logger.debug(f"LLM Response: {response_text}")
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        response_data = json.loads(response_text.strip())
        
        # Parse insertions
        insertions = []
        for ins_data in response_data.get('insertions', []):
            try:
                insertion = VisualInsertion(**ins_data)
                insertions.append(insertion)
            except Exception as e:
                logger.warning(f"Failed to parse insertion: {str(e)}")
                continue
        
        # Parse rejections
        rejections = []
        for rej_data in response_data.get('rejected', []):
            try:
                rejection = RejectedInsertion(**rej_data)
                rejections.append(rejection)
            except Exception as e:
                logger.warning(f"Failed to parse rejection: {str(e)}")
                continue
        
        # Filter by confidence threshold
        filtered_insertions = [
            ins for ins in insertions
            if ins.confidence >= threshold
        ]
        
        rejected_low_confidence = len(insertions) - len(filtered_insertions)
        if rejected_low_confidence > 0:
            logger.info(
                f"Filtered out {rejected_low_confidence} insertions "
                f"below confidence threshold {threshold}"
            )
        
        # Validate frequency constraints (max 1 per 10 seconds)
        filtered_insertions = validate_insertions_frequency(
            filtered_insertions,
            max_per_interval=1,
            interval=10.0
        )
        
        # Validate time bounds
        filtered_insertions = validate_insertion_bounds(
            filtered_insertions,
            transcript.duration
        )
        
        decisions = LLMDecisions(
            insertions=filtered_insertions,
            rejected=rejections,
            metadata=response_data.get('metadata', {})
        )
        
        logger.info(
            f"LLM analysis complete: {len(decisions.insertions)} insertions, "
            f"{len(decisions.rejected)} rejections"
        )
        
        return decisions
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
        logger.error(f"Response text: {response_text}")
        raise LLMError(f"Invalid JSON response from LLM: {str(e)}")
        
    except Exception as e:
        logger.error(f"LLM analysis failed: {str(e)}")
        raise LLMError(f"Failed to analyze transcript: {str(e)}")


def analyze_with_retry(
    transcript: Transcript,
    prompt_path: str,
    threshold: float = 0.75,
    max_retries: int = 2,
    **kwargs
) -> Optional[LLMDecisions]:
    """
    Analyze with retry logic for handling rate limits
    
    Args:
        transcript: Transcript object
        prompt_path: Path to system prompt
        threshold: Confidence threshold
        max_retries: Maximum retry attempts
        **kwargs: Additional arguments for analyze()
        
    Returns:
        LLMDecisions or None if all attempts fail
    """
    import time
    
    for attempt in range(max_retries + 1):
        try:
            return analyze(transcript, prompt_path, threshold, **kwargs)
            
        except LLMError as e:
            if 'rate limit' in str(e).lower() and attempt < max_retries:
                wait_time = 5 * (attempt + 1)  # Exponential backoff
                logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                time.sleep(wait_time)
                continue
            else:
                raise
    
    return None


def get_decisions_summary(decisions: LLMDecisions) -> dict:
    """
    Get summary of LLM decisions
    
    Args:
        decisions: LLMDecisions object
        
    Returns:
        Dictionary with summary stats
    """
    if not decisions.insertions:
        return {
            "total_insertions": 0,
            "total_rejected": len(decisions.rejected),
            "avg_confidence": 0.0,
            "entity_types": {},
            "visual_styles": {}
        }
    
    # Calculate statistics
    confidences = [ins.confidence for ins in decisions.insertions]
    entity_types = {}
    visual_styles = {}
    
    for ins in decisions.insertions:
        entity_types[ins.entity_type] = entity_types.get(ins.entity_type, 0) + 1
        visual_styles[ins.visual_style] = visual_styles.get(ins.visual_style, 0) + 1
    
    return {
        "total_insertions": len(decisions.insertions),
        "total_rejected": len(decisions.rejected),
        "avg_confidence": round(sum(confidences) / len(confidences), 3),
        "min_confidence": round(min(confidences), 3),
        "max_confidence": round(max(confidences), 3),
        "entity_types": entity_types,
        "visual_styles": visual_styles
    }