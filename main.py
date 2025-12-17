from services.transcriber import transcribe
from services.llm import analyze
from services.renderer import render
from utils.audio import extract_audio
import yaml

config = yaml.safe_load(open("config.yml"))

audio = extract_audio("input/raw_video.mp4")
transcript = transcribe(audio)

decisions = analyze(
    transcript=transcript,
    prompt_path="prompt/visual_mapper.txt",
    threshold=config["confidence_threshold"]
)

render(
    video="input/raw_video.mp4",
    decisions=decisions,
    output="output/final.mp4"
)
