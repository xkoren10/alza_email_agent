# Alza Automated AI Customer Support Chatbot

An automated email customer support assistant built for Alza. The system polls a dedicated inbox via IMAP, processes incoming customer inquiries and attachments across multiple formats, generates context-aware responses using Gemini 2.5 Flash, and delivers threaded email replies via SMTP within a strict 2-minute SLA.

## Architecture and Project Structure

The codebase is structured into five dedicated Python modules to separate network operations, AI inference, security validation, and application lifecycle:

```text
├── main.py                  # Main polling loop, execution scheduler, and CLI flag handling
├── connection_check.py      # Functions to validate Gmail and Gemini connection
├── validator.py             # Startup connection health checks for IMAP and Gemini API
├── gmail_handler.py         # IMAP unread email fetching, RFC822 parsing, and SMTP threaded replies
├── gemini_handler.py        # Modern google-genai client initialization, MIME mapping, file uploads, and inference
├── attachment_handler.py    # Security whitelisting, magic byte signature checks, path traversal defense, and safe storage
├── requirements.txt         # Project dependencies
├── extra/                   
|    └── color_print.py      # Definitions for colorful stdout print
└── .env                     # Local configuration and credentials
```

## Security Layer (`attachment_handler.py`)

Incoming file attachments and inline body media undergo a 4-layer validation pipeline prior to processing:

1. **Extension Whitelisting:** Restricts processing strictly to allowed formats (`.pdf`, `.mp3`, `.wav`, `.m4a`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`).
2. **File Size Limits:** Rejects any file exceeding 15 MB to prevent denial-of-service risks.
3. **Magic Byte Verification:** Inspects internal header signatures (e.g., `%PDF`, `\x89PNG`, `RIFF`, `ID3`) to verify file integrity and prevent extension spoofing.
4. **Path Traversal Defense & Sanitization:** Normalizes unicode characters to ASCII, strips directory navigation characters (`..`, `/`, `\`), and isolates files within the `attachments/` directory with collision-free naming.

## Core Capabilities

* **Multimodal Processing:** Accepts text inquiries alongside audio recordings, screenshots, documents, and GIFs.
* **Inline Body Media Parsing:** Extracts embedded images and attachments directly from the HTML body of incoming emails (`Content-Disposition: inline`).
* **Multi-Attachment Handling:** Processes multiple files per email simultaneously, passing them to Gemini before removing temporary remote references.
* **CLI Testing Mode:** Supports a `--no-reply` flag to run dry-run evaluations and print generated AI responses to the console without sending outgoing emails.

## Setup and Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory with the following variables:
```env
EMAIL_USER=your-support-email@gmail.com
EMAIL_PASS=your-gmail-app-password
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

### 3. Dependency Management
Dependencies are listed in `requirements.txt`:
```text
google-genai>=2.33.0
protobuf==7.36.2
python-dotenv==1.2.4
```

## Execution

### Production Mode
Polls the inbox every 10 seconds and automatically sends threaded email replies:
```bash
python main.py
```

### Test Mode (Dry Run)
Processes unread messages and prints generated AI responses to the terminal without delivering email replies:
```bash
python main.py --no-reply
```