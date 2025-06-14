"""
langchain_chat.py
___

Simple Chat Application with `LangChain` and `LangGraph's` in-memory `MemorySaver`.
It shows practical usage of memory and chat contexts. Currently for single user!
"""

# ________Imports___________

import asyncio

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

# from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.chatbot.utils import get_checkpointer, get_llm

# import langchain
# langchain.debug = True

# TODO: Remove this after testing.
# Load environment variables
# load_dotenv() # Not required as using docker.

# Initialize the language model
# HF_TOKEN = os.getenv("HF_TOKEN")

# llm = HuggingFaceEndpoint(
#     repo_id=MODEL_REPO_ID,
#     huggingfacehub_api_token=HF_TOKEN,
#     max_new_tokens=4000,
# )


print("Initialized LOADING MODEL!!")


class ImpersonateAgent:
    def __init__(self, model: BaseChatModel, system: str = ""):
        """Initializes the ChatBot"""

        self.model = model
        self.graph = None
        self.system = (
            system
            or "You're rajneesh Osho, indian philosopher. Answer every query just as he[OSHO] does, use concise answers."
        )

    async def init_graph(self, local: bool):
        """Compiles the ChatBot graph with built-in MessagesState"""
        if not self.graph:
            builder = StateGraph(state_schema=MessagesState)
            # Define the (single) node in the graph
            builder.add_edge(START, "model")
            builder.add_node("model", self.call_model)
            builder.add_edge("model", END)

            # Could use MemorySaver in development.
            # memory = MemorySaver()
            self.graph = builder.compile(
                MemorySaver() if local else ((await get_checkpointer())[0])
            )

        return self.graph

    async def call_model(self, state: MessagesState):
        response = self.model.astream(
            input=await self._get_prompt(state["messages"]),
        )

        async for token in response:
            yield {"messages": [AIMessageChunk(content=token.content)]}

    async def _get_prompt(self, messages: list[AnyMessage]):
        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(self.system),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        return await prompt_template.ainvoke({"messages": messages})

    # def __call__(self, *args: Any, **kwds: Any) -> Any:
    #     return self.graph(self, *args, **kwds)


config = RunnableConfig(
    configurable={"thread_id": "darkdk123"},
)


async def compile_graph(local: bool = False) -> CompiledStateGraph:
    graph = await ImpersonateAgent(get_llm()).init_graph(local)

    try:
        # Generate the PNG image from the graph
        png_image_data = graph.get_graph().draw_mermaid_png()
        # Save the image to a file in the current directory
        with open("graph_image_mermaid.png", "wb") as f:
            f.write(png_image_data)
    except Exception as e:
        # This requires some extra dependencies and is optional
        # logger.info(f"An error occurred: {e}")
        print(f"An error occurred while compiling the `agent graph`: {e}")

    return graph


async def main(local: bool = False):
    app = await ImpersonateAgent(get_llm()).init_graph(local)

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
            if (
                isinstance(message, AIMessageChunk)
                and isinstance(metadata, dict)
                and metadata["langgraph_node"] == "model"
            ):
                if message.response_metadata.get("finish_reason", None) == "stop":
                    # Streaming done!
                    print(message.content, " >>> END")
                    break
                print(message.content, end=" | ")
                # print(input_messages)

    return app


if __name__ == "__main__":
    # Testing locally!
    print("Chatbot is ready! Type 'exit' to stop.")

    # Ensure to open the pg_pool used.
    asyncio.run(get_checkpointer(open=True))

    app = asyncio.run(main())

    # Logging the states, to understand workflow!
    state = app.get_state(config)
    with open("chat_logs.txt", "a") as f:
        f.writelines(
            (message.pretty_repr() + "\n" for message in state.values["messages"])
        )

    with open("state_logs.txt", "w") as f:
        f.writelines((str(i) for i in str(state)))
