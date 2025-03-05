"""Schema for the Agent Server."""

import time
from datetime import datetime
from typing import Annotated, List
from uuid import uuid4

import bleach
from pydantic import BaseModel, Field, StringConstraints, field_validator

# List of fallback responses sent out for any Exceptions from /generate endpoint
FALLBACK_RESPONSES = [
    "Please try re-phrasing, I am likely having some trouble with that question.",
    "I will get better with time, please try with a different question.",
    "I wasn't able to process your input. Let's try something else.",
    "Something went wrong. Could you try again in a few seconds with a different question?",
    "Oops, that proved a tad difficult for me, can you retry with another question?",
]


class Message(BaseModel):
    """Definition of the Chat Message type."""

    role: str = Field(
        description="Role for a message AI, User and System",
        default="user",
        max_length=256,
        pattern=r"[\s\S]*",
    )
    content: str = Field(
        description="The input query/prompt to the pipeline.",
        default="Hello what can you do?",
        max_length=131072,
        pattern=r"[\s\S]*",
    )

    timestamp: str = Field(
        # default="2025-02-28 19:59:04.992537", #type:ignore
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        description="Message Timestamp",
    )

    @field_validator("role")
    def validate_role(cls, value):
        """Field validator function to validate values of the field role"""
        value = bleach.clean(value, strip=True)
        valid_roles = {"user", "assistant", "system"}
        if value.lower() not in valid_roles:
            raise ValueError("Role must be one of 'user', 'assistant', or 'system'")
        return value.lower()

    @field_validator("content")
    def sanitize_content(cls, v):
        """Field validator function to sanitize user populated fields from HTML"""
        v = bleach.clean(v, strip=True)
        if not v:  # Check for empty string
            raise ValueError("Message content cannot be empty.")
        return v

    @field_validator("timestamp")
    def sanitize_timestamp(cls, v):
        """Field validator function to sanitize given timestamp"""
        if not isinstance(v, (str, float)):
            raise TypeError("Timestamp must be a string in ISO format or a float.")
        elif (
            isinstance(v, float) or v.replace(".", "", 1).isdigit() or v == "string"
        ):  # Convert float timestamp to string
            return datetime.fromtimestamp(
                float(v) if v != "string" else time.time()
            ).strftime("%Y-%m-%d %H:%M:%S.%f")
        elif isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                raise ValueError("Timestamp must be a string in ISO format.")
        return v


# Request Schemas
class Prompt(BaseModel):
    """Definition of the Prompt API data type."""

    messages: List[Message] = Field(
        ...,
        description="A list of messages comprising the conversation so far. The roles of the messages must be alternating between user and assistant. The last input message should have role user. A message with the the system role is optional, and must be the very first message if it is present.",
        max_length=10_000,
    )

    user_id: str = Field(description="A unique identifier representing your end-user.")
    thread_id: str = Field(
        ...,
        description="A unique identifier representing the thread associated with the response.",
    )


class ChainResponseChoices(BaseModel):
    """Definition of Chain response choices"""

    index: int = Field(default=0, ge=0, le=256)
    message: Message = Field(default=Message())
    finish_reason: str = Field(default="", max_length=4096, pattern=r"[\s\S]*")


class ChainResponse(BaseModel):
    """Definition of Chain APIs resopnse data type"""

    id: str = Field(default="", max_length=100000, pattern=r"[\s\S]*")
    choices: List[ChainResponseChoices] = Field(default=[], max_length=256)
    thread_id: str = Field(
        description="A unique identifier representing the thread associated with the response.",
    )


class DocumentSearch(BaseModel):
    """Definition of the DocumentSearch API data type."""

    query: str = Field(
        description="The content or keywords to search for within documents.",
        max_length=131072,
        pattern=r"[\s\S]*",
        default="",
    )
    top_k: int = Field(
        description="The maximum number of documents to return in the response.",
        default=4,
        ge=0,
        le=25,
    )


class DocumentChunk(BaseModel):
    """Represents a chunk of a document."""

    content: str = Field(
        description="The content of the document chunk.",
        max_length=131072,
        pattern=r"[\s\S]*",
        default="",
    )
    filename: str = Field(
        description="The name of the file the chunk belongs to.",
        max_length=4096,
        pattern=r"[\s\S]*",
        default="",
    )
    score: float = Field(..., description="The relevance score of the chunk.")


class DocumentSearchResponse(BaseModel):
    """Represents a response from a document search."""

    chunks: List[DocumentChunk] = Field(
        ..., description="List of document chunks.", max_length=256
    )


class DocumentsResponse(BaseModel):
    """Represents the response containing a list of documents."""

    DocumentString: Annotated[
        str, StringConstraints(max_length=131072, pattern=r"[\s\S]*")
    ] = Field(description="List of filenames.", max_length=1000000, default="")


class HealthResponse(BaseModel):
    message: str = Field(max_length=4096, pattern=r"[\s\S]*", default="")


class CreateThreadResponse(BaseModel):
    thread_id: str = Field(max_length=4096)


class EndThreadResponse(BaseModel):
    message: str = Field(max_length=4096, pattern=r"[\s\S]*", default="")


class DeleteThreadResponse(BaseModel):
    message: str = Field(max_length=4096, pattern=r"[\s\S]*", default="")


class FeedbackRequest(BaseModel):
    """Definition of the Feedback Request data type."""

    feedback: float = Field(
        ...,
        description="A unique identifier representing your end-user.",
        ge=-1.0,
        le=1.0,
    )
    thread_id: str = Field(
        ...,
        description="A unique identifier representing the thread associated with the response.",
    )


class FeedbackResponse(BaseModel):
    """Definition of the Feedback Request data type."""

    message: str = Field(max_length=4096, pattern=r"[\s\S]*", default="")


class GetThreadResponse(BaseModel):
    thread_id: str
    user_id: str
    conversation_history: List[Message]
    last_conversation_time: str = "None"
    start_conversation_time: str = "None"


def fallback_response_generator(sentence: str, thread_id: str = ""):
    """Mock response generator to simulate streaming predefined fallback responses."""

    # Simulate breaking the sentence into chunks (e.g., by word)
    sentence_chunks = sentence.split()  # Split the sentence by words
    resp_id = str(uuid4())  # unique response id for every query
    # Send each chunk (word) in the response
    for chunk in sentence_chunks:
        chain_response = ChainResponse(thread_id=thread_id)
        response_choice = ChainResponseChoices(
            index=0, message=Message(role="assistant", content=f"{chunk} ")
        )
        chain_response.id = resp_id
        chain_response.choices.append(response_choice)
        yield "data: " + str(chain_response.model_dump()) + "\n\n"

    # End with [DONE] response
    chain_response = ChainResponse(thread_id=thread_id)
    response_choice = ChainResponseChoices(
        message=Message(role="assistant", content=" "), finish_reason="[DONE]"
    )
    chain_response.id = resp_id
    chain_response.choices.append(response_choice)
    yield "data: " + str(chain_response.model_dump()) + "\n\n"
