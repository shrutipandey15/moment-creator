# 🎶✨ Moment Creator

**Turn any song into a shareable, animated lyric experience.**  
Create a "moment" by syncing audio with its lyrics, select your favorite lines, and share a unique, interactive player with friends.

---

## 📌 About The Project

**Moment Creator** is a web application that brings music and words to life.  
Have you ever heard a line in a song that perfectly captures a feeling or a memory?  
This tool lets you isolate those lines, pair them with the music, and send them as a special, focused experience to someone else.

When a user receives a shared moment:

- The music plays
- The lyrics scroll by in sync
- Selected lines are highlighted
- A personal message appears with subtle animations

It creates a **powerful and personal impact** — like sending someone a lyrical postcard.

---

## 🚀 Core Features

- 🎥 **YouTube Integration**: Paste a YouTube link — we’ll extract the audio and song details.
- 🎵 **Direct Audio Upload**: Upload your own audio file if you prefer.
- 🧠 **Automatic Lyric Fetching**: Uses the Genius API (or paste your own).
- 🤖 **AI-Powered Syncing**: AssemblyAI transcribes the audio and aligns every word with precision.
- 🎧 **Interactive Web Player**: Elegant player with real-time lyric highlights.
- 💌 **Select & Share**: Choose any lyric line(s) to share with a custom message.
- 🔗 **Unique Shareable Links**: Every "moment" gets its own magical URL.

---

## ⚙️ How It Works

1. **Input**  
   Provide a song title and either a YouTube URL or audio upload. Lyrics can be fetched or manually added.

2. **Processing**  
   The backend uses `yt-dlp` to download audio from YouTube.

3. **Transcription**  
   The audio is sent to AssemblyAI for word-level timestamps.

4. **Alignment**  
   A Python script aligns the transcription with the user’s lyrics line by line.

5. **Moment Creation**  
   The finalized data (audio path, lyrics, timings, metadata) is stored in a JSON object.

6. **Playback & Sharing**  
   The frontend player reads the JSON and powers the lyric experience. Custom messages + selected lines are encoded into the shareable URL.

---

## 🛠️ Tech Stack

**Backend**  
- Python  
- Flask  

**Frontend**  
- HTML5  
- CSS3 (with CSS variables)  
- Vanilla JavaScript  

**APIs & Libraries**  
- [AssemblyAI](https://www.assemblyai.com/) – AI audio transcription  
- [Genius API](https://genius.com/developers) – Lyric fetching  
- [YouTube Data API](https://developers.google.com/youtube/registering_an_application) – YouTube search  
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) – YouTube audio extraction  
- [thefuzz](https://github.com/seatgeek/thefuzz) – Fuzzy string matching (if used)

**Deployment**  
- Render (with persistent disk support)  
- Gunicorn (production WSGI server for Flask)

---

## 🧑‍💻 Setup & Local Development

### 1. Prerequisites

- Python 3.8+
- Git

### 2. Installation

Clone the repository:

```bash
git clone https://github.com/your-username/moment-creator.git
cd moment-creator
```
### macOS/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```
### Windows

```bash
python -m venv venv
.\venv\Scripts\activate
```
### Install dependencies

```bash
pip install -r requirements.txt
```

### Setup environment variable
# Create a .env file in the root directory:

```ini
# Flask Secret Key
SECRET_KEY='your_super_secret_flask_key'

# API Keys
ASSEMBLYAI_API_KEY='your_assemblyai_api_key_here'
GENIUS_API_TOKEN='your_genius_api_token_here'
YOUTUBE_API_KEY='your_youtube_data_api_key_here'
```

---

## ❤️ A Note
This project was built with love for music, moments, and meaningful expression.
Whether you're capturing heartbreak, nostalgia, or joy — make it a moment worth remembering.

## 📄 License
This project is licensed under the MIT License.
See the LICENSE file for more details.

## ⚠️ Current Deployment Challenges

**Heads up!**  
As of 2025, there are ongoing issues with downloading YouTube audio via `yt-dlp` on server platforms like **Render**.

- Many requests are returning **403 Forbidden** or **400 Bad Request** errors due to recent changes in YouTube's bot detection systems.
- Projects like [cobalt.tools](https://github.com/imputnet/cobalt/issues/1356) and various `yt-dlp` deployments are affected.
- This issue seems **environment-specific** — `yt-dlp` often works perfectly on local machines but fails in hosted environments (like Render), sometimes due to IP blacklisting or sign-in restrictions.

💡 I’m currently exploring workarounds to deploy this app **without breaking YouTube integration**.  
If you’ve successfully solved this or found a reliable alternative, **I’d love to hear your approach** — feel free to open an issue or submit a pull request!

In the meantime, direct audio uploads remain the most stable option for deployed versions.

