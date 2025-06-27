import os
import json
import uuid
import re
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import assemblyai as aai
import yt_dlp
import lyricsgenius
from dotenv import load_dotenv
from thefuzz import fuzz

load_dotenv()

# --- Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_change_this_later'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MOMENTS_FOLDER'] = 'moments'
app.config['APP_BASE_URL'] = os.getenv('PUBLIC_URL', 'http://127.0.0.1:5000')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MOMENTS_FOLDER'], exist_ok=True)

# --- API Key Setup ---
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
genius_token = os.getenv("GENIUS_API_TOKEN")

if not aai.settings.api_key or not genius_token:
    print("CRITICAL ERROR: API keys for AssemblyAI or Genius are not set as environment variables.")

genius = lyricsgenius.Genius(genius_token, timeout=15, verbose=False, remove_section_headers=True)

def normalize_text_multilingual(text):
    """
    Normalize text for Hindi, English, Hinglish, and Urdu matching
    """
    text = re.sub(r'[^\w\s]', '', text).lower()
    
    replacements = {
        'kh': 'k', 'gh': 'g', 'ch': 'c', 'jh': 'j', 'th': 't', 'dh': 'd', 
        'ph': 'f', 'bh': 'b', 'rh': 'r', 'lh': 'l', 'nh': 'n', 'sh': 's',
        
        'aa': 'a', 'aaa': 'a', 'ee': 'i', 'eee': 'i', 'oo': 'u', 'ooo': 'u',
        'ai': 'e', 'ay': 'e', 'au': 'o', 'aw': 'o', 'ou': 'o',
        
        'yeh': 'ye', 'yeah': 'ye', 'hai': 'he', 'hain': 'hen', 'he': 'he',
        'mein': 'me', 'main': 'me', 'mai': 'me', 'me': 'me',
        'aur': 'or', 'our': 'or', 'ur': 'or',
        'tum': 'tum', 'tumse': 'tumse', 'tumko': 'tumko',
        'ishq': 'ishk', 'ishk': 'ishk', 'eshq': 'ishk',
        'karta': 'karta', 'karte': 'karte', 'karti': 'karti',
        'kehta': 'kehta', 'kehte': 'kehte', 'kehti': 'kehti',
        'dekho': 'dekho', 'dekh': 'dekh', 'dekhna': 'dekhna',
        'kya': 'kya', 'kia': 'kya', 'kyaa': 'kya',
        'bhi': 'bhi', 'bi': 'bhi', 'bhee': 'bhi',
        'nahi': 'nahi', 'nahin': 'nahi', 'nai': 'nahi',
        'woh': 'wo', 'wo': 'wo', 'voh': 'wo',
        'tera': 'tera', 'tere': 'tere', 'teri': 'teri',
        'mera': 'mera', 'mere': 'mere', 'meri': 'meri',
        'hona': 'hona', 'ho': 'ho', 'hoo': 'ho',
        'jaha': 'jaha', 'jahan': 'jahan', 'jahaan': 'jahan',
        'sab': 'sab', 'sabko': 'sabko', 'sabse': 'sabse',
        'love': 'love', 'luv': 'love', 'lav': 'love',
        'mohabbat': 'mohabbat', 'muhabbat': 'mohabbat',
        'dil': 'dil', 'del': 'dil', 'heart': 'dil',
        'pyar': 'pyar', 'pyaar': 'pyar', 'piyar': 'pyar',
        
        'husn': 'husn', 'ishqe': 'ishk', 'muhib': 'muhib',
        'jamal': 'jamal', 'karam': 'karam', 'rehm': 'rehm',
        
        'the': 'the', 'and': 'and', 'you': 'you', 'your': 'your',
        'with': 'with', 'like': 'like', 'when': 'when', 'what': 'what'
    }
    
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)
    
    text = re.sub(r'(.)\1{2,}', r'\1', text)
    
    return ' '.join(text.split())

