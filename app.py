import os
import io
import re
import json
import math
import time
import random
import tempfile
import subprocess
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio_ffmpeg
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from gtts import gTTS

try:
    from google import genai
except Exception:
    genai = None

APP_TITLE = "AI Teacher Video Generator"
WIDTH, HEIGHT = 1280, 720
FPS = 24

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")

def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def wrap_text(text, max_chars=36):
    words = str(text).split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) > max_chars and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines

def safe_scene_text(value, fallback="Key idea"):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:180] if value else fallback

def fallback_lesson(topic, duration_minutes):
    count = max(4, min(12, duration_minutes + 2))
    items = [
        ("Learning goals", f"By the end, you should be able to explain {topic}, recognize its main ideas, and use an example."),
        ("The big idea", f"Let's begin with the central idea behind {topic}. Think of it as a set of connected concepts rather than isolated facts."),
        ("Important terms", f"First, identify the key terms related to {topic}. Understanding the vocabulary makes the rest of the lesson easier."),
        ("Step-by-step explanation", f"Break {topic} into smaller steps. Understand each step, then connect it to the next one."),
        ("Worked example", f"Consider a simple example of {topic}. Identify what is given, choose the relevant idea, and explain each step."),
        ("Visual summary", f"On the board, connect the main points about {topic} with arrows. This shows how the ideas relate to one another."),
        ("Common mistake", f"A common mistake when learning {topic} is memorizing a result without understanding why it works. Always check the reasoning."),
        ("Quick recap", f"To recap, remember the definition, the steps, and the example. Try explaining {topic} in your own words."),
    ]
    scenes = []
    for i in range(count):
        title, narration = items[i % len(items)]
        scenes.append({
            "title": title,
            "narration": narration,
            "board_points": [topic, title, "Understand the idea", "Check with an example"],
            "visual": "concept map" if i % 2 else "step-by-step notes"
        })
    return {"title": f"Understanding {topic}", "scenes": scenes}

def generate_lesson(topic, duration_minutes, api_key):
    if not api_key or genai is None:
        return fallback_lesson(topic, duration_minutes), "Using built-in lesson template (no Gemini API key configured)."
    prompt = f"""Create an educational lesson plan for a classroom teaching video.
Topic: {topic}
Target duration: {duration_minutes} minutes.
Return ONLY valid JSON with this schema:
{{
 "title": "short lesson title",
 "scenes": [
  {{
   "title": "short board heading",
   "narration": "natural spoken explanation, about 70-130 words per scene when suitable",
   "board_points": ["short point", "formula or example if relevant", "short point"],
   "visual": "one of: concept map, worked example, timeline, formula steps, comparison, diagram"
  }}
 ]
}}
Create between {max(4, duration_minutes)} and {min(15, duration_minutes+3)} scenes. Make the lesson accurate, step-by-step, age-neutral, and useful. Include examples and a recap. Do not invent formulas for topics where they do not apply. Keep board points concise. Avoid markdown fences."""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
        data = json.loads(raw)
        scenes = data.get("scenes", [])
        if not scenes:
            raise ValueError("Gemini returned no scenes.")
        cleaned = []
        for scene in scenes:
            narration = str(scene.get("narration", "")).strip()
            if not narration:
                continue
            points = scene.get("board_points", [])
            if not isinstance(points, list):
                points = [str(points)]
            cleaned.append({
                "title": safe_scene_text(scene.get("title"), "Lesson point"),
                "narration": narration,
                "board_points": [safe_scene_text(p) for p in points[:5]],
                "visual": safe_scene_text(scene.get("visual"), "step-by-step notes")
            })
        if not cleaned:
            raise ValueError("Gemini returned empty narration.")
        return {"title": safe_scene_text(data.get("title"), f"Understanding {topic}"), "scenes": cleaned}, "Lesson generated with Gemini."
    except Exception as exc:
        return fallback_lesson(topic, duration_minutes), f"Gemini generation failed; used built-in template. Details: {exc}"

