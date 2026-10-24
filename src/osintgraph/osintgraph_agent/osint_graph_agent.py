import asyncio
import re
import json
import os
import requests
from itertools import islice
import logging


from rich.console import Console
from rich.live import Live
from typing import Annotated, Any, List, Literal, Union
from typing_extensions import TypedDict
from pydantic import BaseModel

from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.messages import (
    AIMessage, AnyMessage, HumanMessage, RemoveMessage, 
    SystemMessage, ToolMessage
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from langgraph.checkpoint.memory import InMemorySaver
from langmem.short_term import SummarizationNode, RunningSummary
import langmem.short_term.summarization as summarization_mod

from ..credential_manager import get_credential_manager
from ..services import llm_models
from ..neo4j_manager import Neo4jManager

from .osint_prompts import (
    INVESTIGATION_PROMPT,
    RESPONSE_PROMPT,
    CUSTOM_INITIAL_SUMMARY_PROMPT,
    CUSTOM_EXISTING_SUMMARY_PROMPT
)
from .osint_tools import (
    build_get_templates_list_tool,
    build_display_templates_tool,
    build_run_template_chunked_tool,
    build_cypher_query_tool,
    build_semantic_cypher_tool
)
from .osint_utils import (
    generate_account_summary,
    generate_image_summary,
    generate_post_summary
)

from ..constants import USEFUL_FIELDS, TRACK_FILE, TREE_TOP_API, CONTENTS_API, TEMPLATES_DIR

from ..ui import ui  
# from dotenv import load_dotenv
# load_dotenv()

# Initialize credential manager
cm = get_credential_manager()
live_console = Console()
def _skip_adjust_messages_before_summarization(
    preprocessed_messages, token_counter
) -> list[AnyMessage]:
    live_console.print("[grey70]Summarizing conversation so far...[/grey70]")
    return preprocessed_messages.messages_to_summarize

# Override the default adjust function to skip any adjustments
summarization_mod._adjust_messages_before_summarization = _skip_adjust_messages_before_summarization

class State(TypedDict):
    question: List[HumanMessage]
    messages: Annotated[list, add_messages]
    scratchpad: Annotated[list, add_messages]
    context: dict[str, RunningSummary]  


class OSINTGraphAgent:
    def __init__(self, debug=False):
        self.debug = debug
        self.provider = llm_models.get_llm_provider()
        self.provider_label = (
            "OrcaRouter" if self.provider == llm_models.orcarouter.PROVIDER_ID else "Gemini"
        )
        self.chat_model = llm_models.get_chat_model("agent")
        if self.chat_model is None:
            raise llm_models.orcarouter.OrcaRouterError(
                "No LLM is configured. Run `osintgraph setup orcarouter` for "
                "OrcaRouter Cyber Inference or `osintgraph setup gemini`.",
                kind="auth",
            )
        self.llm = self.chat_model
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        self.nm = Neo4jManager()
        self.memory = InMemorySaver()
        self.schema_description = self.nm.execute_read(self.nm.get_schema_summary)
        self.config = {"configurable": {"thread_id": "osintgraph_session_1"}, "recursion_limit": 500}
        self.sync_template()
        self.initialize_agent()
        self.initialize_vector_store()
        self.initialize_graph()


    
    def sync_template(self):
        # ===== LOAD TRACKING DATA =====
        if os.path.exists(TRACK_FILE):
            with open(TRACK_FILE, "r") as f:
                tracking_data = json.load(f)
        else:
            tracking_data = {"folder_sha": None, "files": {}}

        try:
            resp = requests.get(TREE_TOP_API, timeout=10)
            if resp.status_code != 200:
                self.logger.warning(f"⚠  Tree API error {resp.status_code}, skipping template sync.")
                return

            tree_data = resp.json().get("tree", [])
            folder_sha = None

            for item in tree_data:
                if item["path"] == "templates" and item["type"] == "tree":
                    folder_sha = item["sha"]
                    break

            if not folder_sha:
                self.logger.warning("⚠  'templates' folder not found.")
                return

            if tracking_data["folder_sha"] == folder_sha:
                self.logger.info("✓  All templates are up to date.")
                return  # No change

            # self.logger.info("Templates folder changed. Syncing...")

            resp = requests.get(CONTENTS_API, timeout=10)
            if resp.status_code != 200:
                self.logger.warning(f"⚠ Contents API error {resp.status_code}, skipping template sync.")
                return

            remote_files = resp.json()
            remote_index = {f["name"]: f["sha"] for f in remote_files if f["type"] == "file"}

            updated_count = 0

            # Download changed or new files
            for name, sha in remote_index.items():
                if tracking_data["files"].get(name) != sha:
                    file_info = next(f for f in remote_files if f["name"] == name)
                    r = requests.get(file_info["download_url"], timeout=10)
                    if r.status_code == 200:
                        with open(os.path.join(TEMPLATES_DIR, name), "wb") as f:
                            f.write(r.content)
                        tracking_data["files"][name] = sha
                        updated_count += 1

            # ===== UPDATE TRACKING FILE AFTER SUCCESSFUL SYNC
            tracking_data["folder_sha"] = folder_sha
            with open(TRACK_FILE, "w") as f:
                json.dump(tracking_data, f)

            if updated_count > 0:
                self.logger.info(f"{updated_count} template file(s) added/updated.")
            else:
                self.logger.info("✅ Templates are already up to date.")

        except requests.RequestException as e:
            self.logger.warning(f"⚠ Network error: {e}")
    def initialize_vector_store(self):
        live_console.print("[grey70]⚡ Updating vectors...[/grey70]")
        def batched(iterable, size):
            it = iter(iterable)
            while True:
                batch = list(islice(it, size))
                if not batch:
                    break
                yield batch

        def inject_summaries_into_posts(post_nodes):
            for post in post_nodes:
                if post.get("image_analysis"):
                    post["image_analysis"] = generate_image_summary(post["image_analysis"])
                if post.get("post_analysis"):
                    post["post_analysis"] = generate_post_summary(post["post_analysis"])
            return post_nodes

        def inject_summaries_into_persons(person_nodes):
            for person in person_nodes:
                if person.get("account_analysis"):
                    person["account_analysis"] = generate_account_summary(person["account_analysis"])
            return person_nodes

        def fetch_nodes_missing_vectors(label, field):
            """
            Fetch nodes where:
            - the field exists and is not null/empty
            - the corresponding vector field is null
            """
            query = f"""
            MATCH (n:{label})
            WHERE n.{field} IS NOT NULL AND trim(n.{field}) <> "" AND n.{field}_vector IS NULL
            RETURN n.id AS id, n.{field} AS content
            """
            return self.nm.execute_read(self.nm.run_query_with_params, query)

        def store_field_vectors_batch(label, batch_data):
            query = f"""
            UNWIND $data AS row
            MATCH (n:{label} {{id: row.id}})
            SET n[row.property] = row.vector
            """
            self.nm.execute_write(self.nm.run_query_with_params, query, {"data": batch_data})

        for label in USEFUL_FIELDS:
            # print(f"🔄 Processing {label} nodes...")

            for field in USEFUL_FIELDS[label]:
                # print(f"🔸 Embedding field: {label}.{field}")

                # Fetch only nodes missing this vector field
                nodes = fetch_nodes_missing_vectors(label, field)

                # Inject summaries if needed
                if label == "Person" and field == "account_analysis":
                    nodes = inject_summaries_into_persons(nodes)
                elif label == "Post" and field in ["post_analysis", "image_analysis"]:
                    nodes = inject_summaries_into_posts(nodes)

                texts = []
                refs = []

                for node in nodes:
                    content = node.get("content")
                    if content:
                        texts.append(str(content))
                        refs.append({"id": node["id"], "property": f"{field}_vector"})

                embeddings = llm_models.get_embeddings_model()
                if embeddings is None:
                    self.logger.warning(
                        "⚠  No embeddings provider configured; skipping graph vector indexing."
                    )
                    break
                for text_batch, ref_batch in zip(batched(texts, 200), batched(refs, 200)):
                    try:
                        # print(f"✨ Embedding batch of size {len(text_batch)} for {label}.{field}")
                        vectors = embeddings.embed_documents(text_batch)
                        batch_data = [
                            {**ref, "vector": vector}
                            for ref, vector in zip(ref_batch, vectors)
                        ]
                        store_field_vectors_batch(label, batch_data)
                    except Exception as e:
                        self.logger.error(f"⚠  Failed to embed {label}.{field} batch: {e}")

            live_console.print(f"[grey70]• ✓  {label}[/grey70]", end=" ")


    def initialize_agent(self):

        self.tools = [
            build_cypher_query_tool(self.nm),
            build_semantic_cypher_tool(self.nm),
            build_get_templates_list_tool(),
            build_display_templates_tool(),
            build_run_template_chunked_tool()

        ]

        self.llm_with_tools = self.chat_model.bind_tools(self.tools)
        # OrcaRouter is a metered gateway rather than a free tier, so the
        # Gemini-specific two-speed model switch has nothing to throttle.
        if self.provider == llm_models.orcarouter.PROVIDER_ID:
            self.llm_with_tools_with_limit = self.llm_with_tools
        else:
            self.llm_with_tools_with_limit = llm_models.get_chat_model("agent_limited").bind_tools(self.tools)
        self.llm = self.llm_with_tools
        self.logger.info("Agent is in beta — responses may be inconsistent. Ask for clarification if needed.")
        self.logger.info("Type 'exit' to end the session.")




    def initialize_graph(self):
    
        message_summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=self.chat_model,
            max_tokens=100000,
            max_tokens_before_summary=200000,
            max_summary_tokens=3000,
            input_messages_key="messages",
            output_messages_key="messages",
            initial_summary_prompt=CUSTOM_INITIAL_SUMMARY_PROMPT,
            existing_summary_prompt=CUSTOM_EXISTING_SUMMARY_PROMPT,
        )

        scratchpad_summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=self.chat_model,
            max_tokens=100000,
            max_tokens_before_summary=150000,
            max_summary_tokens=3000,
            input_messages_key="scratchpad",
            output_messages_key="scratchpad",
            initial_summary_prompt=CUSTOM_INITIAL_SUMMARY_PROMPT,
            existing_summary_prompt=CUSTOM_EXISTING_SUMMARY_PROMPT,
        )

                
        class ToolNode:
            """A node that runs the tools requested in the last AIMessage."""

            def __init__(self, tools: list, agent) -> None:
                self.tools_by_name = {tool.name: tool for tool in tools}
                self.agent = agent  

            def __call__(self, inputs: dict):
                if messages := inputs.get("scratchpad", []):
                    message = messages[-1]
                else:
                    raise ValueError("No message found in input")
                outputs = []
                for tool_call in message.tool_calls:
                    if tool_call["args"].get("__arg1", "").startswith("Prepare:"):
                        self.agent.llm = self.agent.llm_with_tools_with_limit
                        # print("switched with rate limit ")

                    tool_result = self.tools_by_name[tool_call["name"]].invoke(
                        tool_call["args"]
                    )
                    outputs.append(
                        ToolMessage(
                            content=json.dumps(tool_result),
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )
                return {"scratchpad": outputs }

        def thought_node(state: State):
            
            system_message = INVESTIGATION_PROMPT.format(
                schema_description=self.schema_description
                )
            
            return { "scratchpad": [self.llm.invoke( [SystemMessage(content=system_message)] + state["messages"] + state["question"] + state["scratchpad"])] }


        def summary_node(state: dict) -> dict:
            """
            Reads the full message history and generates a smooth, natural Final Answer
            based on all reasoning, evidence, and tool results so far.
            """
            scratchpad = state["scratchpad"]

            # Format all relevant prior messages into a context string
            formatted = []
            formatted.append(f"[USER QUERY]:\n{state['question'][0].content}\n")
            for msg in scratchpad:
                role = msg.get("role") if isinstance(msg, dict) else msg.type
                content = msg.get("content") if isinstance(msg, dict) else msg.content

                if role in ("tool"):
                    name = msg.get("name", "tool") if isinstance(msg, dict) else getattr(msg, "name", "tool")
                    formatted.append(f"**[TOOL OUTPUT - {name}]**\n```\n{content.strip()}\n```")
                elif role == "ai":
                    formatted.append(f"[THOUGHT]:\n{content}")

            summary_prompt = RESPONSE_PROMPT.format(
                schema_description=self.schema_description,
                conversation="\n".join(formatted),
                question=state["question"][0].content
            )

            summary = self.llm.invoke([HumanMessage(content=summary_prompt)])
            self.llm = self.llm_with_tools
            return {"messages": state["question"]  + [summary], "scratchpad": [RemoveMessage(REMOVE_ALL_MESSAGES)]}

        def tools_condition(
            state: Union[list[AnyMessage], dict[str, Any], BaseModel],
            messages_key: str = "scratchpad",
        ) -> Literal["thought_node", "tool_node", "summary_node"]:
            """
            Custom condition function to route to 'tools' if the last message contains tool calls,
            otherwise route to the 'summary' node for finalization.
            """
            if isinstance(state, list):
                ai_message = state[-1]
            elif isinstance(state, dict) and (messages := state.get(messages_key, [])):
                ai_message = messages[-1]
            elif messages := getattr(state, messages_key, []):
                ai_message = messages[-1]
            else:
                raise ValueError(f"No messages found in input state to tool_edge: {state}")

            # Check if the last message is an AI message and contains response metadata
            if isinstance(ai_message, AIMessage):
                response_metadata = getattr(ai_message, "response_metadata", {})
                finish_reason = response_metadata.get("finish_reason", None)

                # Check if finish_reason is MALFORMED_FUNCTION_CALL
                if finish_reason == "MALFORMED_FUNCTION_CALL":
                    return "thought_node"  # Route back to thought_node for retry
        
            # Check if there are tool calls
            if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
                return "tool_node"

            # Default path when no tools were invoked
            return "summary_node"
        
        graph_builder = StateGraph(State)

        graph_builder.add_node("message_summarization_node", message_summarization_node)
        graph_builder.add_node("scratchpad_summarization_node", scratchpad_summarization_node)
        graph_builder.add_node("thought_node", thought_node)
        graph_builder.add_node("summary_node", summary_node)
        tool_node = ToolNode(tools=self.tools, agent=self)
        graph_builder.add_node("tool_node", tool_node)
        graph_builder.add_edge(START, "message_summarization_node")
        graph_builder.add_edge("message_summarization_node", "thought_node")
        graph_builder.add_conditional_edges(
            "thought_node",
            tools_condition,
        )
        graph_builder.add_edge("tool_node", "scratchpad_summarization_node")
        graph_builder.add_edge("scratchpad_summarization_node", "thought_node")
        graph_builder.add_edge("summary_node", END)


        self.graph = graph_builder.compile(checkpointer=self.memory)

    async def stream_graph_updates(self, user_input: str):
        state = {"question": [HumanMessage(content=user_input)], "scratchpad": [AIMessage(content="Thought:")]}
        live_console.print(f"\n✨ [light_salmon1]{self.provider_label}:[/light_salmon1] ")

        ui.status_text.clear()
        ui.output_text .clear()
        # Start Rich Live context for dynamic live_console updates
        with Live(ui.render(), refresh_per_second=10) as live:
            ui._live = live 

            while True:
                try:
                    stream_task = asyncio.create_task(
                        self._astream_messages(state)
                    )
                    await stream_task
                    break
                except (KeyboardInterrupt, asyncio.CancelledError):
                    # Cancel stream properly
                    stream_task.cancel()
                    ui.status_text.clear()
                    ui.output_text.clear()
                    # live.console.print("[grey50]⚡ Interrupted, ready for next input[/grey50]")
                    self.graph.update_state(
                        self.config,
                        {"scratchpad": [RemoveMessage(REMOVE_ALL_MESSAGES)]}
                    )

                    raise
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str:
                        # Inline regex extraction of retry_delay
                        m = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", err_str)
                        delay = int(m.group(1)) if m else 10
                        delay += 15  # small buffer
                        prev_status_items = list(ui.status_text.items)
                        for remaining in range(delay, 0, -1):
                            ui.status_text.set(f"[yellow]Rate limit hit. Retrying in {remaining}s[/yellow]")
                            ui.refresh()
                            await asyncio.sleep(1)  # wait 1 second per loop

                        ui.status_text.items = prev_status_items
                        ui.refresh()

                        continue
                    else:
                        raise  # other errors bubble up
    async def _astream_messages(self, state):
        async for message, metadata in self.graph.astream(
            state,
            config=self.config,
            stream_mode="messages",
        ):
            if metadata.get("langgraph_node") == "summary_node" and isinstance(message, AIMessage):
                ui.output_text += message.content
                ui.refresh()
                
    async def run(self):
        live_console.print(f"\n✨ [light_salmon1]{self.provider_label}:[/light_salmon1] ")
        live_console.print("Hi, I’m your OSINTGraph investigator. I’ll analyze the Neo4j graph for your OSINT queries. What’s on your mind today?")
            
        while True:
            live_console.print("\n👤 [light_salmon1]Analyst:[/light_salmon1]")
            user_input = input()
        
            if not user_input:
                continue
            if user_input.lower() == "exit":

                live_console.print("[grey70]🛰  Session ended[/grey70]")
                break
            try:
                await self.stream_graph_updates(user_input)
            except (KeyboardInterrupt, asyncio.CancelledError):
                # clean exit on Ctrl+C
                live_console.print("[grey70]Interrupted by user[/grey70]")

            except Exception as e:
                print("Error:", e)