def extract_meaningful_words(text):
    """
    Extract meaningful words for matching (ignore very short words and common fillers)
    """
    stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 
                  'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
                  'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'as', 'but', 'or', 'and',
                  'ka', 'ke', 'ki', 'ko', 'se', 'me', 'pe', 'par', 'tak', 'ya', 'jo', 'jis'}
    
    words = normalize_text_multilingual(text).split()
    meaningful_words = [word for word in words if len(word) > 2 and word not in stop_words]
    return meaningful_words

def calculate_multi_strategy_score(lyric_line, transcript_segment):
    """
    Calculate matching score using multiple strategies for robustness
    """
    norm_lyric = normalize_text_multilingual(lyric_line)
    norm_transcript = normalize_text_multilingual(transcript_segment)
    
    scores = []
    
    scores.append(fuzz.partial_ratio(norm_lyric, norm_transcript))
    scores.append(fuzz.token_sort_ratio(norm_lyric, norm_transcript))
    scores.append(fuzz.token_set_ratio(norm_lyric, norm_transcript))
    
    lyric_words = extract_meaningful_words(lyric_line)
    transcript_words = extract_meaningful_words(transcript_segment)
    
    if lyric_words and transcript_words:
        matches = 0
        for lyric_word in lyric_words:
            best_word_score = max([fuzz.ratio(lyric_word, t_word) for t_word in transcript_words] + [0])
            if best_word_score > 70:  
                matches += 1
        
        word_match_percentage = (matches / len(lyric_words)) * 100
        scores.append(word_match_percentage * 1.2)  
    
    if len(lyric_words) >= 2:
        key_phrase = lyric_words[0] + ' ' + lyric_words[-1]
        key_score = fuzz.partial_ratio(key_phrase, norm_transcript)
        scores.append(key_score)
    
    if len(lyric_words) <= 3:
        for lyric_word in lyric_words:
            if lyric_word in norm_transcript:
                scores.append(90)  # High score for exact substring match
                break
    
    return max(scores) if scores else 0

