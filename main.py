import time
import argparse
from datetime import datetime
from connection_check import verify_gmail_connection, verify_gemini_connection
from gmail_handler import fetch_unread_emails, send_email_reply
from gemini_handler import generate_ai_response

def main():
    # Setup CLI argument parsing
    parser = argparse.ArgumentParser(description="Alza Chatbot Polling Service")
    parser.add_argument(
        "--no-reply", 
        action="store_true", 
        help="Run in test mode: process emails and generate AI responses, but do not send replies back."
    )
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Alza Chatbot Polling Service Starting...")
    
    if args.no_reply:
        print("[TEST MODE ENABLED]: Automatic email replies are turned OFF (--no-reply flag active).")

    # 1. Verify Gmail connection first
    if not verify_gmail_connection():
        print("Exiting due to Gmail connection error. Please check your EMAIL_USER and EMAIL_PASS.")
        return

    # 2. Verify Gemini connection second
    if not verify_gemini_connection():
        print("Exiting due to Gemini API connection error. Please check your GEMINI_API_KEY.")
        return

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] All systems online! Polling inbox every 10 seconds...\n")
    
    while True:
        unread_emails = fetch_unread_emails()
        
        if unread_emails:
            for mail in unread_emails:
                print(f"\n--- New Email Found ---")
                print(f"From: {mail['from']}")
                print(f"Subject: {mail['subject']}")
                
                if mail['attachment_paths']:
                    print(f"📎 Attachments/Inline files detected: {len(mail['attachment_paths'])}")
                    for path in mail['attachment_paths']:
                        print(f"   - {path}")
                        
                print(f"Body: {mail['body'][:100]}[...]")
                print(f"-----------------------")
                
                # Generate AI response passing body and list of attachment paths
                ai_reply = generate_ai_response(mail['body'], mail['attachment_paths'])
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI Response Generated:\n{ai_reply}\n-----------------------")

                # Send the reply back in thread ONLY if --no-reply is not active
                if not args.no_reply:
                    send_email_reply(
                        to_email=mail['from'],
                        original_subject=mail['subject'],
                        original_message_id=mail['message_id'],
                        reply_text=ai_reply
                    )
                else:
                    print("[TEST MODE]: Skipped sending email reply to user.")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new messages. Waiting...")
        
        time.sleep(10)

if __name__ == "__main__":
    main()