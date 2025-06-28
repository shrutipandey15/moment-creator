import os
import json
import uuid
import re
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import assemblyai as aai
import yt_dlp
import lyricsgenius
from dotenv import load_dotenv
from thefuzz import fuzz

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_strong_default_secret_key_for_dev')
DATA_DIR = os.environ.get('RENDER_DISK_PATH', 'uploads') 
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')
app.config['MOMENTS_FOLDER'] = os.path.join(DATA_DIR, 'moments')
app.config['APP_BASE_URL'] = os.getenv('RENDER_EXTERNAL_URL', 'http://127.0.0.1:5000')

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_API_BASE_URL = 'https://www.googleapis.com/youtube/v3'

SUPPORTED_LANGUAGES = {
    'auto': 'Auto-detect',
    'en': 'English',
    'hi': 'Hindi',
    'pa': 'Punjabi',
    'ur': 'Urdu',
    'bn': 'Bengali',
    'ta': 'Tamil',
    'te': 'Telugu',
    'ml': 'Malayalam',
    'kn': 'Kannada',
    'gu': 'Gujarati',
    'mr': 'Marathi',
    'or': 'Odia'
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MOMENTS_FOLDER'], exist_ok=True)

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
genius_token = os.getenv("GENIUS_API_TOKEN")

if not all([aai.settings.api_key, genius_token, YOUTUBE_API_KEY]):
    print("CRITICAL ERROR: One or more API keys (AssemblyAI, Genius, YouTube) are not set.")

genius = lyricsgenius.Genius(genius_token, timeout=15, verbose=False, remove_section_headers=True)

def process_and_align(audio_path, lyrics_text, language_code='auto'):
    """Enhanced alignment function with language support."""
    print(f"Transcribing audio for timestamps (Language: {SUPPORTED_LANGUAGES.get(language_code, 'Auto-detect')})...")
    transcriber = aai.Transcriber()
    
    if language_code == 'auto':
        config = aai.TranscriptionConfig(language_detection=True)
    else:
        config = aai.TranscriptionConfig(language_code=language_code)
    
    transcript = transcriber.transcribe(audio_path, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    words = transcript.words
    if not words:
        raise Exception("No words found in transcription")

    if hasattr(transcript, 'language_code'):
        detected_lang = SUPPORTED_LANGUAGES.get(transcript.language_code, transcript.language_code)
        print(f"Detected language: {detected_lang}")

    print("Aligning lyrics...")
    poem_lines = [line.strip() for line in lyrics_text.strip().split('\n') if line.strip()]
    line_timings = []
    total_duration = words[-1].end / 1000.0 if words else 0
    
    word_index = 0
    for i, line_text in enumerate(poem_lines):
        clean_line = re.sub(r'[^\w\s]', '', line_text.lower())
        line_words = clean_line.split()
        
        if not line_words:
            line_duration = total_duration / len(poem_lines)
            start_time = i * line_duration
            end_time = (i + 1) * line_duration
            line_timings.append({'start': start_time, 'end': end_time})
            continue
        
        line_start_time = None
        line_end_time = None
        matched_words = 0
        
        search_start = max(0, word_index - 5)
        search_end = min(len(words), word_index + 20)
        
        for j in range(search_start, search_end):
            transcript_word = re.sub(r'[^\w\s]', '', words[j].text.lower())
            
            for line_word in line_words:
                if fuzz.ratio(transcript_word, line_word) > 80:
                    if line_start_time is None:
                        line_start_time = words[j].start / 1000.0
                    line_end_time = words[j].end / 1000.0
                    matched_words += 1
                    word_index = j + 1
                    break
        
        if matched_words > 0 and line_start_time is not None:
            line_timings.append({'start': line_start_time, 'end': line_end_time})
        else:
            line_duration = total_duration / len(poem_lines)
            start_time = i * line_duration
            end_time = (i + 1) * line_duration
            line_timings.append({'start': start_time, 'end': end_time})

    return poem_lines, line_timings

def search_youtube_videos(query, max_results=5):
    """Search YouTube videos using YouTube Data API."""
    if not YOUTUBE_API_KEY:
        return []
    url = f"{YOUTUBE_API_BASE_URL}/search"
    params = {'part': 'snippet', 'q': query, 'type': 'video', 'maxResults': max_results, 'key': YOUTUBE_API_KEY}
    response = requests.get(url, params=params)
    data = response.json()
    videos = []
    if 'items' in data:
        for item in data['items']:
            videos.append({
                'video_id': item['id']['videoId'],
                'title': item['snippet']['title'],
                'channel': item['snippet']['channelTitle'],
                'thumbnail': item['snippet']['thumbnails']['medium']['url']
            })
    return videos

@app.route('/')
def homepage():
    return render_template('creator.html', supported_languages=SUPPORTED_LANGUAGES)

@app.route('/search_youtube')
def search_youtube():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    try:
        videos = search_youtube_videos(query)
        return jsonify({'videos': videos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create', methods=['POST'])
def create_moment():
    try:
        lyrics_text = request.form.get('lyrics_text')
        title = request.form.get('title')
        youtube_url = request.form.get('youtube_url')
        audio_file = request.files.get('audio_file')
        language_code = request.form.get('language', 'auto')

        if language_code not in SUPPORTED_LANGUAGES:
            language_code = 'auto'

        print(f"Processing with language: {SUPPORTED_LANGUAGES.get(language_code)}")

        if youtube_url:
            print(f"Processing YouTube URL: {youtube_url}")
            temp_filename = str(uuid.uuid4())
            audio_output_template = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'outtmpl': audio_output_template,
                'quiet': True,
                'no_warnings': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                song_title = title or info.get('title', 'Untitled Song')
                artist = info.get('artist') or info.get('channel', 'Unknown Artist')

            audio_output_path = f"{audio_output_template}.mp3"
            audio_filename_to_save = f"{temp_filename}.mp3"
            
            lyrics_to_use = lyrics_text
            if not lyrics_to_use:
                try:
                    print(f"Attempting to fetch lyrics for '{song_title}' by {artist}...")
                    song = genius.search_song(song_title, artist)
                    if song and song.lyrics:
                        print("Successfully fetched lyrics from Genius.")
                        lyrics_to_use = re.sub(r'\[.*?\]', '', song.lyrics)
                    else:
                        raise Exception("Lyrics not found on Genius.")
                except Exception as e:
                    print(f"Automatic lyric lookup failed: {e}")
                    if language_code == 'pa':
                        raise Exception(f"Automatic lyric lookup failed for Punjabi content: {e}. Please provide lyrics manually as Genius may have limited Punjabi content.")
                    else:
                        raise Exception(f"Automatic lyric lookup failed: {e}. Please provide lyrics manually.")
            
        elif audio_file and audio_file.filename != '':
            if not title or not lyrics_text: 
                raise Exception("Title and Lyrics are required for file uploads.")
            
            song_title = title
            audio_filename_to_save = str(uuid.uuid4()) + os.path.splitext(audio_file.filename)[1]
            audio_output_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename_to_save)
            audio_file.save(audio_output_path)
            lyrics_to_use = lyrics_text
        
        else:
            raise Exception("Please provide either a YouTube URL or an audio file.")

        poem_lines, line_timings = process_and_align(audio_output_path, lyrics_to_use, language_code)
        
        moment_id = str(uuid.uuid4())
        moment_data = {
            "id": moment_id, 
            "title": song_title, 
            "audio_filename": audio_filename_to_save, 
            "lyrics": poem_lines, 
            "timings": line_timings,
            "language": language_code,
            "language_name": SUPPORTED_LANGUAGES.get(language_code, 'Auto-detect')
        }
        
        moment_file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
        with open(moment_file_path, 'w', encoding='utf-8') as f:
            json.dump(moment_data, f, indent=2, ensure_ascii=False)

        print(f"Successfully created moment: {moment_id} (Language: {SUPPORTED_LANGUAGES.get(language_code)})")
        return redirect(url_for('view_moment', moment_id=moment_id))

    except Exception as e:
        print(f"An error occurred: {e}")
        flash(f"An error occurred during processing. Please check your inputs and try again. Details: {e}")
        return redirect(url_for('homepage'))

@app.route('/moment/<moment_id>')
def view_moment(moment_id):
    file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            moment_data = json.load(f)
            return render_template('player.html', moment_data=moment_data, base_url=app.config['APP_BASE_URL'])
    except FileNotFoundError:
        return "This moment could not be found.", 404

@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)