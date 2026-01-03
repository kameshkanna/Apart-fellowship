"""
Main kernel orchestrator that coordinates all components.
"""

from typing import Dict, Any, Optional, Callable
from src.kernel.config import KernelConfig, load_config
from src.kernel.interceptor import RequestInterceptor, ToolCall
from src.kernel.risk_engine import RiskEngine
from src.kernel.execution_history import ExecutionHistoryTracker
from src.kernel.attack_detector import AttackDetector
from src.kernel.refusal_generator import RefusalGenerator
from src.kernel.router import ExecutionRouter
from src.kernel.human_intervention import HumanInterventionHandler, InterventionRequest, InterventionDecision
from src.sandbox.protection import ProtectionManager
from src.sandbox.filesystem import SandboxFilesystem
from src.sandbox.logger import ExecutionLogger
from src.api.gemini_wrapper import GeminiWrapper


class ResilientPermissionKernel:
    """Main kernel orchestrator."""
    
    def __init__(self, config_path: str = "config/kernel_config.yaml", api_key: Optional[str] = None):
        # Load configuration
        self.config = load_config(config_path)
        
        # Initialize components
        self.protection_manager = ProtectionManager(self.config.protected_resources)
        self.sandbox = SandboxFilesystem(self.config.sandbox, self.protection_manager)
        self.logger = ExecutionLogger(self.config.execution_history, self.config.sandbox.logs_path)
        self.history_tracker = ExecutionHistoryTracker(self.config.execution_history, self.logger)
        
        self.risk_engine = RiskEngine(self.protection_manager)
        self.attack_detector = AttackDetector(self.config.attack_patterns, self.history_tracker)
        self.refusal_generator = RefusalGenerator(self.config.refusal_templates)
        self.human_intervention = HumanInterventionHandler(self.config.human_intervention)
        
        self.router = ExecutionRouter(
            risk_engine=self.risk_engine,
            history_tracker=self.history_tracker,
            attack_detector=self.attack_detector,
            refusal_generator=self.refusal_generator,
            human_intervention=self.human_intervention
        )
        
        # Initialize Gemini wrapper with rate limiting (10 calls per minute)
        self.gemini = GeminiWrapper(
            api_key=api_key,
            rate_limit=10,  # 10 calls per minute
            rate_window=60  # 60 seconds = 1 minute
        )
        
        # Note: Tool calls are intercepted via JSON parsing in the wrapper
        # The callback is set up in the wrapper's generate_response method
    
    def _handle_tool_call(self, tool_call: ToolCall) -> Dict[str, Any]:
        """Handle intercepted tool call."""
        # Filter out empty/malformed tool calls
        if not tool_call.function_name or not tool_call.function_name.strip():
            print(f"\n[WARNING] Empty tool call detected, ignoring...")
            return {"error": "Empty tool call", "skip": True}
        
        # Extract operation info
        operation_info = self.gemini.interceptor.extract_operation_info(tool_call)
        operation = operation_info["operation"]
        target = operation_info["target"]
        parameters = operation_info["parameters"]
        
        # Filter out empty operations
        if not operation or not operation.strip():
            print(f"\n[WARNING] Empty operation detected, ignoring...")
            return {"error": "Empty operation", "skip": True}
        
        # Print agent reasoning and action
        print(f"\n[AGENT REASONING]")
        print(f"  Tool Call: {tool_call.function_name}")
        print(f"  Operation: {operation}")
        print(f"  Target: {target}")
        if parameters:
            print(f"  Parameters: {parameters}")
        
        # Route operation
        # Convert ToolCall to dict for serialization (avoid passing non-serializable objects)
        tool_call_dict = {
            "function_name": tool_call.function_name,
            "parameters": tool_call.parameters,
            "context": tool_call.context,
            "timestamp": tool_call.timestamp.isoformat(),
            "call_id": tool_call.call_id
        }
        
        # Create serializable context (avoid passing large conversation history)
        serializable_context = {
            "tool_call": tool_call_dict,
            "function_name": tool_call.function_name,
            "parameters": parameters
        }
        
        should_execute, refusal_signal, intervention_request, metadata = self.router.route_operation(
            operation=operation,
            target=target,
            parameters=parameters,
            context=serializable_context
        )
        
        # Print safety assessment
        safety_assessment = metadata.get("safety_assessment", {})
        safety_level = safety_assessment.get("level", "unknown")
        safety_reason = safety_assessment.get("reason", "No reason provided")
        
        print(f"\n[SAFETY ASSESSMENT]")
        print(f"  Level: {safety_level.upper()}")
        print(f"  Reason: {safety_reason}")
        
        if metadata.get("attack_detected"):
            print(f"  ⚠️  ATTACK DETECTED: {metadata.get('attack_pattern')} (confidence: {metadata.get('attack_confidence', 0):.2f})")
        
        routing_decision = metadata.get("routing_decision", "unknown")
        print(f"  Routing Decision: {routing_decision.upper()}")
        
        if should_execute:
            # Execute operation in sandbox
            print(f"\n[ACTION] Executing {operation} on {target}...")
            # Note: Operation is already logged by the router before execution
            result = self._execute_operation(operation, target, parameters)
            if result.get("success"):
                print(f"  ✓ Success: {result.get('message', 'Operation completed')}")
                # Mark that this was a successful safe operation - signal to stop looping
                result["_safe_execution_complete"] = True
            else:
                print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
            return result
        
        elif intervention_request:
            # Handle human intervention
            print(f"\n[ACTION] ⛔ HUMAN INTERVENTION REQUIRED")
            print(f"  Operation: {operation} on {target}")
            print(f"  Risk Analysis: {intervention_request.risk_analysis}")
            
            if intervention_request.decision == InterventionDecision.PENDING:
                # For CLI, we'll auto-reject for safety (in production, would wait)
                intervention_request.decision = InterventionDecision.REJECT
                intervention_request.human_feedback = "Operation blocked: requires human approval"
            
            if intervention_request.decision == InterventionDecision.APPROVE:
                # Execute after approval
                print(f"  ✓ Approved - Executing operation...")
                result = self._execute_operation(operation, target, parameters)
                decision_msg = self.human_intervention.get_decision_message(intervention_request)
                self.gemini.inject_human_decision(decision_msg)
                return result
            else:
                # Rejected or modified
                print(f"  ✗ REJECTED - Operation blocked")
                decision_msg = self.human_intervention.get_decision_message(intervention_request)
                self.gemini.inject_human_decision(decision_msg)
                return {"error": "Operation rejected by human intervention", "message": decision_msg}
        
        elif refusal_signal:
            # Inject refusal signal for resampling (only for NOT_COMPLETELY_SAFE operations)
            print(f"\n[ACTION] 🔄 RESAMPLING TRIGGERED")
            print(f"  Refusal Signal: {refusal_signal}")
            print(f"  Agent will self-correct and try alternative approach...")
            self.gemini.inject_refusal_signal(refusal_signal)
            # Don't mark as complete - allow resampling to continue
            return {"error": "Operation not completely safe", "refusal_signal": refusal_signal, "message": refusal_signal, "_resample": True}
        
        print(f"\n[ACTION] ✗ Operation blocked (unknown reason)")
        return {"error": "Operation blocked"}
    
    def _execute_operation(self, operation: str, target: Optional[str], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute operation in sandbox."""
        try:
            if operation == "read":
                content = self.sandbox.read_file(target)
                return {"success": True, "content": content}
            
            elif operation == "write":
                content = parameters.get("content", "")
                self.sandbox.write_file(target, content)
                return {"success": True, "message": f"File {target} written successfully"}
            
            elif operation == "delete":
                self.sandbox.delete_file(target)
                return {"success": True, "message": f"File {target} deleted successfully"}
            
            elif operation == "list":
                items = self.sandbox.list_directory(target or ".")
                return {"success": True, "items": items}
            
            else:
                return {"error": f"Unknown operation: {operation}"}
        
        except PermissionError as e:
            return {"error": str(e)}
        except FileNotFoundError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}
    
    def process_user_message(self, user_message: str) -> str:
        """Process a user message through the kernel."""
        max_iterations = 5  # Prevent infinite loops
        iteration = 0
        
        print(f"\n{'='*60}")
        print(f"PROCESSING REQUEST: {user_message}")
        print(f"{'='*60}")
        
        try:
            while iteration < max_iterations:
                iteration += 1
                print(f"\n[LOOP] Iteration {iteration}/{max_iterations}")
                print(f"  Status: Processing...")
                
                try:
                    # Track if a safe operation was executed successfully
                    safe_execution_complete = False
                    
                    # Create a wrapper callback that tracks safe execution
                    def tool_call_handler(tool_call):
                        nonlocal safe_execution_complete
                        result = self._handle_tool_call(tool_call)
                        # Check if this was a successful safe operation
                        if result and result.get("_safe_execution_complete"):
                            safe_execution_complete = True
                        return result
                    
                    # Generate response with tool call interception
                    # The intercept_callback will be called for any parsed tool calls
                    response = self.gemini.generate_response(
                        user_message=user_message if iteration == 1 else None,
                        intercept_callback=tool_call_handler  # This handles tool calls parsed from JSON
                    )
                    
                    # If a safe operation completed successfully, get final response and return
                    if safe_execution_complete:
                        # Generate one more response to get the final answer from the model
                        print(f"\n[LOOP] Safe operation completed, getting final response...")
                        
                        # Create a callback that filters out any tool calls (shouldn't happen, but safety)
                        def no_tool_calls_handler(tool_call):
                            print(f"\n[WARNING] Unexpected tool call after safe execution, ignoring...")
                            return {"skip": True}
                        
                        final_response = self.gemini.generate_response(
                            user_message=None,  # Continue conversation
                            intercept_callback=no_tool_calls_handler  # Filter any tool calls
                        )
                        # Extract text from final response
                        if final_response:
                            text = None
                            try:
                                if hasattr(final_response, 'text'):
                                    text = final_response.text
                            except Exception:
                                pass
                            
                            if not text and hasattr(final_response, 'candidates') and final_response.candidates:
                                candidate = final_response.candidates[0]
                                if hasattr(candidate, 'content') and candidate.content:
                                    parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                                    text_parts = []
                                    for part in parts:
                                        if hasattr(part, 'text') and part.text:
                                            text_parts.append(part.text)
                                    if text_parts:
                                        text = ' '.join(text_parts)
                            
                            if text:
                                # Filter out tool call JSON if present
                                import re
                                json_match = re.search(r'\{[^{}]*"tool_call"[^{}]*\}', text)
                                if json_match:
                                    # Remove tool call JSON from response
                                    text = text.replace(json_match.group(0), "").strip()
                                
                                if text:
                                    print(f"\n[LOOP] Final response received")
                                    print(f"{'='*60}\n")
                                    return text
                            
                        # Fallback: return success message
                        result_msg = "Operation completed successfully."
                        print(f"\n[LOOP] Final response received")
                        print(f"{'='*60}\n")
                        return result_msg
                    
                    # Check if tool calls were made (they're handled in the callback)
                    # If we have text response and no tool calls pending, return it
                    if response:
                        text = None
                        try:
                            if hasattr(response, 'text'):
                                text = response.text
                        except Exception:
                            # text might be a property that raises an error
                            pass
                        
                        # If no text attribute, try to extract from candidates
                        if not text and hasattr(response, 'candidates') and response.candidates:
                            candidate = response.candidates[0]
                            if hasattr(candidate, 'content') and candidate.content:
                                parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                                text_parts = []
                                for part in parts:
                                    if hasattr(part, 'text') and part.text:
                                        text_parts.append(part.text)
                                if text_parts:
                                    text = ' '.join(text_parts)
                        
                        # Return text response
                        # Tool calls are handled in the wrapper's intercept_callback
                        # If a tool call was made, the wrapper will add the result to history
                        # and we'll get a final response in the next iteration
                        if text:
                            # Check if this looks like a tool call JSON
                            import json
                            import re
                            # Look for JSON tool call pattern
                            json_match = re.search(r'\{[^{}]*"tool_call"[^{}]*\}', text)
                            if json_match:
                                # Tool call JSON detected - wrapper should have processed it
                                print(f"\n[LOOP] Tool call detected in response, continuing to next iteration...")
                                continue
                            else:
                                # Regular text response - return it
                                print(f"\n[LOOP] Final response received")
                                print(f"{'='*60}\n")
                                return text
                    
                    # If tool calls were made, continue conversation to get final response
                    # (iteration is already incremented at the start of the loop)
                except AttributeError as e:
                    error_msg = str(e) if str(e) else repr(e)
                    return f"Error: Response object missing expected attribute. {error_msg}"
                except Exception as e:
                    error_msg = str(e) if str(e) else repr(e)
                    # Only print full traceback in debug mode
                    import traceback
                    traceback_str = traceback.format_exc()
                    # Print to stderr so it doesn't interfere with user output
                    import sys
                    print(f"Debug: Full error traceback:\n{traceback_str}", file=sys.stderr)
                    return f"Error generating response: {error_msg}"
            
            print(f"\n[LOOP] ⚠️  Maximum iterations ({max_iterations}) reached")
            print(f"{'='*60}\n")
            return "No response generated after processing tool calls"
        except Exception as e:
            error_msg = str(e) if str(e) else repr(e)
            print(f"\n[ERROR] {error_msg}")
            print(f"{'='*60}\n")
            return f"Error processing message: {error_msg}"
    
    def get_execution_history(self) -> list:
        """Get execution history."""
        return self.history_tracker.get_recent_operations()
    
    def clear_history(self):
        """Clear execution history."""
        self.history_tracker.logger.clear_history()
        self.gemini.clear_history()
