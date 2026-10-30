"""Application entry point: wires the components together and exposes the Flask `app`.

Cloud Run:  gunicorn main:app   (see Dockerfile)
Local:      python main.py
"""
import logging
import os

from app.agent import SupportAgent
from app.config import Settings
from app.email_handler import EmailHandler
from app.gmail_client import GmailClient
from app.server import create_app

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")


def build_app():
    settings = Settings.from_env()
    agent = SupportAgent(settings)  # owns the Gemini connection and the knowledge base
    gmail = GmailClient(settings)
    handler = EmailHandler(agent, gmail, settings)
    return create_app(settings, handler, gmail, kb_size=agent.knowledge_size)


app = build_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
