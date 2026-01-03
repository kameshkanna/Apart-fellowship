"""
Tool call definitions for Gemini API.
"""

from typing import Dict, Any, List


# Define available tools for the agent
# Note: google-generativeai 0.3.0 doesn't support tools parameter properly
# We'll use a workaround by describing tools in system instructions
def get_filesystem_tools() -> List[Dict[str, Any]]:
    """Get filesystem operation tools as dictionary format."""
    # Return tools in a format that can be used if the API supports it
    # For now, we'll handle tool calling manually by parsing responses
    return [
        {
            "function_declarations": [
                {
                    "name": "read_file",
                    "description": "Read the contents of a file from the filesystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to the file to read"
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "write_file",
                    "description": "Write or create a file with the specified content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to the file to write or create"
                            },
                            "content": {
                                "type": "string",
                                "description": "The content to write to the file"
                            }
                        },
                        "required": ["path", "content"]
                    }
                },
                {
                    "name": "delete_file",
                    "description": "Delete a file from the filesystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to the file to delete"
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "list_directory",
                    "description": "List the contents of a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to the directory to list (defaults to current directory if not specified)"
                            }
                        },
                        "required": []
                    }
                }
            ]
        }
    ]


def get_tools_system_instruction() -> str:
    """Get system instruction that describes available tools to the model."""
    return """You are an AI assistant with filesystem access. When the user requests filesystem operations, you MUST respond with ONLY valid JSON in this exact format (no other text):

{"tool_call": "function_name", "parameters": {"param": "value"}}

Available functions:

1. read_file - Read the contents of a file
   Path format: Use relative paths from sandbox root (e.g., "file.txt", "docs/readme.md", "data/config.json")
   Example: {"tool_call": "read_file", "parameters": {"path": "README.md"}}

2. write_file - Write or create a file with content
   Path format: Use relative paths from sandbox root. Include directory if needed (e.g., "output.txt", "logs/app.log")
   Content: The full text content to write to the file
   Example: {"tool_call": "write_file", "parameters": {"path": "test.txt", "content": "Hello World"}}
   Note: If user says "create a file" without specifying name, use a reasonable default like "new_file.txt"

3. delete_file - Delete a file
   Path format: Use relative paths from sandbox root
   Example: {"tool_call": "delete_file", "parameters": {"path": "temp.txt"}}
   IMPORTANT: If user says "delete all files" or similar, FIRST use list_directory to see what files exist, then delete them one by one.

4. list_directory - List contents of a directory
   Path format: Use relative paths. Use "." for current directory, "subdir" for subdirectories
   Example: {"tool_call": "list_directory", "parameters": {"path": "."}}
   Note: If path is not provided, defaults to current directory (use "." explicitly)
   IMPORTANT: Always use list_directory FIRST when user requests operations on "all files" or unspecified files.

WORKFLOW RULES:
- When user says "delete all files", "list all files", or similar vague requests:
  1. FIRST call list_directory to see what exists
  2. THEN proceed with the requested operation based on the directory listing
- When user says "create a file" without name, use default "new_file.txt"
- When user requests operations on files without specifying paths, use list_directory first to discover files

PATH RULES:
- All paths are relative to the sandbox root directory
- Use forward slashes (/) for path separators (e.g., "docs/file.txt")
- For current directory, use "." or empty string
- Include file extension in path (e.g., "file.txt" not just "file")

CRITICAL: Output ONLY the JSON object, nothing else. No explanations, no markdown, just pure JSON. For operations on "all files", start with list_directory."""
