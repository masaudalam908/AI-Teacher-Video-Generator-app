# AI Teacher Video Generator

## What this starter app does
- Accepts a topic and duration from 3–15 minutes.
- Optionally uses Gemini to write a lesson script.
- Creates multiple classroom scenes with changing board text and simple diagrams.
- Generates narration with gTTS and assembles an MP4 with a preview/download button.

## Honest limitations
This is a working prototype, not a photorealistic AI video generator. The teacher is a drawn illustration, and mouth movement is not synchronized phoneme-by-phoneme. For realistic teacher footage and accurate lip-sync, integrate a paid avatar API such as HeyGen or D-ID. Scene-by-scene board overlays and avatar footage require additional compositing and API integration.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Google Colab
1. Upload `app.py` and `requirements.txt` to Colab, or create notebook cells that write these files.
2. Run `!pip install -r requirements.txt`.
3. Run `!streamlit run app.py &` (Colab does not provide a stable public URL by default; use a secure tunnel only if you understand its access implications).
4. For longer videos, Colab may disconnect or run out of memory/disk.

## Gemini API key
The key is optional. If using Gemini, create a key through Google AI Studio and pass it as `GEMINI_API_KEY` in your environment, or set it in Streamlit secrets:
```toml
GEMINI_API_KEY = "paste-your-key-here"
```
Never commit secrets to GitHub.

## GitHub and Streamlit Community Cloud
1. Create a GitHub repository.
2. Upload `app.py`, `requirements.txt`, and optionally this README through the repository's **Add file → Upload files** interface.
3. Do not upload API keys or `.streamlit/secrets.toml`.
4. In Streamlit Community Cloud, create an app from the repository and select `app.py`.
5. Open app settings → Secrets and add `GEMINI_API_KEY = "..."` if needed.
6. Deploy and test a short video before trying longer durations.

## Costs
- Streamlit Community Cloud and Colab availability/limits can change; check their current terms.
- gTTS is a network-backed text-to-speech library, not a guaranteed commercial-grade voice API. Check Google's terms before commercial use.
- Gemini API usage may be billed depending on model, region, and current pricing.
- Realistic avatar and video-generation services usually charge by video duration, credits, or generation. Check current provider pricing before enabling them.
