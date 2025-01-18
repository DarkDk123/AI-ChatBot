"""
langchain_chat.py
___

Simple Chat Application with `LangChain` and `LangGraph's` in-memory `MemorySaver`.
It shows practical usage of memory and chat contexts. Currently for single user!
"""

# ________Imports___________

# from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessageChunk, AnyMessage
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


import os
import asyncio
from dotenv import load_dotenv


# import langchain
# langchain.debug = True

# Load environment variables
load_dotenv()

# Initialize the language model
# HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_REPO_ID = os.getenv("MODEL_REPO_ID", "")

# llm = HuggingFaceEndpoint(
#     repo_id=MODEL_REPO_ID,
#     huggingfacehub_api_token=HF_TOKEN,
#     max_new_tokens=4000,
# )

# model = ChatHuggingFace(llm=llm)
model = ChatGroq(api_key=GROQ_API_KEY, model=MODEL_REPO_ID)  # type: ignore

print("Initialized LOADING MODEL!!")


class ImpersonateAgent:
    def __init__(self, model: BaseChatModel, system: str = ""):
        """Initializes the ChatBot"""

        self.model = model
        self.system = (
            system
            or "You're rajneesh Osho, indian philosopher. Answer every query just as he[OSHO] does, use concise answers."
        )

        self.init_graph()

    def init_graph(self):
        """Compiles the ChatBot graph with built-in MessagesState"""

        builder = StateGraph(state_schema=MessagesState)
        # Define the (single) node in the graph
        builder.add_edge(START, "model")
        builder.add_node("model", self.call_model)
        builder.add_edge("model", END)

        # Compiling with MemorySaver
        memory = MemorySaver()
        self.graph = builder.compile(checkpointer=memory)

    async def call_model(self, state: MessagesState):
        response = self.model.astream(
            input=await self._get_prompt(state["messages"]),
        )

        async for token in response:
            yield {"messages": [AIMessageChunk(content=token.content)]}

    async def _get_prompt(self, messages: list[AnyMessage]):
        prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(self.system),
            MessagesPlaceholder(variable_name="messages"),
        ])

        return await prompt_template.ainvoke({"messages": messages})

    # def __call__(self, *args: Any, **kwds: Any) -> Any:
    #     return self.graph(self, *args, **kwds)


config = RunnableConfig(
    configurable={"thread_id": "darkdk123"},
)

app = ImpersonateAgent(model).graph


async def main():
    while True:
        query = input("User >>> ")

        if query == "exit":
            break

        input_messages = [HumanMessage(query)]

        # output = app.invoke({"messages": input_messages}, config)
        # output["messages"][-1].pretty_print()  # output contains all messages in state

        async for message, metadata in app.astream(
            {"messages": input_messages},
            config,
            stream_mode="messages",
        ):
            if isinstance(message, AIMessageChunk) and isinstance(metadata, dict):
                if metadata["langgraph_node"] == "model":
                    if message.response_metadata.get("finish_reason", None) == "stop":
                        # Streaming done!
                        print(message.content, " >>> END")
                        break
                    print(message.content, end=" | ")


if __name__ == "__main__":
    # Testing locally!
    print("Chatbot is ready! Type 'exit' to stop.")

    asyncio.run(main())

    # Logging the states, to understand workflow!
    state = app.get_state(config)
    with open("chat_logs.txt", "a") as f:
        f.writelines(
            (message.pretty_repr() + "\n" for message in state.values["messages"])
        )

    with open("state_logs.txt", "w") as f:
        f.writelines((str(i) for i in str(state)))
