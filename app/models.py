"""Plain data objects passed between the components."""
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


@dataclass
class Attachment:
    filename: str
    mime_type: str
    data: bytes


@dataclass
class IncomingEmail:
    message_id: str  # Gmail API id, used for labelling
    thread_id: str
    rfc_message_id: str  # "Message-ID" header, used for In-Reply-To / References
    sender: str  # raw "From" header
    reply_to: str  # address the reply should go to (Reply-To, falling back to From)
    subject: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased header names
    attachments: list[Attachment] = field(default_factory=list)


class Category(str, Enum):
    TECHNICAL_SUPPORT = "technical_support"  # error codes, diagnostics, how-to
    SPARE_PARTS = "spare_parts"  # part availability, SKUs, prices
    PRODUCT_INFO = "product_info"  # specs, warranty, delivery
    GENERAL = "general"  # greetings, thanks, anything answerable without documents
    OTHER = "other"  # complaints, refunds, safety, unclear or off-topic requests: acknowledged, not solved


class Classification(BaseModel):
    """Structured output of the classification step (also used as the Gemini response schema)."""

    category: Category
    needs_knowledge_base: bool = Field(
        description="True if the answer depends on manuals, error codes, specs or spare-part data."
    )
    search_query: str = Field(
        description=(
            "A short query for the knowledge base that combines the email text and anything seen in "
            "attachments (error codes, part names, visible warning lights). Empty if no lookup is needed."
        )
    )
    summary: str = Field(description="One sentence describing what the customer wants.")
    language: str = Field(description="Language of the customer's email, e.g. 'English' or 'Czech'.")


@dataclass
class Evidence:
    source: str
    content: str
    score: float

    def as_prompt_text(self) -> str:
        return f"[{self.source} | relevance {self.score:.2f}]\n{self.content}"


@dataclass
class Reply:
    to: str
    subject: str
    body: str
    thread_id: str
    in_reply_to: str
