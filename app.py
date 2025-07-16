import os
import json
import uuid
import re
import requests
import time
import random
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import assemblyai as aai
import yt_dlp
from yt_dlp.utils import DownloadError
import lyricsgenius
from dotenv import load_dotenv
from thefuzz import fuzz

# --- Initialization & Configuration ---
load_dotenv()
app = Flask(__name__)

# --- App Configuration ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_strong_default_secret_key_for_dev')
DATA_DIR = os.environ.get('RENDER_DISK_PATH', 'data')
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')
app.config['MOMENTS_FOLDER'] = os.path.join(DATA_DIR, 'moments')
app.config['APP_BASE_URL'] = os.getenv('RENDER_EXTERNAL_URL', 'http://127.0.0.1:5000')

# --- API Keys & Services ---
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GENIUS_API_TOKEN = os.getenv("GENIUS_API_TOKEN")

if not all([ASSEMBLYAI_API_KEY, GENIUS_API_TOKEN, YOUTUBE_API_KEY]):
    raise RuntimeError("CRITICAL ERROR: One or more required API keys (AssemblyAI, Genius, YouTube) are not set in the environment. The application cannot start.")

aai.settings.api_key = ASSEMBLYAI_API_KEY
genius = lyricsgenius.Genius(GENIUS_API_TOKEN, timeout=15, verbose=False, remove_section_headers=True)

# --- Directory Setup ---
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MOMENTS_FOLDER'], exist_ok=True)


# --- Core Processing Functions ---

