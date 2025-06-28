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
import lyricsgenius
from dotenv import load_dotenv
from thefuzz import fuzz

load_dotenv()

# --- Configuration (Render-friendly) ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_strong_default_secret_key_for_dev')
DATA_DIR = os.environ.get('RENDER_DISK_PATH', 'uploads') 
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')
app.config['MOMENTS_FOLDER'] = os.path.join(DATA_DIR, 'moments')
app.config['APP_BASE_URL'] = os.getenv('RENDER_EXTERNAL_URL', 'http://127.0.0.1:5000')

# YouTube Data API configuration (for search)
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_API_BASE_URL = 'https://www.googleapis.com/youtube/v3'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MOMENTS_FOLDER'], exist_ok=True)

# --- API Key Setup ---
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
genius_token = os.getenv("GENIUS_API_TOKEN")

if not all([aai.settings.api_key, genius_token, YOUTUBE_API_KEY]):
    print("CRITICAL ERROR: One or more API keys (AssemblyAI, Genius, YouTube) are not set.")

genius = lyricsgenius.Genius(genius_token, timeout=15, verbose=False, remove_section_headers=True)

def get_random_user_agent():
    """Return a random user agent to avoid detection."""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0'
    ]
    return random.choice(user_agents)

def download_with_fallback_methods(youtube_url, output_path):
    """Try multiple download methods with different configurations."""
    
    # Method 1: Standard approach with enhanced headers
    methods = [
        {
            'name': 'Enhanced Headers',
            'opts': {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'source_address': '0.0.0.0',
                'http_headers': {
                    'User-Agent': get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                'sleep_interval': random.uniform(1, 3),
                'max_sleep_interval': 5,
                'retries': 3
            }
        },
        
        # Method 2: Use different player client
        {
            'name': 'Web Player Client',
            'opts': {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['web']}},
                'http_headers': {'User-Agent': get_random_user_agent()},
                'sleep_interval': random.uniform(1, 3)
            }
        },
        
        # Method 3: Mobile web client
        {
            'name': 'Mobile Web Client',
            'opts': {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['mweb']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1'
                },
                'sleep_interval': random.uniform(2, 4)
            }
        },
        
        # Method 4: Use cookies if available (environment variable)
        {
            'name': 'With Cookies',
            'opts': {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'http_headers': {'User-Agent': get_random_user_agent()},
                'sleep_interval': random.uniform(1, 3)
            }
        }
    ]
    
    # Add cookies to method 4 if available
    cookies_b64 = os.getenv('YOUTUBE_COOKIES_B64')
    if cookies_b64:
        try:
            import base64
            cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
            cookies_file = '/tmp/yt_cookies.txt'
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            methods[3]['opts']['cookiefile'] = cookies_file
            print("Using cookies from environment variable")
        except Exception as e:
            print(f"Failed to decode cookies: {e}")
            methods.pop(3)  # Remove cookie method if it fails
    else:
        methods.pop(3)  # Remove cookie method if no cookies available
    
    last_error = None
    
    for method in methods:
        try:
            print(f"Trying download method: {method['name']}")
            
            # Add random delay before each attempt
            time.sleep(random.uniform(0.5, 2.0))
            
            with yt_dlp.YoutubeDL(method['opts']) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                
                # Clean up temporary cookies file if it exists
                if 'cookiefile' in method['opts'] and os.path.exists(method['opts']['cookiefile']):
                    os.remove(method['opts']['cookiefile'])
                
                print(f"Successfully downloaded using method: {method['name']}")
                return info
                
        except Exception as e:
            print(f"Method '{method['name']}' failed: {str(e)}")
            last_error = e
            
            # Clean up temporary cookies file if it exists and method failed
            if 'cookiefile' in method['opts'] and os.path.exists(method['opts']['cookiefile']):
                os.remove(method['opts']['cookiefile'])
            
            # Wait before trying next method
            time.sleep(random.uniform(2, 5))
            continue
    
    # If all methods failed, raise the last error
    raise Exception(f"All download methods failed. Last error: {str(last_error)}")

def process_and_align(audio_path, lyrics_text):
    """Your robust alignment function remains here."""
    print("Transcribing audio for timestamps...")
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(language_detection=True)
    transcript = transcriber.transcribe(audio_path, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    words = transcript.words
    if not words:
        raise Exception("No words found in transcription")

    print("Aligning lyrics...")
    poem_lines = [line.strip() for line in lyrics_text.strip().split('\n') if line.strip()]
    line_timings = []
    total_duration = words[-1].end / 1000.0 if words else 0
    
    # Using a simple time-based fallback for alignment for now.
    for i, line_text in enumerate(poem_lines):
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
    return render_template('creator.html')

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

        if youtube_url:
            print(f"Processing YouTube URL: {youtube_url}")
            temp_filename = str(uuid.uuid4())
            audio_output_template = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            
            # Use the enhanced download function
            info = download_with_fallback_methods(youtube_url, audio_output_template)
            
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

        poem_lines, line_timings = process_and_align(audio_output_path, lyrics_to_use)
        
        moment_id = str(uuid.uuid4())
        moment_data = {
            "id": moment_id, 
            "title": song_title, 
            "audio_filename": audio_filename_to_save, 
            "lyrics": poem_lines, 
            "timings": line_timings
        }
        
        moment_file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
        with open(moment_file_path, 'w') as f:
            json.dump(moment_data, f, indent=2)

        print(f"Successfully created moment: {moment_id}")
        return redirect(url_for('view_moment', moment_id=moment_id))

    except Exception as e:
        print(f"An error occurred: {e}")
        flash(f"An error occurred during processing. Please check your inputs and try again. Details: {e}")
        return redirect(url_for('homepage'))

@app.route('/moment/<moment_id>')
def view_moment(moment_id):
    file_path = os.path.join(app.config['MOMENTS_FOLDER'], f'{moment_id}.json')
    try:
        with open(file_path, 'r') as f:
            moment_data = json.load(f)
            return render_template('player.html', moment_data=moment_data, base_url=app.config['APP_BASE_URL'])
    except FileNotFoundError:
        return "This moment could not be found.", 404

@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)