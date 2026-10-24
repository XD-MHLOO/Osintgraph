import json
import os
import re
from datetime import datetime
import logging
import time

import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.panel import Panel
from langchain.tools import StructuredTool
from langchain_core.tools import Tool

from ...services.llm_analyzer import LLMAnalyzer
from ...services import llm_models
from ...utils.schemas import GetTemplateDetailsInput
from ...constants import TEMPLATES_DIR, DEBUG_LOGS_DIR
from ...ui import ui

logger = logging.getLogger(__name__)

console = Console()


def _template_model():
    """Template analysis uses the active provider's chat model."""
    if llm_models.get_llm_provider() == llm_models.orcarouter.PROVIDER_ID:
        return llm_models.get_chat_model("template")
    return llm_models.gemini_2_5_flash_llm_with_limit


def get_template_llm():
    """Built lazily so importing the CLI never constructs a network client."""
    return LLMAnalyzer(default_model=_template_model())



def detect_and_print(text):
    lines = text.strip().splitlines()

    # Step 1: Detect fenced code block
    if lines and lines[0].startswith("```"):
        match = re.search(r"^```(\w+)?", lines[0])
        lang = match.group(1).lower() if match and match.group(1) else ""
        code_content = "\n".join(lines[1:-1]) if len(lines) > 2 else ""

        ui.status_text += (
            Panel(
                Syntax(code_content, lang or "text", theme="monokai"),
                style="on rgb(30,30,30)",
                border_style="bright_black"
            )
        )
        return

    # Step 2: Try JSON parsing
    try:
        parsed = json.loads(text)
        pretty_json = json.dumps(parsed, indent=2)
        ui.status_text +=(
            Panel(
                Syntax(pretty_json, "json", theme="monokai"),
                style="on rgb(30,30,30)",
                border_style="bright_black"
            )
        )
        return
    except json.JSONDecodeError:
        pass

    # Step 3: Markdown detection
    if any(marker in text for marker in ["**", "* ", "#", "\n>"]):
        ui.status_text += (
            Panel(
                Markdown(text),
                style="on rgb(30,30,30)",
                border_style="bright_black"
            )
        )
    else:
        ui.status_text += (
            Panel(
                text,
                style="on rgb(30,30,30)",
                border_style="bright_black"
            )
        )

def validate_template(filename: str) -> dict:
    file_path = os.path.join(TEMPLATES_DIR, filename)

    required_top_level_keys = {"name", "description", "input_fields", "system_prompt", "user_prompt"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"YAML parsing failed: {e}")
    
    # Check top-level required keys
    missing_keys = required_top_level_keys - set(template.keys())
    if missing_keys:
        raise ValueError(f"Missing required keys: {missing_keys}")
    
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", template["name"]):
        raise ValueError("Template name must be alphanumeric and may include _ or -")

    # Check input_fields
    if not isinstance(template["input_fields"], list):
        raise ValueError("input_fields must be a list")

    for field in template["input_fields"]:
        if not isinstance(field, dict):
            raise ValueError("Each input field must be a dictionary")
        
        if "name" not in field or "description" not in field:
            raise ValueError(f"Each input field must include 'name' and 'description': {field}")
        
        if not isinstance(field["name"], str):
            raise ValueError(f"Field 'name' must be a string: {field}")
        
        if not isinstance(field["description"], str):
            raise ValueError(f"Field 'description' must be a string: {field}")

    # Check that all placeholders exist in user_prompt
    user_prompt = template["user_prompt"]
    for field in template["input_fields"]:
        placeholder = "{" + field["name"] + "}"
        if placeholder not in user_prompt:
            raise ValueError(f"Placeholder {placeholder} not found in user_prompt")

    return template

def load_all_templates(input) -> dict:
    """
    Scans all .yaml templates in the folder and validates each.

    Returns:
        {
            "valid": [ {"name": str, "description": str}, ... ],
            "invalid": [ {"filename": str, "error": str}, ... ]
        }
    """
    valid_templates = []
    invalid_templates = []
    console.print("[grey70]Retrieving Templates...[/grey70]")

    for filename in os.listdir(TEMPLATES_DIR):
        if filename.endswith(".yaml"):
            try:
                template = validate_template(filename)
                valid_templates.append({
                    "name": template["name"],
                    "description": template["description"].strip(),
                    "input_fields": [
                        {
                            "name": field["name"],
                            "description": field["description"].strip()
                        }
                        for field in template["input_fields"]
                    ]
                })
            except ValueError as e:
                invalid_templates.append({
                    "filename": filename,
                    "error": str(e)
                })

    return {
        "valid": valid_templates,
        "invalid": invalid_templates
    }

