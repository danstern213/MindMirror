import tiktoken
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def count_tokens(messages: List[Dict[str, Any]], model: str = "gpt-4o") -> int:
    """
    Count the number of tokens in a list of messages.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content' keys
        model: The model to count tokens for (default: "gpt-4o")
        
    Returns:
        int: The total number of tokens
    """
    try:
        # Handle known model name variations
        model_for_encoding = model.lower()
        
        # Map OpenAI model names to tiktoken model names
        if "gpt-5" in model_for_encoding or "chatgpt-5" in model_for_encoding:
            # GPT-5 models - try o200k_base first, fall back to cl100k_base if not available
            # Note: o200k_base may not be available in all tiktoken versions
            try:
                encoding = tiktoken.get_encoding("o200k_base")
                logger.debug(f"Using o200k_base encoding for model {model}")
            except (KeyError, ValueError):
                # Fall back to cl100k_base if o200k_base is not available
                encoding = tiktoken.get_encoding("cl100k_base")
                logger.debug(f"o200k_base not available, using cl100k_base encoding for model {model}")
        elif "chatgpt-4" in model_for_encoding or "gpt-4" in model_for_encoding:
            model_for_encoding = "gpt-4"
            encoding = tiktoken.encoding_for_model(model_for_encoding)
        elif "gpt-3.5" in model_for_encoding:
            model_for_encoding = "gpt-3.5-turbo"
            encoding = tiktoken.encoding_for_model(model_for_encoding)
        else:
            # Try to get encoding for the model directly
            encoding = tiktoken.encoding_for_model(model_for_encoding)
    except (KeyError, ValueError):
        # For unknown models, try o200k_base (common for newer models) then fall back to cl100k_base
        try:
            encoding = tiktoken.get_encoding("o200k_base")
            logger.debug(f"Model {model} not found in tiktoken registry. Using o200k_base encoding.")
        except (KeyError, ValueError):
            # Final fallback to cl100k_base
            encoding = tiktoken.get_encoding("cl100k_base")
            logger.debug(f"Model {model} not found in tiktoken registry. Using cl100k_base encoding.")
    
    num_tokens = 0
    for message in messages:
        # Every message follows {role: content} format
        num_tokens += 4  # Every message starts with a fixed token overhead
        for key, value in message.items():
            if key == "name":  # If there's a name, the role is omitted
                num_tokens -= 1  # Role is always needed and minimal, so subtract 1
            num_tokens += len(encoding.encode(str(value)))
    
    num_tokens += 2  # Every reply is primed with <im_start>assistant
    
    # Add a 5% safety margin to account for potential discrepancies between tiktoken and OpenAI's server-side counting
    # This helps prevent unexpected limit exceeding
    adjusted_tokens = int(num_tokens * 1.05)
    
    if adjusted_tokens != num_tokens:
        logger.debug(f"Token count adjusted from {num_tokens} to {adjusted_tokens} (5% safety margin)")
    
    return adjusted_tokens

def truncate_messages_to_fit_limit(
    messages: List[Dict[str, Any]], 
    model: str = "gpt-4o",
    max_tokens: int = 28500,  # More conservative limit with larger safety margin (~5%)
    preserve_system_message: bool = True,
    preserve_last_user_message: bool = True
) -> List[Dict[str, Any]]:
    """
    Truncate messages to fit within token limit.
    
    Strategy:
    1. Always preserve system message if requested
    2. Always preserve most recent user message if requested
    3. Remove older messages from the middle until under the limit
    
    Args:
        messages: List of message dictionaries
        model: Model to count tokens for
        max_tokens: Maximum allowed tokens
        preserve_system_message: Whether to preserve the system message
        preserve_last_user_message: Whether to preserve the most recent user message
        
    Returns:
        List[Dict[str, Any]]: Truncated message list
    """
    # Check current token count
    current_tokens = count_tokens(messages, model)
    
    # If we're already under the limit, return as is
    if current_tokens <= max_tokens:
        return messages
    
    logger.warning(
        f"Message token count ({current_tokens}) exceeds limit ({max_tokens}). "
        f"Truncating to fit within limit."
    )
    
    # Make a copy to avoid modifying the original
    truncated_messages = messages.copy()
    
    # If we need to preserve system message and it exists
    system_message = None
    if preserve_system_message and truncated_messages and truncated_messages[0]["role"] == "system":
        system_message = truncated_messages.pop(0)
    
    # If we need to preserve last user message and it exists
    last_user_message = None
    if preserve_last_user_message:
        # Find the last user message
        for i in range(len(truncated_messages) - 1, -1, -1):
            if truncated_messages[i]["role"] == "user":
                last_user_message = truncated_messages.pop(i)
                break
    
    # Now we have messages with system and last user removed (if they existed and needed preservation)
    # Sort remaining messages by importance (older messages are less important)
    remaining_messages = truncated_messages
    
    # Re-add system message if we preserved it
    result = []
    if system_message:
        result.append(system_message)
    
    # Keep adding messages until we hit the token limit
    current_tokens = count_tokens(result, model)
    token_budget = max_tokens - current_tokens
    
    # If we need to preserve last user message, reserve tokens for it
    if last_user_message:
        last_user_tokens = count_tokens([last_user_message], model)
        token_budget -= last_user_tokens
    
    # Add as many remaining messages as will fit in the budget
    # Starting from the most recent
    for message in reversed(remaining_messages):
        message_tokens = count_tokens([message], model)
        if message_tokens <= token_budget:
            result.append(message)
            token_budget -= message_tokens
        else:
            # If can't fit the whole message, skip it
            logger.debug(f"Skipping message to fit token budget: {message['role'][:10]}...")
    
    # Add the last user message if we preserved it
    if last_user_message:
        result.append(last_user_message)
    
    # Verify the final token count
    final_tokens = count_tokens(result, model)
    logger.info(f"Truncated message count from {current_tokens} to {final_tokens} tokens")
    
    return result 