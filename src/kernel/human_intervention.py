"""
Human intervention handler for extremely unsafe operations.
"""

from typing import Dict, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from src.utils.templates import RefusalTemplates
from src.kernel.config import HumanInterventionConfig


class InterventionDecision(Enum):
    """Human intervention decision types."""
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    PENDING = "pending"


@dataclass
class InterventionRequest:
    """Request for human intervention."""
    operation: str
    target: Optional[str]
    risk_analysis: str
    context: Dict[str, Any]
    timestamp: datetime
    decision: InterventionDecision = InterventionDecision.PENDING
    human_feedback: Optional[str] = None


class HumanInterventionHandler:
    """Handles human intervention for extremely unsafe operations."""
    
    def __init__(self, config: HumanInterventionConfig):
        self.config = config
        self.templates = RefusalTemplates()
        self.pending_requests: Dict[str, InterventionRequest] = {}
        self.decision_callback: Optional[Callable[[InterventionRequest], InterventionDecision]] = None
    
    def queue_intervention(
        self,
        operation: str,
        target: Optional[str],
        risk_analysis: str,
        context: Dict[str, Any],
        request_id: Optional[str] = None
    ) -> InterventionRequest:
        """Queue an operation for human intervention."""
        if request_id is None:
            request_id = f"{operation}_{target}_{datetime.utcnow().timestamp()}"
        
        request = InterventionRequest(
            operation=operation,
            target=target,
            risk_analysis=risk_analysis,
            context=context,
            timestamp=datetime.utcnow()
        )
        
        self.pending_requests[request_id] = request
        
        # Generate intervention message
        message = self.templates.generate_human_intervention_message(
            operation=operation,
            context=context,
            risk_analysis=risk_analysis
        )
        
        # If CLI interface, prompt user
        if self.config.interface == "cli":
            self._prompt_cli(request, message)
        
        return request
    
    def _prompt_cli(self, request: InterventionRequest, message: str):
        """Prompt user via CLI for intervention decision."""
        print("\n" + "="*60)
        print(message)
        print("="*60)
        print("\nOptions:")
        print("  [a]pprove - Allow operation to proceed")
        print("  [r]eject - Block operation and suggest alternative")
        print("  [m]odify - Suggest modification to operation")
        print("\nDecision: ", end="")
        
        # In actual implementation, this would wait for user input
        # For now, we'll use the callback if available
        if self.decision_callback:
            decision = self.decision_callback(request)
            self.handle_decision(request, decision, None)
    
    def handle_decision(
        self,
        request: InterventionRequest,
        decision: InterventionDecision,
        feedback: Optional[str] = None
    ):
        """Handle human decision on intervention request."""
        request.decision = decision
        request.human_feedback = feedback
    
    def get_decision_message(self, request: InterventionRequest) -> str:
        """Get message to inject into conversation based on human decision."""
        if request.decision == InterventionDecision.APPROVE:
            return f"Human approval granted for: {request.operation}"
        elif request.decision == InterventionDecision.REJECT:
            return f"Human intervention: Operation {request.operation} was rejected for security reasons. {request.human_feedback or 'Please use a safer alternative.'}"
        elif request.decision == InterventionDecision.MODIFY:
            return f"Human intervention: Operation {request.operation} should be modified. {request.human_feedback or 'Please use a safer version of this operation.'}"
        else:
            return f"Operation {request.operation} is pending human review."
    
    def set_decision_callback(self, callback: Callable[[InterventionRequest], InterventionDecision]):
        """Set callback for automated decision handling (for testing)."""
        self.decision_callback = callback
