"""
Gemini API wrapper with tool call interception.
"""

import os
import time
import threading
from typing import List, Dict, Any, Optional, AsyncIterator
from collections import deque
import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse
from src.api.tool_calls import get_filesystem_tools, get_tools_system_instruction
from src.kernel.interceptor import RequestInterceptor, ToolCall


class GeminiWrapper:
    """Wrapper for Gemini API with interception capability."""
    
    def __init__(
        self,
        api_key: Optional[str] = "",
        model_name: str = "gemini-2.5-flash",
        rate_limit: int = 10,
        rate_window: int = 60
    ):
        # Use provided api_key, or environment variable, or default
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        # If still None, use the default value from parameter
        if not self.api_key:
            self.api_key = ""
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name=model_name)
        self.tools = get_filesystem_tools()
        self.interceptor = RequestInterceptor()
        self.conversation_history: List[Dict[str, Any]] = []
        
        # Get system instruction for tools (workaround since tools parameter doesn't work in 0.3.0)
        self.tools_instruction = get_tools_system_instruction()
        
        # Use start_chat for better conversation management
        try:
            self.chat_session = self.model.start_chat(history=[])
        except Exception:
            self.chat_session = None
        
        # Rate limiting
        self.rate_limit = rate_limit  # Max calls per window
        self.rate_window = rate_window  # Window in seconds (default 60 = 1 minute)
        self.api_call_timestamps: deque = deque()  # No maxlen, we'll clean manually
        self.rate_limit_lock = threading.Lock()
    
    def add_to_history(self, role: str, content: str):
        """Add message to conversation history."""
        # For chat sessions, history is managed automatically
        # We keep our own history for generate_content fallback
        # Gemini API expects: [{'role': 'user', 'parts': ['text']}, {'role': 'model', 'parts': ['text']}]
        self.conversation_history.append({
            "role": role,
            "parts": [content]  # parts should be a list of strings
        })
        
        # Also add to chat session history if available
        if self.chat_session and hasattr(self.chat_session, 'history'):
            # Chat session manages its own history, but we can sync if needed
            pass
    
    def inject_refusal_signal(self, refusal_signal: str):
        """Inject a refusal signal into the conversation history."""
        # Inject as assistant's own reasoning (add as model response)
        self.add_to_history("model", refusal_signal)
    
    def inject_human_decision(self, decision_message: str):
        """Inject human decision into conversation history."""
        # Add as user message
        self.add_to_history("user", decision_message)
    
    def _check_rate_limit(self) -> bool:
        """
        Check if we're within rate limit and record the call if allowed.
        Returns True if we can make a call, False if limit exceeded.
        """
        with self.rate_limit_lock:
            current_time = time.time()
            
            # Remove timestamps older than the window
            while self.api_call_timestamps and (current_time - self.api_call_timestamps[0]) > self.rate_window:
                self.api_call_timestamps.popleft()
            
            # Check if we're at the limit
            if len(self.api_call_timestamps) >= self.rate_limit:
                return False
            
            # Record this API call
            self.api_call_timestamps.append(current_time)
            return True
    
    def _wait_for_rate_limit(self):
        """Wait until we can make an API call within rate limits."""
        current_time = time.time()
        
        with self.rate_limit_lock:
            # Remove old timestamps
            while self.api_call_timestamps and (current_time - self.api_call_timestamps[0]) > self.rate_window:
                self.api_call_timestamps.popleft()
            
            if len(self.api_call_timestamps) >= self.rate_limit:
                # Calculate wait time until oldest call expires
                oldest_timestamp = self.api_call_timestamps[0]
                wait_time = self.rate_window - (current_time - oldest_timestamp) + 0.1  # Small buffer
            else:
                wait_time = 0
        
        if wait_time > 0:
            time.sleep(wait_time)
    
    def generate_response(
        self,
        user_message: Optional[str] = None,
        intercept_callback: Optional[callable] = None
    ) -> GenerateContentResponse:
        """Generate response with tool call interception."""
        # Check and enforce rate limit
        if not self._check_rate_limit():
            # Wait until we can make the call
            self._wait_for_rate_limit()
            # Try again after waiting
            if not self._check_rate_limit():
                raise RuntimeError(
                    f"Rate limit exceeded: {self.rate_limit} calls per {self.rate_window} seconds. "
                    f"Please wait before making another API call."
                )
        
        # Generate response
        # Note: google-generativeai 0.3.0 doesn't support tools parameter properly
        # We'll use a workaround: inject tool descriptions in the prompt and parse JSON responses
        response = None
        
        # Get the user message
        message_content = None
        
        if user_message:
            message_content = user_message
            # Add tools instruction to first message only
            if len(self.conversation_history) == 0:
                # Prepend tools instruction to help model understand available tools
                enhanced_message = f"{self.tools_instruction}\n\nUser request: {message_content}"
                message_content = enhanced_message
            # Add user message to history (original, not enhanced)
            self.add_to_history("user", user_message)
        elif self.conversation_history:
            # For continuation (after tool calls), use a continuation prompt
            # Check if last message was a function response or tool result
            last_msg = self.conversation_history[-1]
            if isinstance(last_msg, dict):
                role = last_msg.get("role", "")
                if role == "function" or "Tool" in str(last_msg.get("parts", [])):
                    # After function call, ask for final response
                    message_content = "Please provide a final response to the user based on the tool execution results."
                    self.add_to_history("user", message_content)
                elif role == "user":
                    # Get last user message from history
                    parts = last_msg.get("parts", [])
                    if parts and isinstance(parts[0], str):
                        message_content = parts[0]
                    else:
                        message_content = "Please continue."
                        self.add_to_history("user", message_content)
                else:
                    # Last message was model response, add continuation
                    message_content = "Please continue with your response."
                    self.add_to_history("user", message_content)
            else:
                message_content = "Please continue."
                self.add_to_history("user", message_content)
        else:
            # No history and no message - this shouldn't happen, but provide a default
            message_content = "Please respond."
            self.add_to_history("user", message_content)
        
        # Use chat session if available
        # Note: chat_session might not work well with our tool calling workaround
        # So we'll primarily use generate_content
        if False and self.chat_session and message_content:
            try:
                response = self.chat_session.send_message(message_content)
            except Exception as e:
                print(f"Warning: Error with chat session: {e}")
                response = None
        
        # Fallback to generate_content
        if not response:
            # Build contents for generate_content
            contents = []
            
            # Convert conversation history to the format expected by generate_content
            # Note: Gemini API expects parts to be strings, not dicts
            for msg in self.conversation_history:
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    parts = msg.get("parts", [])
                    if parts:
                        # Extract text from parts - all parts must be strings
                        text_parts = []
                        for part in parts:
                            if isinstance(part, str):
                                text_parts.append(part)
                            elif isinstance(part, dict):
                                # Handle function responses or other dict parts
                                if "text" in part:
                                    text_parts.append(part["text"])
                                elif "function_response" in part:
                                    # Convert function_response to text format
                                    func_resp = part["function_response"]
                                    if isinstance(func_resp, dict):
                                        name = func_resp.get("name", "unknown")
                                        response = func_resp.get("response", {})
                                        if isinstance(response, dict):
                                            if response.get("success"):
                                                content = response.get("content") or response.get("message") or "Success"
                                                text_parts.append(f"Tool '{name}' executed successfully. Result: {content}")
                                            else:
                                                error = response.get("error") or response.get("message") or "Error"
                                                text_parts.append(f"Tool '{name}' error: {error}")
                                        else:
                                            text_parts.append(f"Tool '{name}' result: {response}")
                                    else:
                                        text_parts.append(f"Tool result: {func_resp}")
                                else:
                                    # Other dict format - convert to string
                                    text_parts.append(str(part))
                        
                        # Only add if we have valid text parts
                        if text_parts and all(isinstance(p, str) for p in text_parts):
                            contents.append({"role": role, "parts": text_parts})
            
            # Always ensure we have message_content
            if not message_content:
                # If no message_content, try to get it from the last user message in history
                if self.conversation_history:
                    last_msg = self.conversation_history[-1]
                    if isinstance(last_msg, dict) and last_msg.get("role") == "user":
                        parts = last_msg.get("parts", [])
                        if parts and isinstance(parts[0], str):
                            message_content = parts[0]
                        else:
                            message_content = "Please continue."
                    else:
                        message_content = "Please continue."
                else:
                    message_content = "Please respond."
            
            # If we have message_content but no contents from history, add it
            if not contents:
                # No contents from history, use message_content
                contents = [{"role": "user", "parts": [message_content]}]
            elif message_content:
                # We have contents from history, check if we need to add message_content
                # Only add if it's different from the last message
                last_content = contents[-1] if contents else None
                if not last_content or last_content.get("parts", []) != [message_content]:
                    contents.append({"role": "user", "parts": [message_content]})
            
            # Final check: ensure we have content to send
            # Also validate that all parts are strings
            valid_contents = []
            for msg in contents:
                if isinstance(msg, dict) and "role" in msg and "parts" in msg:
                    parts = msg["parts"]
                    # Ensure all parts are strings
                    string_parts = [p for p in parts if isinstance(p, str)]
                    if string_parts:
                        valid_contents.append({"role": msg["role"], "parts": string_parts})
            
            if not valid_contents:
                # Last resort: create a default message
                valid_contents = [{"role": "user", "parts": ["Please respond to the user's request."]}]
            
            contents = valid_contents
            
            try:
                response = self.model.generate_content(contents=contents)
            except Exception as e:
                raise RuntimeError(f"Failed to generate response: {str(e)}")
        
        # Check for tool calls in response
        # Since tools parameter doesn't work in 0.3.0, we parse the response text for JSON tool calls
        tool_calls_found = []
        
        # First, try to parse JSON tool calls from response text
        response_text = None
        try:
            if hasattr(response, 'text'):
                response_text = response.text
        except Exception:
            pass
        
        if response_text:
            # Parse for JSON tool call format: {"tool_call": "function_name", "parameters": {...}}
            import json
            import re
            # Look for JSON tool calls in the response
            # Improved pattern to handle nested JSON in parameters
            matches = []
            
            # Method 1: Try to find complete JSON objects with tool_call
            # Match from first { to matching }
            brace_count = 0
            start_idx = -1
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        json_str = response_text[start_idx:i+1]
                        try:
                            data = json.loads(json_str)
                            if "tool_call" in data and "parameters" in data:
                                matches.append(json_str)
                        except json.JSONDecodeError:
                            pass
                        start_idx = -1
            
            # Method 2: Try regex pattern as fallback
            if not matches:
                json_pattern = r'\{\s*"tool_call"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{[^}]*\}\s*\}'
                regex_matches = re.findall(json_pattern, response_text, re.DOTALL)
                for match in regex_matches:
                    try:
                        data = json.loads(match)
                        if "tool_call" in data and "parameters" in data:
                            matches.append(match)
                    except json.JSONDecodeError:
                        continue
            
            for match in matches:
                try:
                    tool_data = json.loads(match)
                    if "tool_call" in tool_data and "parameters" in tool_data:
                        func_name = tool_data["tool_call"]
                        func_args = tool_data["parameters"]
                        
                        # Filter out empty tool calls
                        if not func_name or not func_name.strip():
                            continue
                        
                        # Filter out empty parameters
                        if not func_args or (isinstance(func_args, dict) and not func_args):
                            continue
                        
                        tool_call = self.interceptor.intercept_tool_call(
                            function_name=func_name,
                            parameters=func_args,
                            context={"user_message": user_message or "tool_call", "parsed_from_text": True}
                        )
                        tool_calls_found.append(tool_call)
                        
                        # Call interception callback if provided
                        if intercept_callback:
                            try:
                                result = intercept_callback(tool_call)
                                
                                # Skip empty results (from filtered tool calls)
                                if result and result.get("skip"):
                                    continue
                                
                                if result:
                                    # Add function response to history for next turn
                                    # Format as function response that model can understand
                                    if isinstance(result, dict):
                                        if result.get("success"):
                                            result_text = result.get("content") or result.get("message") or str(result)
                                        else:
                                            result_text = f"Error: {result.get('error', 'Unknown error')}"
                                    else:
                                        result_text = str(result)
                                    
                                    # Add as user message so model can see the result in next turn
                                    # Format it clearly so model understands it's a tool result
                                    # Always add as text string (not function_response dict) for compatibility
                                    if isinstance(result, dict):
                                        if result.get("success"):
                                            # Successful execution
                                            content = result.get("content") or result.get("message") or result_text
                                            self.add_to_history("user", f"Tool '{func_name}' executed successfully. Result: {content}")
                                        else:
                                            # Error result
                                            error_msg = result.get("error") or result.get("message") or result_text
                                            self.add_to_history("user", f"Tool '{func_name}' error: {error_msg}")
                                    else:
                                        # Other result type
                                        self.add_to_history("user", f"Tool '{func_name}' result: {result_text}")
                            except Exception as e:
                                error_text = f"Tool '{func_name}' execution failed: {str(e)}"
                                self.add_to_history("user", error_text)
                except (json.JSONDecodeError, KeyError) as e:
                    continue
        
        # Also check for native function_calls (if API supports it)
        try:
            # Check for function_calls attribute directly on response
            if hasattr(response, 'function_calls') and response.function_calls:
                for function_call in response.function_calls:
                    try:
                        # Extract function name and args
                        func_name = function_call.name if hasattr(function_call, 'name') else str(function_call)
                        func_args = {}
                        if hasattr(function_call, 'args'):
                            if isinstance(function_call.args, dict):
                                func_args = function_call.args
                            elif hasattr(function_call.args, '__dict__'):
                                func_args = function_call.args.__dict__
                        
                        tool_call = self.interceptor.intercept_tool_call(
                            function_name=func_name,
                            parameters=func_args,
                            context={"user_message": user_message or "tool_call"}
                        )
                        tool_calls_found.append(tool_call)
                        
                        # Call interception callback if provided
                        if intercept_callback:
                            try:
                                result = intercept_callback(tool_call)
                                # Skip empty results (from filtered tool calls)
                                if result and result.get("skip"):
                                    continue
                                
                                # Add function response to history as text (not function_response dict)
                                # The API doesn't support function_response format in 0.3.0
                                if result:
                                    if isinstance(result, dict):
                                        if result.get("success"):
                                            content = result.get("content") or result.get("message") or str(result)
                                            self.add_to_history("user", f"Tool '{func_name}' executed successfully. Result: {content}")
                                        else:
                                            error_msg = result.get("error") or result.get("message") or str(result)
                                            self.add_to_history("user", f"Tool '{func_name}' error: {error_msg}")
                                    else:
                                        self.add_to_history("user", f"Tool '{func_name}' result: {result}")
                            except Exception as e:
                                # If callback fails, add error to history as text
                                self.add_to_history("user", f"Tool '{func_name}' execution failed: {str(e)}")
                    except Exception as e:
                        print(f"Warning: Error processing function call: {e}")
                        import traceback
                        traceback.print_exc()
            
            # Also check candidates structure (fallback)
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                    for part in parts:
                        # Check for function_call attribute
                        if hasattr(part, 'function_call'):
                            function_call = part.function_call
                            try:
                                func_name = function_call.name if hasattr(function_call, 'name') else str(function_call)
                                func_args = {}
                                if hasattr(function_call, 'args'):
                                    if isinstance(function_call.args, dict):
                                        func_args = function_call.args
                                    elif hasattr(function_call.args, '__dict__'):
                                        func_args = function_call.args.__dict__
                                
                                tool_call = self.interceptor.intercept_tool_call(
                                    function_name=func_name,
                                    parameters=func_args,
                                    context={"user_message": user_message or "tool_call"}
                                )
                                tool_calls_found.append(tool_call)
                                
                                # Call interception callback if provided
                                if intercept_callback:
                                    try:
                                        result = intercept_callback(tool_call)
                                        # Skip empty results (from filtered tool calls)
                                        if result and result.get("skip"):
                                            continue
                                        
                                        # Add function response to history as text (not function_response dict)
                                        if result:
                                            if isinstance(result, dict):
                                                if result.get("success"):
                                                    content = result.get("content") or result.get("message") or str(result)
                                                    self.add_to_history("user", f"Tool '{func_name}' executed successfully. Result: {content}")
                                                else:
                                                    error_msg = result.get("error") or result.get("message") or str(result)
                                                    self.add_to_history("user", f"Tool '{func_name}' error: {error_msg}")
                                            else:
                                                self.add_to_history("user", f"Tool '{func_name}' result: {result}")
                                    except Exception as e:
                                        # If callback fails, add error to history as text
                                        self.add_to_history("user", f"Tool '{func_name}' execution failed: {str(e)}")
                            except Exception as e:
                                print(f"Warning: Error processing function call from part: {e}")
                                import traceback
                                traceback.print_exc()
        except Exception as e:
            # Log error but continue
            print(f"Warning: Error processing tool calls: {e}")
            import traceback
            traceback.print_exc()
        
        # Add response text to history if available
        try:
            # Try to get text from response
            response_text = None
            if hasattr(response, 'text'):
                try:
                    response_text = response.text
                except Exception as e:
                    # text might be a property that raises an error
                    print(f"Warning: Error accessing response.text: {e}")
            
            # If no text attribute, try to extract from candidates
            if not response_text and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                    text_parts = []
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        response_text = ' '.join(text_parts)
            
            if response_text:
                # Add model response to history
                self.add_to_history("model", response_text)
        except Exception as e:
            print(f"Warning: Error adding response to history: {e}")
            import traceback
            traceback.print_exc()
        
        return response
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get full conversation history."""
        return self.conversation_history.copy()
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
        self.interceptor.clear_history()
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        with self.rate_limit_lock:
            current_time = time.time()
            # Remove old timestamps
            while self.api_call_timestamps and (current_time - self.api_call_timestamps[0]) > self.rate_window:
                self.api_call_timestamps.popleft()
            
            calls_in_window = len(self.api_call_timestamps)
            remaining_calls = max(0, self.rate_limit - calls_in_window)
            
            if self.api_call_timestamps:
                oldest_timestamp = self.api_call_timestamps[0]
                time_until_reset = max(0, self.rate_window - (current_time - oldest_timestamp))
            else:
                time_until_reset = 0
            
            return {
                "rate_limit": self.rate_limit,
                "rate_window_seconds": self.rate_window,
                "calls_in_window": calls_in_window,
                "remaining_calls": remaining_calls,
                "time_until_reset_seconds": time_until_reset
            }
