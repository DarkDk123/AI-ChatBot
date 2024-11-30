"""
langchain_chat.py
___

Simple Chat Application with `ConversationSummaryBufferMemory` (deprecated (should use `LangGraph` instead))\
Yet, this isn't scalable but shows practical usage of memory and chat contexts.
"""

# Imports
from langchain.memory import ConversationSummaryBufferMemory
from langchain_huggingface import HuggingFaceEndpoint
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize the language model
HF_TOKEN = os.getenv("HF_TOKEN")

llm = HuggingFaceEndpoint(repo_id="Qwen/Qwen2.5-Coder-32B-Instruct", huggingfacehub_api_token=HF_TOKEN)


# Memory for the user
memory = ConversationSummaryBufferMemory(
        llm = llm,
        max_token_limit = 4000, # for conversation
        memory_key='messages',
        return_messages=True
)


# Prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            content="You are a helpful assistant. Answer all questions to the best of your ability."
        ),
        MessagesPlaceholder(variable_name="messages"), # other messages in the prompt!
    ]
)


# Main function to handle user messages.
def handle_user_message(user_input):
    # Load memory variables to get the conversation history
    history = memory.load_memory_variables(inputs={})

    # Generate a response based on the conversation history
    response = llm.invoke(
        history["messages"] + [{"role": "user", "content": user_input}]
    )

    # Save the user query & AI response in memory
    memory.save_context(
        inputs={"USER": user_input}, outputs={"AI": response}
    )

    return response



# Main template code!
if __name__ == "__main__":
    print("Chatbot is ready! Type 'exit' to stop.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        response = handle_user_message(user_input)
        print(f"AI: {response}")

        with open('chat_logs.txt', 'w') as f:
            f.write(str(memory.chat_memory.messages))
