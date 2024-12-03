"""
utils.py
---

It contains some utility functions.
"""

from langchain_chat import model


def suggest_title(question: str):
    """Suggests title for a conversation."""

    return model.invoke(
        f"Suggest a max 3-4 word title for the given conversation start '{question}', \
                Asked to a spiritual Chat Bot on Rajneesh OSHO."
    ).content
