from langchain_chat import app, config, MODEL_REPO_ID
import streamlit as st

st.title("OSHO LLM ChatBot")
with st.expander(label="Model Info...", icon="📕"):
    st.write(f"Model used is `{MODEL_REPO_ID}` available on HuggingFace")

# Updates session state variables
if "messages" not in st.session_state:
    # Will store messages
    st.session_state.messages = []

# Updating avatars
if "avatars" not in st.session_state:
    st.session_state.avatars = {
        "assistant": "./avatars/Osho_Rajneesh.jpg",  # Still, He is the true Master 🙏🏻
        "user": "./avatars/user.jpeg",
    }

# Displaying all messages
for message in st.session_state.messages:
    with st.chat_message(
        message["role"], avatar=st.session_state.avatars[message["role"]]
    ):
        st.markdown(message["content"])


# User input and response
if prompt := st.chat_input("How to forgot her?!"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar=st.session_state.avatars["user"]):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=st.session_state.avatars["assistant"]):
        output = app.invoke({"messages": [prompt]}, config)
        st.markdown(response := output["messages"][-1].content)

    st.session_state.messages.append({"role": "assistant", "content": response})