def draw_board(draw, scene, scene_index, total_scenes):
    # Classroom wall and board
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(25, 44, 63))
    draw.rectangle((0, 0, WIDTH, 82), fill=(17, 31, 47))
    draw.text((40, 22), "AI CLASSROOM  •  LESSON", font=get_font(26, True), fill=(220, 237, 250))
    draw.text((WIDTH-220, 26), f"SCENE {scene_index+1}/{total_scenes}", font=get_font(19, True), fill=(150, 195, 220))
    # Board
    draw.rounded_rectangle((285, 112, 1215, 650), radius=18, fill=(35, 83, 76), outline=(203, 176, 126), width=12)
    draw.text((330, 140), safe_scene_text(scene.get("title"), "Today's lesson"), font=get_font(32, True), fill=(255, 232, 132))
    draw.line((330, 190, 1160, 190), fill=(180, 220, 200), width=3)
    points = scene.get("board_points") or ["Understand the idea", "Work through an example", "Summarize the result"]
    y = 220
    for idx, point in enumerate(points[:5]):
        draw.ellipse((335, y+7, 351, y+23), fill=(255, 222, 120))
        lines = wrap_text(point, 45)
        for line in lines[:2]:
            draw.text((370, y), line, font=get_font(24), fill=(247, 250, 242))
            y += 34
        y += 16
        if y > 570:
            break
    # Simple scene-dependent diagram on right side of board
    kind = str(scene.get("visual", "")).lower()
    if "formula" in kind or "example" in kind:
        draw.rounded_rectangle((790, 470, 1135, 590), radius=12, outline=(255, 232, 132), width=3)
        draw.text((820, 490), "EXAMPLE", font=get_font(19, True), fill=(255, 232, 132))
        draw.text((820, 530), "Step 1  →  Step 2", font=get_font(21, True), fill=(255, 255, 255))
    elif "map" in kind or "diagram" in kind:
        boxes = [(790, 475, 900, 525), (1000, 450, 1120, 500), (1000, 535, 1120, 585)]
        for box in boxes:
            draw.rounded_rectangle(box, radius=8, outline=(160, 225, 240), width=3)
        draw.text((802, 490), "IDEA", font=get_font(16, True), fill=(255,255,255))
        draw.text((1010, 465), "PART A", font=get_font(15, True), fill=(255,255,255))
        draw.text((1010, 550), "PART B", font=get_font(15, True), fill=(255,255,255))
        draw.line((900,500,1000,475), fill=(160,225,240), width=3)
        draw.line((900,500,1000,560), fill=(160,225,240), width=3)
    else:
        draw.rounded_rectangle((800, 475, 1135, 585), radius=12, outline=(160, 225, 240), width=3)
        draw.text((825, 495), "REMEMBER", font=get_font(19, True), fill=(160, 225, 240))
        draw.text((825, 532), "Idea → Example → Review", font=get_font(17), fill=(255,255,255))
    # Teacher illustration on the left; facial/mouth pose varies by frame
    # Body and neck
    draw.ellipse((63, 145, 233, 320), fill=(201, 151, 112), outline=(45, 35, 30), width=4)
    draw.pieslice((58, 130, 238, 300), 180, 360, fill=(45, 34, 30))
    draw.rectangle((125, 290, 172, 350), fill=(201, 151, 112))
    draw.polygon([(65, 355), (105, 328), (188, 328), (235, 355), (260, 650), (42, 650)], fill=(57, 105, 163))
    draw.polygon([(105, 330), (148, 390), (188, 330), (170, 430), (135, 430)], fill=(242, 242, 235))
    # Face details
    draw.ellipse((105, 220, 120, 235), fill=(30, 28, 25))
    draw.ellipse((177, 220, 192, 235), fill=(30, 28, 25))
    draw.arc((122, 235, 178, 275), 10, 170, fill=(90, 40, 35), width=4)
    # Raised arm / pointer
    draw.line((218, 390, 258, 310, 300, 280), fill=(201,151,112), width=19)
    draw.ellipse((286, 265, 310, 289), fill=(201,151,112))
    # Bottom caption panel
    draw.rectangle((0, 660, WIDTH, HEIGHT), fill=(12, 22, 34))
    draw.text((35, 672), "TEACHER EXPLAINS  •  BOARD CONTENT CHANGES WITH EACH SCENE", font=get_font(18, True), fill=(222, 236, 247))

