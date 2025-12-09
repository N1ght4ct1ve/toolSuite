import numpy as np
import soundfile as sf
import os
import sys

# Import your classes
# Assuming the extractor code is in extractor.py and reader is in reader_kokoro.py
try:
    from extractor import Extractor
    from reader_kokoro import Reader
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Error: Please ensure 'extractor.py' and 'reader_kokoro.py' are in the same directory.")
    sys.exit(1)

def main():
    xml_file = "electronics-10-02440.xml"
    output_wav = "full_paper_read.wav"
    
    # 1. Extract content from the XML
    print(f"--- Parsing {xml_file} ---")
    extractor = Extractor(xml_file)
    title, abstract, sections = extractor.extract()

    if not title and not sections:
        print("No content found or file does not exist.")
        return

    # 2. Initialize the Kokoro Reader
    print("--- Initializing Kokoro Pipeline ---")
    reader = Reader()
    
    # List to hold raw audio data arrays
    full_audio_buffer = []
    
    # Helper to process text and add to buffer
    def process_text_chunk(text_chunk):
        if not text_chunk.strip():
            return
            
        # We use reader.pipeline directly to capture audio in memory 
        # instead of writing small files immediately.
        generator = reader.pipeline(text_chunk, voice='af_heart')
        
        for _, _, audio in generator:
            full_audio_buffer.append(audio)

    # 3. Read the Title
    print(f"Processing Title: {title}")
    process_text_chunk(f"Title: {title}.")
    
    # Insert a small silence between title and body (0.5 seconds of silence at 24khz)
    silence = np.zeros(int(24000 * 0.5))
    full_audio_buffer.append(silence)

    # 4. Read the Abstract
    if abstract:
        print("Processing Abstract")
        process_text_chunk("Abstract.")
        full_audio_buffer.append(silence)
        process_text_chunk(abstract)
        full_audio_buffer.append(silence)

    # 5. Read the Sections
    total_sections = len(sections)
    for index, section in enumerate(sections):
        sec_title = section['section-title']
        sec_text = section['section-text']
        
        print(f"Processing Section {index + 1}/{total_sections}: {sec_title}")
        
        # Announce the section title
        if sec_title:
            process_text_chunk(f"Section: {sec_title}.")
            full_audio_buffer.append(silence) # Pause after section header
            
        # Read the section body
        if sec_text:
            process_text_chunk(sec_text)
            
        # Pause between sections
        full_audio_buffer.append(silence)

    # 6. Concatenate and Write to File
    if full_audio_buffer:
        print(f"--- Merging audio and writing to {output_wav} ---")
        # Concatenate all numpy arrays into one long array
        combined_audio = np.concatenate(full_audio_buffer)
        
        # Write to WAV (Kokoro usually outputs at 24khz)
        sf.write(output_wav, combined_audio, 24000)
        print("Done!")
    else:
        print("No audio was generated.")

if __name__ == "__main__":
    main()