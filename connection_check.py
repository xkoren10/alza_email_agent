import os
import imaplib
from google import genai
from dotenv import load_dotenv
from extra.color_print import printRed, printGreen, printYellow

load_dotenv()

IMAP_SERVER = "imap.gmail.com"
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

def verify_gmail_connection():
    """Tests the connection to Gmail IMAP using credentials from .env."""
    try:
        print("Verifying Gmail connection... ", end='')
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        mail.logout()
        printGreen("Gmail IMAP connection successful!")
        return True
    except Exception as e:
        printRed(f"Gmail connection failed: {e}")
        return False

def verify_gemini_connection():
    """Tests the connection to the Gemini API by listing available models using the new client."""
    try:
        print("Verifying Gemini API connection... ", end='')
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        models_pager = client.models.list()
        model_names = [m.name for m in models_pager]
        
        if model_names:
            printGreen("Gemini API connection successful!")
            return True
        else:
            printYellow("Connected to Gemini, but no models were found.")
            return False
    except Exception as e:
        printRed(f"Gemini API connection failed: {e}")
        return False