import whisper
import logging
from typing import Optional
from models.transcript import Transcript, Segment, Word
from utils.audio import get_audio_duration

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription errors"""
    pass


def transcribe(
    audio_path: str,
    model_size: str = "base",
    language: str = "id",
    word_timestamps: bool = True
) -> Transcript:
    """
    Transcribe audio file using Whisper
    
    Args:
        audio_path: Path to audio file
        model_size: Whisper model size (tiny, base, small, medium, large)
        language: Language code (id for Indonesian, en for English)
        word_timestamps: Whether to generate word-level timestamps
        
    Returns:
        Transcript object with segments and words
        
    Raises:
        TranscriptionError: If transcription fails
    """
    logger.info(f"Loading Whisper model: {model_size}")
    
    try:
        # Load Whisper model
        model = whisper.load_model(model_size)
        
        logger.info(f"Transcribing audio: {audio_path}")
        
        # Transcribe with word timestamps
        result = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            word_timestamps=word_timestamps,
            verbose=False
        )
        
        # Get audio duration
        duration = get_audio_duration(audio_path)
        
        # Parse Whisper output into our models
        segments = []
        
        for seg in result.get('segments', []):
            # Extract words with timestamps
            words = []
            
            if word_timestamps and 'words' in seg:
                for word_data in seg['words']:
                    word = Word(
                        word=word_data.get('word', '').strip(),
                        start=word_data.get('start', 0.0),
                        end=word_data.get('end', 0.0)
                    )
                    words.append(word)
            else:
                # Fallback: create single word from segment text
                word = Word(
                    word=seg.get('text', '').strip(),
                    start=seg.get('start', 0.0),
                    end=seg.get('end', 0.0)
                )
                words.append(word)
            
            segment = Segment(
                start=seg.get('start', 0.0),
                end=seg.get('end', 0.0),
                text=seg.get('text', '').strip(),
                words=words
            )
            segments.append(segment)
        
        transcript = Transcript(
            segments=segments,
            language=result.get('language', language),
            duration=duration
        )
        
        # Validate transcript
        total_words = len(transcript.get_all_words())
        
        if total_words == 0:
            raise TranscriptionError("No speech detected in audio")
        
        if total_words < 10:
            logger.warning(f"Very short transcript detected: only {total_words} words")
        
        logger.info(
            f"Transcription complete: {len(segments)} segments, "
            f"{total_words} words, {duration:.2f}s duration"
        )
        
        return transcript
        
    except whisper.ModelNotFoundError as e:
        logger.error(f"Whisper model not found: {model_size}")
        raise TranscriptionError(f"Invalid model size: {model_size}")
        
    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")


def transcribe_with_retry(
    audio_path: str,
    model_size: str = "base",
    language: str = "id",
    max_retries: int = 2
) -> Optional[Transcript]:
    """
    Transcribe with retry logic and fallback models
    
    Args:
        audio_path: Path to audio file
        model_size: Initial model size
        language: Language code
        max_retries: Maximum retry attempts
        
    Returns:
        Transcript or None if all attempts fail
    """
    models_to_try = [model_size]
    
    # Add fallback models
    if model_size not in ['tiny', 'base']:
        models_to_try.append('base')
    if 'tiny' not in models_to_try:
        models_to_try.append('tiny')
    
    for attempt, model in enumerate(models_to_try, 1):
        try:
            logger.info(f"Transcription attempt {attempt}/{len(models_to_try)} with model: {model}")
            return transcribe(audio_path, model_size=model, language=language)
            
        except TranscriptionError as e:
            if attempt == len(models_to_try):
                logger.error(f"All transcription attempts failed")
                raise
            else:
                logger.warning(f"Attempt {attempt} failed, trying next model")
                continue
    
    return None


def get_transcript_summary(transcript: Transcript) -> dict:
    """
    Get summary statistics from transcript
    
    Args:
        transcript: Transcript object
        
    Returns:
        Dictionary with summary stats
    """
    all_words = transcript.get_all_words()
    
    return {
        "total_segments": len(transcript.segments),
        "total_words": len(all_words),
        "duration": transcript.duration,
        "language": transcript.language,
        "words_per_minute": round(len(all_words) / (transcript.duration / 60), 2) if transcript.duration > 0 else 0,
        "avg_words_per_segment": round(len(all_words) / len(transcript.segments), 2) if transcript.segments else 0
    }