def download_youtube_audio(youtube_url, output_template, max_retries=3):
    """
    Downloads audio from YouTube with optimized logic, retries, and robust error handling.
    """
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 60,
        'retries': 3,
        'ignoreerrors': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
        },
    }
    
    for attempt in range(max_retries):
        try:
            print(f"Download attempt {attempt + 1}/{max_retries}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True) 
                
                duration = info.get('duration')
                if duration and duration > 600:
                    return False, None, None, "Video is too long (over 10 minutes). Please choose a shorter one."
                
                final_filepath = info['requested_downloads'][0]['filepath']
                
                if os.path.exists(final_filepath):
                    print(f"Successfully downloaded audio to: {final_filepath}")
                    return True, info, final_filepath, None
                else:
                    raise Exception(f"File not found at expected path '{final_filepath}' after download.")

        except DownloadError as e:
            error_str = str(e)
            if 'HTTP Error 403: Forbidden' in error_str:
                 return False, None, None, "Download failed: YouTube is blocking requests from this server (403 Forbidden)."
            if 'Requested format is not available' in error_str:
                return False, None, None, "Download failed: A suitable audio format could not be found for this video."

            print(f"Download attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            else:
                return False, None, None, f"Download timed out after {max_retries} attempts. The network connection is likely too slow."
                
        except Exception as e:
            print(f"An unexpected error occurred during download: {e}")
            return False, None, None, f"An unexpected error prevented the download: {str(e)}"
    
    return False, None, None, "Download failed after all retry attempts."


def transcribe_audio(audio_path, language_code):
    print(f"Transcribing audio...")
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(language_detection=True if language_code == 'auto' else False, language_code=language_code if language_code != 'auto' else None)
    transcript = transcriber.transcribe(audio_path, config)
    if transcript.status == aai.TranscriptStatus.error: raise Exception(f"Transcription failed: {transcript.error}")
    if not transcript.words: raise Exception("Transcription successful, but no words were found.")
    return transcript.words

def align_lyrics(transcript_words, lyrics_text):
    print("Aligning lyrics...")
    poem_lines = [line.strip() for line in lyrics_text.strip().split('\n') if line.strip()]
    line_timings = []
    word_index = 0
    for line_text in poem_lines:
        clean_line = re.sub(r'[^\w\s]', '', line_text.lower())
        line_words = clean_line.split()
        if not line_words:
            line_timings.append({'start': 0, 'end': 0})
            continue
        best_match_index, highest_ratio = -1, 0
        search_start = max(0, word_index - 5)
        search_end = min(len(transcript_words), word_index + len(line_words) + 15)
        for j in range(search_start, search_end):
            transcript_chunk = ' '.join([re.sub(r'[^\w\s]', '', w.text.lower()) for w in transcript_words[j:j+len(line_words)]])
            ratio = fuzz.ratio(clean_line, transcript_chunk)
            if ratio > highest_ratio:
                highest_ratio, best_match_index = ratio, j
        if highest_ratio > 70 and best_match_index != -1:
            start_time = transcript_words[best_match_index].start / 1000.0
            end_time = transcript_words[min(best_match_index + len(line_words) - 1, len(transcript_words) - 1)].end / 1000.0
            word_index = best_match_index + len(line_words)
            line_timings.append({'start': start_time, 'end': end_time})
        else:
            line_timings.append({'start': 0, 'end': 0})
    return poem_lines, line_timings

def parse_title_and_artist(title_string, channel):
    cleaned_title = re.sub(r'[\(\[].*?[\)\]]', '', title_string).strip()
    separators = [' - ', ' – ', ' | ']
    artist, title = None, cleaned_title
    for sep in separators:
        if sep in cleaned_title:
            parts = cleaned_title.split(sep, 1)
            artist, title = (parts[0].strip(), parts[1].strip()) if len(parts[0]) < len(parts[1]) else (parts[1].strip(), parts[0].strip())
            break
    return {'artist': artist or channel, 'title': title}

def get_lyrics_from_genius(title, artist):
    """
    Fetches lyrics from Genius API and aggressively cleans them to remove metadata.
    """
    try:
        print(f"Fetching lyrics for '{title}' by {artist}...")
        song = genius.search_song(title, artist) or genius.search_song(title)
        if not song or not song.lyrics:
            return None

        lyrics = song.lyrics
        
        lines = lyrics.split('\n')
        
        start_index = 0
        for i, line in enumerate(lines):
            if 'lyrics' in line.lower() and i + 1 < len(lines):
                if lines[i+1].strip():
                    start_index = i + 1
                    break
            if line.strip().startswith('[') and line.strip().endswith(']'):
                start_index = i
                break
        
        if start_index == 0 and len(lines) > 1:
            start_index = 1

        cleaned_lyrics = '\n'.join(lines[start_index:])
        
        cleaned_lyrics = re.sub(r'\[.*?\]', '', cleaned_lyrics)
        cleaned_lyrics = re.sub(r'\d*Embed$', '', cleaned_lyrics)

        print("Successfully fetched and cleaned lyrics from Genius.")
        return cleaned_lyrics.strip()

    except Exception as e:
        print(f"Genius API lookup failed: {e}")
        return None

# --- Flask Routes ---

@app.route('/')
def homepage():
    return render_template('creator.html')

@app.route('/search_youtube')
def search_youtube():
    query = request.args.get('q', '')
    if not query: return jsonify({'error': 'Query parameter required'}), 400
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {'part': 'snippet', 'q': query, 'type': 'video', 'maxResults': 5, 'key': YOUTUBE_API_KEY}
        response = requests.get(url, params=params)
        response.raise_for_status()
        videos = [{'video_id': item['id']['videoId'], 'title': item['snippet']['title'], 'channel': item['snippet']['channelTitle'], 'thumbnail': item['snippet']['thumbnails']['medium']['url']} for item in response.json().get('items', [])]
        return jsonify({'videos': videos})
    except Exception as e:
        return jsonify({'error': f'An unexpected server error occurred: {e}'}), 500

@app.route('/create', methods=['POST'])
def create_moment():
    try:
        user_provided_title = request.form.get('title')
        lyrics_to_use = request.form.get('lyrics_text')
        youtube_url = request.form.get('youtube_url')
        audio_file = request.files.get('audio_file')
        language_code = request.form.get('language', 'auto')

        if not user_provided_title:
            raise Exception("A title is required to create a moment.")
        
        song_title_to_save = user_provided_title
        audio_output_path = None
        audio_filename_to_save = None

        if youtube_url:
            temp_filename = str(uuid.uuid4())
            audio_output_template = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            
            success, info, final_filepath, error_msg = download_youtube_audio(youtube_url, audio_output_template)
            
            if not success:
                raise Exception(error_msg)
            
            audio_output_path = final_filepath
            audio_filename_to_save = os.path.basename(final_filepath)
            
            raw_title = info.get('title', 'Untitled')
            channel = info.get('channel', 'Unknown Artist')
            parsed_info = parse_title_and_artist(raw_title, channel)
            song_title_to_save = parsed_info['title']
            
            if not lyrics_to_use:
                lyrics_to_use = get_lyrics_from_genius(parsed_info['title'], parsed_info['artist'])
                if not lyrics_to_use:
                    raise Exception("Could not automatically find lyrics. Please paste them manually.")
            
        elif audio_file and audio_file.filename:
            if not lyrics_to_use: raise Exception("Lyrics are required when uploading an audio file.")
            audio_filename_to_save = str(uuid.uuid4()) + os.path.splitext(audio_file.filename)[1]
            audio_output_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename_to_save)
            audio_file.save(audio_output_path)
        
        else:
            raise Exception("Please provide a YouTube URL or upload an audio file.")

        transcript_words = transcribe_audio(audio_output_path, language_code)
        poem_lines, line_timings = align_lyrics(transcript_words, lyrics_to_use)
        
        moment_id = str(uuid.uuid4())
        moment_data = {
            "id": moment_id, 
            "title": song_title_to_save, 
            "audio_filename": audio_filename_to_save, 
            "lyrics": poem_lines, 
            "timings": line_timings
        }
        
        moment_file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
        with open(moment_file_path, 'w', encoding='utf-8') as f:
            json.dump(moment_data, f, indent=2, ensure_ascii=False)

        print(f"Successfully created moment: {moment_id}")
        return redirect(url_for('view_moment', moment_id=moment_id))

    except Exception as e:
        error_message = str(e)
        print(f"An error occurred: {error_message}")
        flash(error_message)
        return redirect(url_for('homepage'))

@app.route('/moment/<moment_id>')
def view_moment(moment_id):
    file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            moment_data = json.load(f)
            return render_template('player.html', moment_data=moment_data, base_url=app.config['APP_BASE_URL'])
    except FileNotFoundError:
        flash("Sorry, the moment you are looking for could not be found.")
        return redirect(url_for('homepage'))

@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