def run_template(template_name: str, args: dict) -> str:
    if not template_name.endswith(".yaml"):
        template_name += ".yaml"

    filename = template_name

    try:
        template = validate_template(filename)

    except ValueError as e:
        return f"Invalid Template: {e}"
    
    # Format user prompt
    try:
        rendered_user_prompt = template["user_prompt"].format(**args)
    except KeyError as e:
        return json.dumps({
            "error": f"Missing required argument: {str(e)}. Please provide all required fields and try again.",
            "missing_argument": str(e),
            "expected_placeholders": list(template.get("input_fields", [])),
            "raw_input": args
        }, indent=2)

    # Build full prompt for debug
    full_prompt = f"[SYSTEM]\n{template['system_prompt'].strip()}\n\n[USER]\n{rendered_user_prompt.strip()}"
    ui.status_text.set(f"[grey70]Executing Template {template_name}...[/grey70]")
    time.sleep(70)
    result = get_template_llm().analyze_text(user_prompt=rendered_user_prompt, system_prompt=template['system_prompt'], json_output=False)
    ui.status_text.set(f"[grey70]Results from {template_name}:[/grey70]")

    detect_and_print(result)

    # Save to debug file
    
    if logger.isEnabledFor(logging.DEBUG):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prompt_path = os.path.join(DEBUG_LOGS_DIR, f"template_rendered_prompt_{timestamp}.txt")
        result_path = os.path.join(DEBUG_LOGS_DIR,f"template_result_{timestamp}.txt")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(full_prompt)
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(result)
        ui.status_text += (f"[grey70]Saved debug rendered prompt to: {prompt_path}[/grey70]")
        ui.status_text += (f"[grey70]Saved debug template result to: {result_path}[/grey70]")

    return {
        "template_name": template_name,
        "result": result,
    }


def display_templates(template_name: str) -> dict:
    """
    Returns structured info about a specific template:
    - name
    - description
    - input_fields (with name and description)
    - system_prompt
    - user_prompt

    Raises ValueError if invalid.
    """
    if not template_name.endswith(".yaml"):
        template_name += ".yaml"

    try:
        template = validate_template(template_name)
    except Exception as e:
        return f"Invalid template: {e}"

    file_path = os.path.join(TEMPLATES_DIR, template_name)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    syntax = Syntax(content, "yaml", theme="monokai", line_numbers=True)
    console.print(f"[grey70]Displaying template: {template_name}[grey70]")
    console.print(syntax)
    
    return {
        "name": template["name"],
        "description": template["description"].strip(),
        "input_fields": [
            {
                "name": field["name"],
                "description": field["description"].strip()
            }
            for field in template["input_fields"]
        ],
        "system_prompt": template["system_prompt"],
        "user_prompt": template["user_prompt"]
    }


buffer_storage: dict[str, list[str]] = {}

# def run_template_chunked_json(input_str: str) -> dict:
#     data = extract_json_block(input_str)
#     if isinstance(data, dict) and "error" in data:
#         return {
#             "error": f"Chunk rejected: {data['error']}"
#         }
#     template_name = data["template_name"]
#     args = data["args"]

#     args = dict(args)  # clone to avoid mutating caller input
#     is_final_chunk = args.pop("is_final_chunk", False)

#     template_info = display_templates(template_name)
#     input_fields = [field["name"] for field in template_info["input_fields"]]

#     chunked_fields = [field for field in input_fields if field in args]

#     if not chunked_fields:
#         return {
#             "error": f"No valid input field found in chunk. Expected one of: {input_fields}"
#         }
#     if len(chunked_fields) > 1:
#         return {"error": "Only one input field can be chunked at a time."}

#     chunked_field = chunked_fields[0]
#     chunk_value = args[chunked_field]

#     # Buffer this chunk
#     buffer_storage.setdefault(chunked_field, []).append(chunk_value)

#     # If not final, just acknowledge
#     if not is_final_chunk:
#         return {
#             "status": "chunk received",
#             "buffer_length": len(buffer_storage[chunked_field]),
#             "chunked_field": chunked_field,
#         }

#     # Final chunk: assemble full input
#     if chunked_field not in buffer_storage:
#         return {
#             "error": f"No previous chunks received for field '{chunked_field}'"
#         }

