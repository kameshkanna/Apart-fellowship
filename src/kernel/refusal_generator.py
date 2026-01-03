"""
Refusal signal generator for resampling triggers.
"""

from typing import Dict, Any, Optional
from src.utils.templates import RefusalTemplates
from src.kernel.config import RefusalTemplatesConfig


class RefusalGenerator:
    """Generates refusal signals to trigger model resampling."""
    
    def __init__(self, config: RefusalTemplatesConfig):
        self.config = config
        self.templates = RefusalTemplates()
    
    def generate_refusal_signal(
        self,
        operation: str,
        reason: str,
        target: Optional[str] = None,
        alternative: Optional[str] = None
    ) -> str:
        """Generate a refusal signal for operations that are not completely safe."""
        if alternative is None:
            alternative = self.templates.suggest_alternative(operation, target or "the target")
        
        return self.templates.generate_not_safe_refusal(
            operation=operation,
            reason=reason,
            alternative=alternative,
            template=self.config.not_safe
        )
    
    def generate_contextual_refusal(
        self,
        operation: str,
        safety_assessment: Dict[str, Any],
        target: Optional[str] = None
    ) -> str:
        """Generate a contextual refusal signal based on safety assessment."""
        reason = safety_assessment.get("reason", "this operation is not completely safe")
        details = safety_assessment.get("details", {})
        
        # Enhance reason with details
        if details.get("protection_check"):
            reason = details["protection_check"]
        elif details.get("matched_patterns"):
            patterns = ", ".join(details["matched_patterns"])
            reason = f"operation matches risk patterns: {patterns}"
        
        alternative = self.templates.suggest_alternative(operation, target or "the target")
        
        return self.generate_refusal_signal(
            operation=operation,
            reason=reason,
            target=target,
            alternative=alternative
        )