def process_and_align(audio_path, lyrics_text):
    """
    Robust transcription and alignment for Hindi, English, Hinglish, and Urdu
    """
    SIMILARITY_THRESHOLD = 55
    
    print("Transcribing audio for timestamps...")
    transcriber = aai.Transcriber()
    
    config = aai.TranscriptionConfig(
        language_detection=True,
        punctuate=True,
        format_text=True,
        speaker_labels=False, 
        dual_channel=False
    )
    
    transcript = transcriber.transcribe(audio_path, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    words = transcript.words
    if not words:
        raise Exception("No words found in transcription")

    print("Aligning lyrics with timestamps using multilingual fuzzy matching...")
    
    sample_words = [w.text for w in words[:15]]
    print(f"Transcribed words sample: {' '.join(sample_words)}")

    poem_lines = [line.strip() for line in lyrics_text.strip().split('\n') if line.strip()]
    line_timings = []
    
    total_duration = (words[-1].end / 1000.0) if words else 0
    current_word_index = 0
    
    for i, line_text in enumerate(poem_lines):
        if not line_text.strip():
            line_timings.append({'start': 0, 'end': 0})
            continue

        best_score = 0
        best_start_index = -1
        best_end_index = -1
        
        meaningful_words = extract_meaningful_words(line_text)
        search_window_size = max(len(meaningful_words) * 2, 8)  # At least 8 words
        search_window_size = min(search_window_size, 25)  # Max 25 words
        
        search_end = min(len(words), current_word_index + (len(words) // len(poem_lines)) * 3)
        
        for start_idx in range(current_word_index, search_end - search_window_size):
            end_idx = min(start_idx + search_window_size, len(words))
            
            segment_words = [words[j].text for j in range(start_idx, end_idx)]
            transcript_segment = ' '.join(segment_words)
            
            score = calculate_multi_strategy_score(line_text, transcript_segment)
            
            if score > best_score:
                best_score = score
                best_start_index = start_idx
                word_span = max(len(meaningful_words), 2)
                best_end_index = min(start_idx + word_span - 1, len(words) - 1)
        
        # Apply results or use fallback
        if best_score >= SIMILARITY_THRESHOLD and best_start_index != -1:
            start_time = words[best_start_index].start / 1000.0
            end_time = words[best_end_index].end / 1000.0
            line_timings.append({'start': start_time, 'end': end_time})
            current_word_index = best_end_index + 1
            print(f"  SUCCESS (Score: {best_score:.0f}%) - Line {i+1}")
        else:
            # Time-based fallback for unmatched lines
            line_duration = total_duration / len(poem_lines)
            start_time = i * line_duration
            end_time = (i + 1) * line_duration
            line_timings.append({'start': start_time, 'end': end_time})
            print(f"  FALLBACK (Score: {best_score:.0f}%) - Line {i+1}: Using time-based alignment")

    print("Post-processing timings...")
    for i in range(len(line_timings)):
        if line_timings[i]['end'] - line_timings[i]['start'] < 1.5:
            line_timings[i]['end'] = line_timings[i]['start'] + 1.5
        
        if i > 0 and line_timings[i]['start'] <= line_timings[i-1]['end']:
            line_timings[i]['start'] = line_timings[i-1]['end'] + 0.2
            line_timings[i]['end'] = line_timings[i]['start'] + 1.5

    if line_timings and line_timings[-1]['end'] > total_duration:
        excess = line_timings[-1]['end'] - total_duration
        for timing in line_timings:
            timing['start'] = max(0, timing['start'] - excess * 0.1)
            timing['end'] = max(timing['start'] + 1.0, timing['end'] - excess * 0.1)

    successful_matches = len([t for t in line_timings if t['start'] > 0])
    print(f"Alignment complete: {successful_matches}/{len(poem_lines)} lines successfully matched")
    
    return poem_lines, line_timings

@app.route('/')
def homepage():
    return render_template('creator.html')

@app.route('/create', methods=['POST'])
def create_moment():
    try:
        lyrics_text = request.form.get('lyrics_text')
        title = request.form.get('title')
        youtube_url = request.form.get('youtube_url')
        audio_file = request.files.get('audio_file')

        if youtube_url:
            # --- YOUTUBE WORKFLOW ---
            print(f"Processing YouTube URL: {youtube_url}")
            temp_filename = str(uuid.uuid4())
            audio_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{temp_filename}.mp3')
            
            ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}], 'outtmpl': os.path.join(app.config['UPLOAD_FOLDER'], temp_filename), 'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                song_title = title or info.get('title', 'Untitled Song')
                artist = info.get('artist') or info.get('channel', 'Unknown Artist')

            audio_filename_to_save = f'{temp_filename}.mp3'
            
            # --- THE "TRY MAGIC, THEN FALLBACK" LOGIC ---
            lyrics_to_use = lyrics_text
            if not lyrics_to_use: # Only try Genius if the user didn't provide lyrics
                try:
                    print(f"Attempting to fetch lyrics for '{song_title}'...")
                    song = genius.search_song(song_title, artist)
                    if song and song.lyrics:
                        print("Successfully fetched lyrics from Genius.")
                        lyrics_to_use = re.sub(r'\[.*?\]', '', song.lyrics)
                    else:
                        raise Exception("Lyrics not found on Genius.")
                except Exception as e:
                    raise Exception(f"Automatic lyric lookup failed: {e}. Please provide lyrics manually.")
            
        elif audio_file:
            # --- UPLOAD WORKFLOW ---
            if not title or not lyrics_text: raise Exception("Title and Lyrics are required for file uploads.")
            song_title = title
            audio_filename_to_save = str(uuid.uuid4()) + os.path.splitext(audio_file.filename)[1]
            audio_output_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename_to_save)
            audio_file.save(audio_output_path)
            lyrics_to_use = lyrics_text
        
        else:
            raise Exception("Please provide either a YouTube URL or an audio file.")

        # --- COMMON PROCESSING ---
        poem_lines, line_timings = process_and_align(audio_output_path, lyrics_to_use)
        
        moment_id = str(uuid.uuid4())
        moment_data = {"id": moment_id, "title": song_title, "audio_filename": audio_filename_to_save, "lyrics": poem_lines, "timings": line_timings}
        
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