#     full_content = "\n".join(buffer_storage[chunked_field])
#     full_args = {chunked_field: full_content}

#     # Copy static fields (non-chunked ones)
#     for field in input_fields:
#         if field in args and field != chunked_field:
#             full_args[field] = args[field]

#     # Clean up buffer
#     del buffer_storage[chunked_field]

#     return run_template(template_name, full_args)

def run_template_chunked(input_str: str):
    global buffer_storage  # Optional: if using a global variable

    if input_str.startswith("Prepare:"):
        template_name = input_str.removeprefix("Prepare:").strip()

        templates = load_all_templates({})["valid"]
        matched_template = next((t for t in templates if t["name"] == template_name), None)

        if not matched_template:
            available = ", ".join(t["name"] for t in templates)
            return f"[Error: Template '{template_name}' not found. Available templates: {available}]"

        input_fields = [field for field in matched_template["input_fields"]]
        buffer_storage.clear()
        buffer_storage["template"] = template_name
        buffer_storage["input_fields"] = input_fields
        buffer_storage["chunks"] = {}
        buffer_storage["processed_count"] = 0
        buffer_storage["total_fields"] = len(input_fields)

        console.print(f"[grey70]Preparing Template {template_name}...[/grey70]")

        return (
            f"[Template prepared: {template_name}]\n"
            f"Input fields: {', '.join(f['name'] for f in input_fields)}\n"
            "Use 'Start:<field>' to begin chunking."
        )

    elif input_str.startswith("Start:"):
        field_name = input_str.removeprefix("Start:").strip()

        if "template" not in buffer_storage:
            return "[Error: No template prepared. Use 'Prepare:<template_name>' first.]"


        input_fields = buffer_storage.get("input_fields", [])
        field_obj = next((f for f in input_fields if f["name"] == field_name), None)

        if not field_obj:
            expected_fields = ", ".join(sorted(f["name"] for f in input_fields))
            return (
                f"[Error: '{field_name}' is not a valid input field for template '{buffer_storage['template']}']\n"
                f"Expected fields: {expected_fields}"
            )

        buffer_storage["current_field"] = field_name
        buffer_storage["chunks"][field_name] = []
        buffer_storage["processed_count"] += 1
        
        field_desc = field_obj.get("description")
        ui.status_text.set(f"[grey70]Processing field ({buffer_storage['processed_count']}/{buffer_storage['total_fields']}): {field_name}...[/grey70]")
        ui.refresh()

        return (
            f"[Start chunking for: {field_name}]\n"
            f"Description: {field_desc}\n"
            f"Now send Chunk:<data>"
        )

    elif input_str.startswith("Chunk:"):
        if "current_field" not in buffer_storage or not buffer_storage["current_field"]:
            return "[Error: No active field. Use 'Start:<field_name>' before sending chunks.]"

        chunk_data = input_str.removeprefix("Chunk:").strip()
        field = buffer_storage["current_field"]
        buffer_storage["chunks"].setdefault(field, []).append(chunk_data)

        return (
            f"[Chunk received for: {field}]\n"
            f"Total chunks for {field}: {len(buffer_storage['chunks'][field])}\n"
            f"If more data is available, continue retrieving using SKIP / LIMIT."
        )

    elif input_str.startswith("End:"):
        field_name = input_str.removeprefix("End:").strip()
        if buffer_storage.get("current_field") != field_name:
            return f"[Error: End:{field_name} does not match current active field: {buffer_storage.get('current_field')}]"

        buffer_storage["current_field"] = None

        all_fields = [f["name"] for f in buffer_storage["input_fields"]]
        completed = list(buffer_storage["chunks"].keys())
        remaining = [f for f in all_fields if f not in completed]

        remaining_str = ", ".join(remaining) if remaining else "None (all fields complete)"

        return f"[Finished chunking for: {field_name}]\nRemaining fields: {remaining_str}\nSend 'Start:<next_input_field>' or 'Run:{buffer_storage['template']}' when ready."

    elif input_str.startswith("Run:"):
        template_name = input_str.removeprefix("Run:").strip()

        if template_name != buffer_storage.get("template"):
            return f"[Error: Template mismatch. Expected to run '{buffer_storage.get('template')}', got '{template_name}']"

        args = {
            field: "\n".join(chunks)
            for field, chunks in buffer_storage.get("chunks", {}).items()
        }
        
        result = run_template(template_name, args)
        buffer_storage.clear()
        return result

    else:
        return (
            "[Error: Unrecognized command. Use one of the following:\n"
            "- Prepare:<template_name>\n"
            "- Start:<input_field_name>\n"
            "- Chunk:<data>\n"
            "- End:<input_field_name>\n"
            "- Run:<template_name>]"
        )

