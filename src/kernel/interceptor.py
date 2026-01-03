"""
Request interceptor for capturing tool calls.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ToolCall:
    """Represents a tool call request."""
    function_name: str
    parameters: Dict[str, Any]
    context: Dict[str, Any]
    timestamp: datetime
    call_id: str


class RequestInterceptor:
    """Intercepts and parses tool calls before execution."""
    
    def __init__(self):
        self.call_history: List[ToolCall] = []
        self.pending_calls: Dict[str, ToolCall] = {}
    
    def intercept_tool_call(
        self,
        function_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolCall:
        """Intercept and parse a tool call."""
        call_id = f"{function_name}_{datetime.utcnow().timestamp()}"
        
        tool_call = ToolCall(
            function_name=function_name,
            parameters=parameters,
            context=context or {},
            timestamp=datetime.utcnow(),
            call_id=call_id
        )
        
        self.call_history.append(tool_call)
        self.pending_calls[call_id] = tool_call
        
        return tool_call
    
    def extract_operation_info(self, tool_call: ToolCall) -> Dict[str, Any]:
        """Extract operation information from tool call."""
        # Map function names to operations
        operation_map = {
            "read_file": "read",
            "write_file": "write",
            "delete_file": "delete",
            "list_directory": "list",
            "execute_command": "execute",
        }
        
        operation = operation_map.get(tool_call.function_name, tool_call.function_name)
        target = tool_call.parameters.get("path") or tool_call.parameters.get("file_path") or tool_call.parameters.get("target")
        
        return {
            "operation": operation,
            "target": target,
            "parameters": tool_call.parameters,
            "function_name": tool_call.function_name
        }
    
    def get_recent_calls(self, count: int = 10) -> List[ToolCall]:
        """Get recent tool calls."""
        return self.call_history[-count:] if len(self.call_history) > count else self.call_history
    
    def clear_history(self):
        """Clear call history."""
        self.call_history.clear()
        self.pending_calls.clear()
