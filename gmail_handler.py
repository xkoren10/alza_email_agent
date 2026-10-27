import os
import email
import imaplib
from email.header import decode_header
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from attachment_handler import process_and_save_attachment
from extra.color_print import printRed, printGreen, printYellow

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

load_dotenv()

IMAP_SERVER = "imap.gmail.com"
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")


def fetch_unread_emails():
    """Connects to Gmail, fetches unread emails, passes attachments to security handler, and marks them as read."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            return []

        email_list = []
        for num in messages[0].split():
            res, msg_data = mail.fetch(num, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    
                    from_whom = msg.get("From")
                    msg_id = msg.get("Message-ID")

                    body = ""
                    attachment_paths = []

                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            is_attachment = "attachment" in content_disposition.lower()
                            is_inline_image = content_type.startswith("image/") and "inline" in content_disposition.lower()
                            
                            if is_attachment or is_inline_image:
                                raw_filename = part.get_filename()
                                if not raw_filename:
                                    ext = content_type.split('/')[-1] if '/' in content_type else 'bin'
                                    raw_filename = f"embedded_file.{ext}"
                                
                                decoded_parts = decode_header(raw_filename)
                                filename = "".join(
                                    text.decode(encoding or "utf-8") if isinstance(text, bytes) else text
                                    for text, encoding in decoded_parts
                                )
                                
                                file_payload = part.get_payload(decode=True)
                                
                                # Delegate security and saving to attachment_handler module
                                saved_path = process_and_save_attachment(file_payload, filename, content_type)
                                if saved_path:
                                    attachment_paths.append(saved_path)
                            
                            elif content_type == "text/plain" and not body:
                                body = part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    email_list.append({
                        "id": num,
                        "from": from_whom,
                        "subject": subject,
                        "message_id": msg_id,
                        "body": body,
                        "attachment_paths": attachment_paths
                    })

            mail.store(num, '+FLAGS', '\\Seen')

        mail.logout()
        return email_list

    except Exception as e:
        printRed(f"Error fetching emails: {e}")
        return []

def send_email_reply(to_email, original_subject, original_message_id, reply_text):
    """Sends a threaded reply back to the sender via Gmail SMTP."""
    try:
        subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        msg.attach(MIMEText(reply_text, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
            
        printGreen(f"Successfully replied to {to_email}")
        return True

    except Exception as e:
        printRed(f"Error sending email reply: {e}")
        return False