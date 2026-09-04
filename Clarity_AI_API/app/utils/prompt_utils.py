"""Utility functions for generating LLM prompts."""

 

from typing import List, Tuple, Optional

 

def generate_llm_prompt(

    file_contents: List[Tuple[str, bytes]],

    user_question: str,

    chat_history: Optional[List[dict]] = None

) -> str:

    """

    Generate a prompt for an LLM based on file contents, chat history, and user question.

   

    Args:

        file_contents: List of tuples (filename, content) with 1-2 file raw text contents

        user_question: The user's question to be answered

        chat_history: Optional list of previous chat messages in format:

                     [{"user": "...", "agent": "..."}]

   

    Returns:

        Formatted prompt string ready to send to LLM

    """

    # Build the prompt

    prompt_parts = []

   

    # Add system instruction

    prompt_parts.append(

        "You are a helpful AI assistant. Answer the user's question based on the provided file raw text "

        "and conversation history. Be accurate, concise, and cite specific information from the file contents when relevant.\n"

    )

   

    # Add file contents

    prompt_parts.append("=" * 80)

    prompt_parts.append("FILES:")

    prompt_parts.append("=" * 80)

   

    for i, (filename, content) in enumerate(file_contents, 1):

        file_label = f"File {i}: {filename}" if len(file_contents) > 1 else f"File: {filename}"

        prompt_parts.append(f"\n### {file_label}\n")

        # Decode bytes to string if needed

        if isinstance(content, bytes):

            content = content.decode('utf-8', errors='ignore')

        prompt_parts.append(content.strip())

        prompt_parts.append("\n")

   

    prompt_parts.append("=" * 80)

   

    # Add chat history if provided

    if chat_history and len(chat_history) > 0:

        prompt_parts.append("\nCONVERSATION HISTORY:")

        prompt_parts.append("=" * 80)

       

        for msg in chat_history:

            user_msg = msg.get("user", "")

            agent_msg = msg.get("agent", "")

            if user_msg:

                prompt_parts.append(f"\nUser: {user_msg}")

            if agent_msg:

                prompt_parts.append(f"Agent: {agent_msg}")

       

        prompt_parts.append("\n" + "=" * 80)

   

    # Add current user question

    prompt_parts.append("\nCURRENT QUESTION:")

    prompt_parts.append("=" * 80)

    prompt_parts.append(f"\n{user_question}\n")

    prompt_parts.append("=" * 80)

   

    # Add instruction for answer

    multi_file_instruction = ""

    if len(file_contents) > 1:

        multi_file_instruction = (

            "IMPORTANT: Since multiple files are provided, you MUST cite which specific file(s) you are referencing "

            "when providing information (e.g., 'According to File 1: filename.txt...' or 'File 2: filename.txt mentions...'). "

        )

   

    prompt_parts.append(

        f"\nPlease provide a comprehensive answer to the current question based on the file(s) above. "

        f"{multi_file_instruction}"

        f"If the conversation history is relevant, consider it when formulating your response. "

        f"Use the conversation history only to interpret the current question, but do NOT treat it as a factual source unless it is also supported by the file content. "

        f"If the answer cannot be found in the provided files, clearly state that."

    )

   

    return "\n".join(prompt_parts)

 