def build_get_templates_list_tool():
    return Tool.from_function(
        name="get_templates_list",
        func=load_all_templates,
        description=(
            "Retrieve all YAML OSINT investigation templates.\n\n"
            "This tool:\n"
            "- Returns `valid` templates: includes name, description, and required input fields.\n"
            "- Returns `invalid` templates: shows filename and error (e.g., missing fields or bad formatting).\n"
            "Don't need to mention if no invalid templates."
            "Use this to help the user find available templates or debug broken ones."
        )

    )

def build_display_templates_tool():
    return StructuredTool.from_function(
        name="display_templates",
        func=display_templates,
        args_schema=GetTemplateDetailsInput,
        description="""
            Purpose:
            - Show the full content of a specific OSINT investigation template.

            When to Use:
            - Call this tool only when the user explicitly requests to view or inspect a template.

            What It Provides:
            - Displays the template content on the console.
            - Returns details including:
                - Template description
                - Required input fields
                - System prompt
                - User prompt
            """
    )

def build_run_template_chunked_tool():
    return Tool.from_function(
        func=run_template_chunked,
        name="run_template_chunked_tool",
        description="""
            # 📌 OSINTGraph Template Chunking Tool (Final Consolidated Spec)

            ## Purpose

            Use this tool to execute a named template by streaming structured input fields in chunks.

            ---

            ## Command Sequence

            ### 1. Prepare a template


            ```
            Prepare:<template_name>
            ```

            * Initializes the template buffer.
            * Returns the list of expected `input_fields`.

            ### 2. Start an input field

            ```
            Start:<input_field_name>
            ```

            * Opens submission for one field.
            * Must be called **before any chunks** for that field.
            * You may not retrieve any data for a field until you have started it.
            * Only after Start may you retrieve data in chunks.

            ### 3. Retrieve + submit data in chunks

            * Fetch data from Neo4j using **SKIP + LIMIT**.
            * Each batch must be submitted as:



            ```
            Chunk:<structured_section>
            ```

            * A **section** = one complete data entry for the field (post, comment, account, etc.).

            #### Chunk Size Rules (based on required attributes)

            1. Requires `Post.image_analysis` → **1 per chunk**
            (`SKIP 0 LIMIT 1`, `SKIP 1 LIMIT 1`, …).
            2. Requires `Person.account_analysis` or `Post.post_analysis` → **5 per chunk**.
            3. Requires only standard attributes (username, bio, caption, text) → **20 per chunk**.

            **Priority Rule:** Always use the **smallest applicable chunk size**:
            `ImageAnalysis (1) > Post/AccountAnalysis (5) > Standard (20)`

            #### Formatting Rules

            * Each chunk must contain **all attributes** required by the field’s description.
            * If missing → set value to `null`.
            * Never pad with fake entries; final chunk may be smaller.
            * Always send one chunk immediately before retrieving the next.

            ### 4. End the field



            ```
            End:<input_field_name>
            ```

            * Marks the field complete.
            * You may then `Start` another field.

            ### 5. Run the template



            ```
            Run:<template_name>
            ```

            * Executes the template with all submitted fields.
            * Returns the final result.
            * No additional tool calls after this.

            ---

            ## Behavior Rules

            * Always follow the strict sequence:

            ```
            Prepare → (Start → [SKIP+LIMIT → Chunk(s) → repeat] → End)+ → Run
            ```
            * All fields listed in `Prepare` must be fully populated before `Run`.
            * Always include `null` explicitly for missing attributes.
            * Only one command per message.

            ---

            ## Example

            ```
            Prepare:investigation_template
            Start:post_context
            Chunk:<first 1 post_context entry from SKIP 0 LIMIT 1>
            Chunk:<next 1 post_context entry from SKIP 1 LIMIT 1>
            End:post_context

            Start:comment_context
            Chunk:<first 20 comment_context entries from SKIP 0 LIMIT 20>
            Chunk:<next 20 comment_context entries from SKIP 20 LIMIT 20>
            End:comment_context

            Run:investigation_template
            ```

            """
    )

