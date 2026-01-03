"""
Execution history tracker for multi-step attack detection.
"""

from typing import List, Dict, Any, Optional
from src.sandbox.logger import ExecutionLogger
from src.kernel.config import ExecutionHistoryConfig


class ExecutionHistoryTracker:
    """Tracks execution history for pattern detection."""
    
    def __init__(self, config: ExecutionHistoryConfig, logger: ExecutionLogger):
        self.config = config
        self.logger = logger
    
    def record_operation(
        self,
        operation: str,
        target: Optional[str] = None,
        risk_level: str = "unknown",
        executed: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Record an operation in execution history."""
        return self.logger.log_operation(
            operation=operation,
            target=target,
            risk_level=risk_level,
            executed=executed,
            context=context
        )
    
    def get_recent_operations(self, count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent operations from history."""
        return self.logger.get_recent_operations(count)
    
    def get_operation_sequence(self, length: int = 5) -> List[Dict[str, Any]]:
        """Get the most recent sequence of operations."""
        return self.get_recent_operations(length)
    
    def get_operations_by_type(self, operation_type: str) -> List[Dict[str, Any]]:
        """Get all operations of a specific type."""
        return self.logger.get_operations_by_type(operation_type)
    
    def analyze_pattern(self, operation: str, target: Optional[str] = None) -> Dict[str, Any]:
        """Analyze recent operations for patterns related to current operation."""
        recent = self.get_recent_operations()
        
        analysis = {
            "recent_operations": recent,
            "operation_count": len(recent),
            "read_operations": [op for op in recent if "read" in op.get("operation", "").lower()],
            "list_operations": [op for op in recent if "list" in op.get("operation", "").lower()],
            "write_operations": [op for op in recent if any(kw in op.get("operation", "").lower() for kw in ["write", "delete", "modify"])],
            "protected_access_attempts": [op for op in recent if op.get("risk_level") in ["not_completely_safe", "extremely_unsafe"]],
        }
        
        return analysis
