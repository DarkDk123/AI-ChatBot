"""
main_streamlit
---

This script provides a simple, elegant Streamlit app for interacting with a LangChain LLM Chatbot.
It supports **multiple conversation threads** with independent message contexts.

Note:
- This UI runs independently of any container or orchestration system.
- It directly uses the LangGraph codebase, without additional context or API/DB layers.
"""

import asyncio

import nest_asyncio
import streamlit as st

from src.chatbot.main.main_graph import AIMessageChunk, compile_graph, config
from src.chatbot.utils import (
    LLM_MODEL_NAME,
    # get_checkpointer,
    # remove_state_from_checkpointer,
    suggest_title,
    to_sync_generator,
)

AVATARS_PATH = "src/chatbot/main/avatars"


if "initialized" not in st.session_state:
    nest_asyncio.apply()
    # asyncio.run(get_checkpointer(open=True))
    st.session_state.app = asyncio.run(compile_graph())
    st.session_state.initialized = True

st.title("OSHO LLM ChatBot")
with st.expander(label="Model Info...", icon="📕"):
    st.write(f"Model used is `{LLM_MODEL_NAME}` available")

# Updates session state variables
if "conversations" not in st.session_state:
    # Will store conversations
    st.session_state.conversations = {}
    st.session_state.convo_id = 0

# Updating avatars
if "avatars" not in st.session_state:
    st.session_state.avatars = {
        "assistant": f"{AVATARS_PATH}/Osho_Rajneesh.jpg",  # Still, He is the true Master 🙏🏻
        "user": f"{AVATARS_PATH}/user.jpeg",
    }

# Start new conversation
if st.sidebar.button("Start New Conversation") or st.session_state.convo_id == 0:
    st.session_state.convo_id += 1
    convo_id = st.session_state.convo_id
    st.session_state.conversations[convo_id] = {
        "title": "Untitled Conversation",
        "messages": [],
    }

# Displaying all conversations
ids_and_titles = {
    k: st.session_state.conversations[k]["title"]
    for k in st.session_state.conversations.keys()
}

convo_ids = ids_and_titles.keys()

if convo_ids:
    convo_id = st.sidebar.radio(
        "Select Conversation",
        list(convo_ids),
        format_func=lambda x: ids_and_titles[x],
        index=st.session_state.convo_id - 1,
    )
else:
    convo_id = None

# Displaying conversation title

if convo_id:
    conv_title = st.subheader(
        f"**💬 {st.session_state.conversations[convo_id]['title']}**"
    )

# Displaying all messages in conversation
if convo_id:
    for message in st.session_state.conversations[convo_id]["messages"]:
        with st.chat_message(
            message["role"], avatar=st.session_state.avatars[message["role"]]
        ):
            st.markdown(message["content"])

# User input and response
if convo_id and (prompt := st.chat_input("What's on your mind?")):
    st.session_state.conversations[convo_id]["messages"].append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    # Update conversation title
    if st.session_state.conversations[convo_id]["title"] == "Untitled Conversation":
        suggestion = suggest_title(prompt)
        st.session_state.conversations[convo_id]["title"] = suggestion
        conv_title.title(suggestion)  # type:ignore

    # Continue conversation
    with st.chat_message("user", avatar=st.session_state.avatars["user"]):
        st.markdown(prompt)

    # if not st.session_state.conversations[convo_id]["title"]:
    #     conv_title.text = st.session_state.conversations[convo_id]["title"] = prompt

    with st.chat_message("assistant", avatar=st.session_state.avatars["assistant"]):
        config.get("configurable", {})["thread_id"] = f"darkdk123_conv_{convo_id}"

        async def stream():
            async for message, metadata in st.session_state.app.astream(
                {"messages": [prompt]}, config, stream_mode="messages"
            ):
                if (
                    isinstance(message, AIMessageChunk)
                    and isinstance(metadata, dict)
                    and metadata["langgraph_node"] == "model"
                ):
                    if message.response_metadata.get("finish_reason", None) == "stop":
                        # Streaming done!
                        yield message.content
                        break
                    yield message.content

        # Run the async stream and display it using st.write_stream
        response = st.write_stream(to_sync_generator(stream()))

    # Append the assistant's response to the conversation
    st.session_state.conversations[convo_id]["messages"].append(
        {
            "role": "assistant",
            "content": response,
        }
    )

    # # Do something on exit
    # @st.cache_data()
    # def on_exit():
    #     """Run once on exit."""
    #     asyncio.run(
    #         remove_state_from_checkpointer(config.get("configurable", {})["thread_id"])
    #     )

    # # Use `atexit` to run the function on exit
    # import atexit

    # atexit.register(on_exit)
