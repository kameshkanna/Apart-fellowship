"""
Templates for refusal signals and human intervention messages.
"""

from typing import Dict, Any


class RefusalTemplates:
    """Templates for generating refusal signals."""
    
    @staticmethod
    def generate_not_safe_refusal(
        operation: str,
        reason: str,
        alternative: str,
        template: str = "I cannot execute {operation} because {reason}. Instead, {alternative}."
    ) -> str:
        """Generate a refusal signal for operations that are not completely safe."""
        return template.format(
            operation=operation,
            reason=reason,
            alternative=alternative
        )
    
    @staticmethod
    def generate_human_intervention_message(
        operation: str,
        context: Dict[str, Any],
        risk_analysis: str
    ) -> str:
        """Generate message for human intervention queue."""
        return f"""
⚠️  HUMAN INTERVENTION REQUIRED

Operation: {operation}
Risk Level: EXTREMELY UNSAFE

Context:
{context}

Risk Analysis:
{risk_analysis}

Recent Operations:
{context.get('recent_operations', 'None')}

Please review and approve/reject this operation.
"""
    
    @staticmethod
    def suggest_alternative(operation: str, target: str) -> str:
        """Suggest a safer alternative to a dangerous operation."""
        operation_lower = operation.lower()
        
        if "delete" in operation_lower or "remove" in operation_lower:
            return f"Instead of deleting {target}, I can help you review its contents first or move it to a backup location."
        
        if "modify" in operation_lower or "edit" in operation_lower:
            return f"Instead of modifying {target}, I can show you its current contents and help you create a modified copy in a safe location."
        
        if "chmod" in operation_lower or "chown" in operation_lower:
            return f"Instead of changing permissions on {target}, I can help you understand the current permissions and suggest safer alternatives."
        
        return f"Instead of {operation} on {target}, I can help you with a safer alternative approach."
