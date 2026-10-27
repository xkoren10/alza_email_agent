import os
import unicodedata
import re

ATTACHMENT_DIR = "attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

# Whitelist of supported extensions and their required magic bytes (file signatures)
SUPPORTED_FILE_TYPES = {
    '.pdf': {'mime': 'application/pdf', 'magic': [b'%PDF']},
    '.png': {'mime': 'image/png', 'magic': [b'\x89PNG\r\n\x1a\n']},
    '.jpg': {'mime': 'image/jpeg', 'magic': [b'\xff\xd8\xff']},
    '.jpeg': {'mime': 'image/jpeg', 'magic': [b'\xff\xd8\xff']},
    '.webp': {'mime': 'image/webp', 'magic': [b'RIFF']}, 
    '.gif': {'mime': 'image/gif', 'magic': [b'GIF87a', b'GIF89a']},
    '.mp3': {'mime': 'audio/mpeg', 'magic': [b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2']},
    '.wav': {'mime': 'audio/wav', 'magic': [b'RIFF']},
    '.m4a': {'mime': 'audio/mp4', 'magic': [b'ftypM4A', b'ftypisom', b'ftypmp42']}
}

MAX_FILE_SIZE_MB = 15  # Max allowed file size to prevent DoS

def sanitize_filename(filename):
    """Strips path traversal characters and normalizes unicode to safe ASCII."""
    filename = os.path.basename(filename)
    nfkd_form = unicodedata.normalize('NFKD', filename)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('ASCII')
    safe_name = re.sub(r'[^\w\s.-]', '', only_ascii)
    return safe_name.strip().replace(' ', '_')

def verify_magic_bytes(file_bytes, file_ext):
    """Validates that the file's internal signature matches its extension."""
    if file_ext not in SUPPORTED_FILE_TYPES:
        return False
    
    signatures = SUPPORTED_FILE_TYPES[file_ext]['magic']
    
    if file_ext == '.webp':
        return b'RIFF' in file_bytes[:12] and b'WEBP' in file_bytes[:12]
    if file_ext == '.wav':
        return b'RIFF' in file_bytes[:12] and b'WAVE' in file_bytes[:12]

    for sig in signatures:
        if file_bytes.startswith(sig):
            return True
            
    return False

def process_and_save_attachment(file_payload, raw_filename, content_type):
    """Performs all security checks and saves the file safely. Returns file path or None."""
    try:
        file_ext = os.path.splitext(raw_filename)[1].lower()
        
        # 1. Whitelist extension check
        if file_ext not in SUPPORTED_FILE_TYPES:
            print(f"⚠️ Security Alert: Blocked unsupported file type: {raw_filename}")
            return None

        if not file_payload:
            return None

        # 2. File size limit check (DoS defense)
        file_size_mb = len(file_payload) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            print(f"⚠️ Security Alert: Blocked oversized file ({file_size_mb:.2f} MB): {raw_filename}")
            return None

        # 3. Magic byte verification (prevent extension spoofing)
        if not verify_magic_bytes(file_payload, file_ext):
            print(f"🚨 SECURITY ALERT: File signature mismatch! Possible spoofed extension: {raw_filename}")
            return None

        # 4. Sanitize filename & prevent path traversal
        safe_name = sanitize_filename(raw_filename)
        save_path = os.path.join(ATTACHMENT_DIR, safe_name)
        
        # Handle duplicate filenames safely
        counter = 1
        base, ext = os.path.splitext(save_path)
        while os.path.exists(save_path):
            save_path = f"{base}_{counter}{ext}"
            counter += 1
            
        with open(save_path, "wb") as f:
            f.write(file_payload)
            
        print(f"🔒 Securely saved and verified file: {os.path.basename(save_path)}")
        return save_path

    except Exception as e:
        print(f"❌ Error processing attachment {raw_filename}: {e}")
        return None