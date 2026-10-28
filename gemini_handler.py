import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are an intelligent customer support AI assistant for Alza Aerospace division handling the AeroSpace Pulsar-1 shuttle. 
Your goal is to read incoming customer inquiries (including any attached documents, images, or official knowledge base references), understand their context, and generate a helpful, polite, and human-like response.
Keep your answers clear, concise, and professional, and ground your technical details strictly in the provided reference data when applicable.
"""

def get_mime_type(file_path):
    """Determines the correct MIME type based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        '.pdf': 'application/pdf',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.m4a': 'audio/mp4',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif': 'image/gif'
    }
    return mime_map.get(ext, 'application/octet-stream')

def generate_ai_response(email_body, attachment_paths=None, rag_contexts=None):
    """Sends the email body, optional RAG context snippets, and multiple file attachments to Gemini."""
    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        
        contents = []
        uploaded_files = []

        # Iterate through all attachment/inline paths and upload them
        if attachment_paths:
            for path in attachment_paths:
                if os.path.exists(path):
                    mime_type = get_mime_type(path)
                    print(f"Uploading file to Gemini API ({mime_type}): {path}")
                    
                    uploaded_file = client.files.upload(
                        file=path,
                        config={"mime_type": mime_type}
                    )
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file)

        # Format retrieved RAG contexts if available
        context_block = ""
        if rag_contexts:
            context_block = "--- OFFICIAL KNOWLEDGE BASE REFERENCES ---\n" + "\n\n".join(rag_contexts) + "\n\n"

        prompt_text = f"{context_block}Customer Email Body:\n{email_body}\n\nPlease generate a helpful response to this customer inquiry considering any attached files, images, or knowledge base references above."
        contents.append(prompt_text)

        print(contents)  # Debug: Show what is being sent to Gemini

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config={
                "system_instruction": SYSTEM_PROMPT
            }
        )
        
        # Cleanup all uploaded files from Google servers
        for uf in uploaded_files:
            try:
                client.files.delete(name=uf.name)
            except Exception:
                pass
        
        if not response.text:
            print("Warning: Gemini returned an empty response.")
            return "I have received your message and attachments, but I am unable to generate a response at this moment."
            
        return response.text
        
    except Exception as e:
        return f"[Error generating AI response: {str(e)}]"