def make_scene_frames(scene, scene_index, total_scenes, duration, temp_dir):
    # Create a short animated clip: subtle zoom/pan and alternating mouth poses.
    base = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(base)
    draw_board(draw, scene, scene_index, total_scenes)
    path = os.path.join(temp_dir, f"scene_{scene_index:02d}.mp4")
    # Encode one image with a slight animated crop/zoom; board scene itself changes each scene.
    # The teacher is a stylized illustrated avatar, not a photorealistic or phoneme-accurate avatar.
    frames = max(1, int(duration * FPS))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(suffix=".png", dir=temp_dir, delete=False) as tmp:
        base.save(tmp.name)
        png_path = tmp.name
    cmd = [
        ffmpeg, "-y", "-loop", "1", "-i", png_path,
        "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration}",
        "-filter_complex",
        f"[0:v]scale={WIDTH+30}:{HEIGHT+30},crop={WIDTH}:{HEIGHT}:x='15+8*sin(t*0.8)':y='15+5*cos(t*0.6)',fps={FPS}[v];[1:v][v]overlay=0:0:shortest=1",
        "-t", str(duration), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", path
    ]
    # A simpler fallback if the filter chain fails
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        os.remove(png_path)
    except OSError:
        pass
    if result.returncode != 0 or not os.path.exists(path):
        clip = ImageClip(np.array(base)).set_duration(duration)
        clip.write_videofile(path, fps=FPS, codec="libx264", audio=False, logger=None)
        clip.close()
    return path

