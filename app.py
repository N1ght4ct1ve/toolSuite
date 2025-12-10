import os
import threading
import queue
import sqlite3
import time
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import numpy as np
import soundfile as sf

# Import existing logic
from extractor import Extractor

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'audio'
app.config['DATA_FOLDER'] = 'data'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)

# Database setup
DB_PATH = os.path.join(app.config['DATA_FOLDER'], 'app.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # stored_filename is the file on disk in uploads/
    # audio_filename is the file on disk in audio/
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (id TEXT PRIMARY KEY, filename TEXT, stored_filename TEXT, 
                  audio_filename TEXT, status TEXT, created_at REAL,
                  progress INTEGER DEFAULT 0, total_chunks INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# Job Queue
job_queue = queue.Queue()

def process_audio_job():
    # Initialize Reader once
    print("Worker: Initializing Reader...")
    try:
        from reader_kokoro import Reader
        reader = Reader()
        print("Worker: Reader initialized.")
    except Exception as e:
        print(f"Worker: Failed to initialize reader: {e}")
        return

    while True:
        job_id = job_queue.get()
        if job_id is None:
            break
        
        print(f"Worker: Processing job {job_id}")
        
        # Get job details
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT stored_filename FROM jobs WHERE id=?", (job_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            job_queue.task_done()
            continue
            
        stored_filename = row[0]
        original_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        
        # Update status to processing
        c.execute("UPDATE jobs SET status='processing' WHERE id=?", (job_id,))
        conn.commit()
        
        try:
            # Extraction
            extractor = Extractor(original_path)
            title, abstract, sections = extractor.extract()
            
            if not title and not sections:
                # If it's a text file, extractor might return empty title but have sections
                # Extractor logic handles this now.
                pass

            # Audio Generation Logic
            full_audio_buffer = []
            
            # Helper function to split long text into paragraphs/sentences
            def split_into_chunks(text, max_chars=500):
                """Split text into smaller chunks for better progress tracking"""
                if not text or not text.strip():
                    return []
                
                # Split by paragraphs first (double newlines)
                paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                
                chunks = []
                for para in paragraphs:
                    # If paragraph is still too long, split by sentences
                    if len(para) > max_chars:
                        # Split by sentence-ending punctuation
                        import re
                        sentences = re.split(r'(?<=[.!?])\s+', para)
                        current_chunk = ""
                        for sentence in sentences:
                            if len(current_chunk) + len(sentence) < max_chars:
                                current_chunk += " " + sentence if current_chunk else sentence
                            else:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                current_chunk = sentence
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                    else:
                        chunks.append(para)
                
                return chunks if chunks else [text]
            
            # Calculate total chunks for progress tracking
            chunks_to_process = []
            if title:
                chunks_to_process.append(f"Title: {title}.")
            if abstract:
                chunks_to_process.append("Abstract.")
                chunks_to_process.extend(split_into_chunks(abstract))
            for section in sections:
                if section.get('section-title'):
                    chunks_to_process.append(f"Section: {section['section-title']}.")
                if section.get('section-text'):
                    chunks_to_process.extend(split_into_chunks(section['section-text']))
            
            total_chunks = len(chunks_to_process)
            processed_chunks = [0]  # Use list to allow modification in nested function
            
            # Update total chunks in DB
            c.execute("UPDATE jobs SET total_chunks=? WHERE id=?", (total_chunks, job_id))
            conn.commit()
            
            def process_text_chunk(text_chunk):
                if not text_chunk or not text_chunk.strip():
                    return
                # Use the reader instance
                generator = reader.pipeline(text_chunk, voice='af_heart')
                for _, _, audio in generator:
                    full_audio_buffer.append(audio)
                
                # Update progress
                processed_chunks[0] += 1
                c.execute("UPDATE jobs SET progress=? WHERE id=?", (processed_chunks[0], job_id))
                conn.commit()

            # Process all chunks in order
            silence = np.zeros(int(24000 * 0.3))  # 0.3s silence between chunks
            
            for i, chunk in enumerate(chunks_to_process):
                process_text_chunk(chunk)
                # Add silence after titles/headers (longer pause)
                if chunk.startswith("Title:") or chunk.startswith("Section:") or chunk == "Abstract.":
                    full_audio_buffer.append(np.zeros(int(24000 * 0.5)))
                else:
                    full_audio_buffer.append(silence)

            if full_audio_buffer:
                combined_audio = np.concatenate(full_audio_buffer)
                output_filename = f"{job_id}.wav"
                output_path = os.path.join(app.config['AUDIO_FOLDER'], output_filename)
                sf.write(output_path, combined_audio, 24000)
                
                c.execute("UPDATE jobs SET status='completed', audio_filename=? WHERE id=?", 
                          (output_filename, job_id))
            else:
                print(f"Worker: No audio generated for job {job_id}")
                c.execute("UPDATE jobs SET status='failed' WHERE id=?", (job_id,))

        except Exception as e:
            print(f"Worker: Job {job_id} failed: {e}")
            import traceback
            traceback.print_exc()
            c.execute("UPDATE jobs SET status='failed' WHERE id=?", (job_id,))
        
        conn.commit()
        conn.close()
        job_queue.task_done()

# Start worker thread
worker_thread = threading.Thread(target=process_audio_job, daemon=True)
worker_thread.start()

@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY created_at ASC")
    jobs = c.fetchall()
    conn.close()
    return render_template('index.html', jobs=jobs)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file:
        filename = secure_filename(file.filename)
        job_id = str(uuid.uuid4())
        stored_filename = f"{job_id}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        file.save(file_path)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO jobs (id, filename, stored_filename, status, created_at) VALUES (?, ?, ?, ?, ?)",
                  (job_id, filename, stored_filename, 'queued', time.time()))
        conn.commit()
        conn.close()
        
        job_queue.put(job_id)
        
        return redirect(url_for('index'))

@app.route('/status/<job_id>')
def job_status(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, audio_filename, progress, total_chunks FROM jobs WHERE id=?", (job_id,))
    row = c.fetchone()
    conn.close()
    if row:
        progress = row[2] or 0
        total = row[3] or 0
        percent = int((progress / total * 100) if total > 0 else 0)
        return jsonify({
            'status': row[0], 
            'audio_filename': row[1],
            'progress': progress,
            'total_chunks': total,
            'percent': percent
        })
    return jsonify({'status': 'unknown'}), 404

@app.route('/clear_history', methods=['POST'])
def clear_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get all files to delete them from disk
    c.execute("SELECT stored_filename, audio_filename FROM jobs")
    files = c.fetchall()
    
    for stored_filename, audio_filename in files:
        if stored_filename:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], stored_filename))
            except OSError:
                pass
        if audio_filename:
            try:
                os.remove(os.path.join(app.config['AUDIO_FOLDER'], audio_filename))
            except OSError:
                pass

    # Clear the database
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/uploads/<path:filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/audio/<path:filename>')
def download_audio(filename):
    return send_from_directory(app.config['AUDIO_FOLDER'], filename)

if __name__ == '__main__':
    # Note: debug=True reloads the server, which might restart the worker thread.
    # For production, use a proper WSGI server and separate worker process.
    # For this demo, it's fine, but existing jobs in queue might be lost on reload.
    # The DB state persists though.
    app.run(host='0.0.0.0', debug=True, port=5000, use_reloader=False) 
