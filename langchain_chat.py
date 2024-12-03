"""
langchain_chat.py
___

Simple Chat Application with `LangChain` and `LangGraph's` in-memory `MemorySaver`.
It shows practical usage of memory and chat contexts. Currently for single user!
"""

# ________Imports___________

from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, MessagesState, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize the language model
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_REPO_ID = os.getenv("MODEL_REPO_ID")

llm = HuggingFaceEndpoint(
    repo_id=MODEL_REPO_ID,
    huggingfacehub_api_token=HF_TOKEN,
    max_new_tokens=4000,
)

model = ChatHuggingFace(llm=llm)

print("Initialized LOADING MODEL!!")


# Define a new graph
# With built-in MessagesState
workflow = StateGraph(state_schema=MessagesState)


# Define the function that calls the model
def call_model(state: MessagesState):
    prompt_template = ChatPromptTemplate.from_messages([
        SystemMessage(
            "You're rajneesh Osho, indian philosopher. Answer every query just as he[OSHO] does, use concise answers.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ])

    response = model.invoke(prompt_template.invoke(state))

    return {"messages": [AIMessage(response.content)]}


# Define the (single) node in the graph
workflow.add_edge(START, "model")
workflow.add_node("model", call_model)
workflow.add_edge("model", END)

# Add memory
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# Main running code!
config = {"configurable": {"thread_id": "darkdk123"}}

if __name__ == "__main__":
    # Testing locally!
    print("Chatbot is ready! Type 'exit' to stop.")

    while True:
        query = input("User >>> ")

        if query == "exit":
            break

        input_messages = [HumanMessage(query)]

        output = app.invoke({"messages": input_messages}, config)
        output["messages"][-1].pretty_print()  # output contains all messages in state

    # Logging the states, to understand workflow!
    state = app.get_state(config)
    with open("chat_logs.txt", "a") as f:
        f.writelines(
            (message.pretty_repr() + "\n" for message in state.values["messages"])
        )

    with open("state_logs.txt", "w") as f:
        f.writelines((str(i) for i in str(state)))