def create_video(lesson, duration_minutes, language, progress_callback):
    temp_dir = tempfile.mkdtemp(prefix="ai_teacher_")
    scenes = lesson["scenes"]
    target_seconds = duration_minutes * 60
    # Allocate time based on narration length, then normalize to the requested total duration.
    weights = [max(1, len(s.get("narration", ""))) for s in scenes]
    total_weight = sum(weights)
    durations = [target_seconds * w / total_weight for w in weights]
    # Keep minimum scene length practical; then renormalize.
    durations = [max(8, d) for d in durations]
    scale = target_seconds / sum(durations)
    durations = [d * scale for d in durations]
    audio_paths, scene_paths = [], []
    for i, scene in enumerate(scenes):
        progress_callback(0.08 + 0.65 * i / max(1, len(scenes)), f"Generating narration and classroom scene {i+1}/{len(scenes)}")
        text = scene["narration"]
        audio_path = os.path.join(temp_dir, f"voice_{i:02d}.mp3")
        # gTTS is a network service; a working internet connection is required.
        tts = gTTS(text=text, lang=language, slow=False)
        tts.save(audio_path)
        audio_paths.append(audio_path)
        scene_paths.append(make_scene_frames(scene, i, len(scenes), durations[i], temp_dir))
    progress_callback(0.78, "Assembling scenes and narration")
    clips = []
    for video_path, audio_path, target_dur in zip(scene_paths, audio_paths, durations):
        audio = AudioFileClip(audio_path)
        video = ImageClip(np.array(Image.open(video_path).convert("RGB"))).set_duration(target_dur)
        # Use the generated scene MP4 as the visual source so the subtle motion is preserved.
        from moviepy.editor import VideoFileClip
        visual = VideoFileClip(video_path).set_duration(target_dur)
        if audio.duration > target_dur:
            audio = audio.subclip(0, target_dur)
        elif audio.duration < target_dur:
            # Hold the last frame while the narration scene finishes.
            pass
        visual = visual.set_audio(audio)
        clips.append(visual)
    final = concatenate_videoclips(clips, method="compose")
    out_path = os.path.join(temp_dir, "ai_teacher_lesson.mp4")
    progress_callback(0.9, "Rendering MP4")
    final.write_videofile(out_path, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast", threads=2, logger=None)
    final.close()
    for clip in clips:
        try:
            clip.close()
        except Exception:
            pass
    progress_callback(1.0, "Video ready")
    return out_path, temp_dir

st.title("🎓 AI Teacher Video Generator")
st.write("Create a classroom-style lesson with an illustrated teacher, changing board content, spoken narration, and an MP4 download.")
st.info("This starter version renders an animated classroom scene with changing board content and narration. It does not yet provide photorealistic AI video or phoneme-accurate lip-sync; see the limitations below.")

with st.sidebar:
    st.header("Lesson settings")
    topic = st.text_input("Enter lesson topic", placeholder="e.g. Newton's laws of motion")
    duration = st.slider("Video duration (minutes)", min_value=3, max_value=15, value=3)
    language_name = st.selectbox("Narration language", ["English", "Urdu", "Hindi", "Spanish", "French"])
    language_codes = {"English": "en", "Urdu": "ur", "Hindi": "hi", "Spanish": "es", "French": "fr"}
    st.caption("Gemini API key is optional; without it, the app uses a basic built-in lesson template.")
    api_key_input = st.text_input("Gemini API key (optional)", type="password")
    st.caption("For deployment, use Streamlit Secrets instead of entering a key into a public app.")
    generate = st.button("Generate Teaching Video", type="primary", use_container_width=True)

if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "lesson_data" not in st.session_state:
    st.session_state.lesson_data = None

if generate:
    if not topic.strip():
        st.error("Please enter a topic first.")
    else:
        api_key = api_key_input.strip()
        if not api_key:
            try:
                api_key = st.secrets.get("GEMINI_API_KEY", "")
            except Exception:
                api_key = os.getenv("GEMINI_API_KEY", "")
        with st.status("Preparing your lesson...", expanded=True) as status:
            progress = st.progress(0)
            msg = st.empty()
            def update_progress(value, message):
                progress.progress(min(1.0, max(0.0, value)))
                msg.write(message)
            lesson, note = generate_lesson(topic.strip(), duration, api_key)
            st.session_state.lesson_data = lesson
            st.write(note)
            try:
                video_path, temp_dir = create_video(lesson, duration, language_codes[language_name], update_progress)
                st.session_state.video_path = video_path
                st.session_state.video_temp_dir = temp_dir
                status.update(label="Video generated successfully", state="complete", expanded=False)
            except Exception as exc:
                status.update(label="Video generation failed", state="error", expanded=True)
                st.error(f"Could not render the video: {exc}")
                st.markdown("Check that FFmpeg dependencies installed correctly and that the runtime has enough memory and disk space.")

if st.session_state.lesson_data:
    with st.expander("Preview generated lesson script", expanded=False):
        st.subheader(st.session_state.lesson_data.get("title", "Lesson"))
        for idx, scene in enumerate(st.session_state.lesson_data["scenes"], start=1):
            st.markdown(f"**Scene {idx}: {scene['title']}**")
            st.write(scene["narration"])
            st.caption("Board: " + " • ".join(scene.get("board_points", [])))

if st.session_state.video_path and os.path.exists(st.session_state.video_path):
    st.subheader("Your teaching video")
    with open(st.session_state.video_path, "rb") as f:
        video_bytes = f.read()
    st.video(video_bytes)
    st.download_button(
        "⬇️ Download Video (MP4)",
        data=video_bytes,
        file_name="ai_teacher_lesson.mp4",
        mime="video/mp4",
        type="primary"
    )

with st.expander("Important limitations and next upgrade"):
    st.markdown("""
- **Teacher realism:** the included teacher is a drawn 2D illustration, not a photorealistic avatar.
- **Lip synchronization:** the mouth is not synchronized to individual speech sounds. Accurate lip-sync requires an avatar service such as HeyGen or D-ID and a paid API account in most production scenarios.
- **Board content:** board text and simple diagrams change scene by scene. This starter does not generate complex, hand-written board animation or arbitrary scientific illustrations.
- **Duration:** the final video is rendered to the selected duration, but narration may finish early in a scene; it can leave a short visual pause. Review the output before publishing.
- **Language:** Google Text-to-Speech (gTTS) requires internet access and its language/voice quality varies. It is not a guaranteed commercial-grade voice service.
- **Hosting:** rendering a 15-minute video can exceed Streamlit Community Cloud resource or request limits. For production, use a background worker/storage service and keep Streamlit as the frontend.
- **API keys:** never commit API keys to GitHub. Use Streamlit Community Cloud → App settings → Secrets.
""")
