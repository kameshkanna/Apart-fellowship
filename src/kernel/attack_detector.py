"""
Multi-step attack pattern detector.
"""

from typing import List, Dict, Any, Optional, Tuple
from src.kernel.config import AttackPatternsConfig
from src.kernel.execution_history import ExecutionHistoryTracker


class AttackDetector:
    """Detects multi-step attack patterns from execution history."""
    
    def __init__(self, config: AttackPatternsConfig, history_tracker: ExecutionHistoryTracker):
        self.config = config
        self.history_tracker = history_tracker
    
    def detect_attack_pattern(
        self,
        current_operation: str,
        current_target: Optional[str] = None
    ) -> Tuple[bool, float, str, Dict[str, Any]]:
        """
        Detect if current operation is part of a multi-step attack.
        
        Returns:
            Tuple of (is_attack, confidence, pattern_name, details)
        """
        recent_ops = self.history_tracker.get_recent_operations()
        
        if len(recent_ops) < 2:
            return (False, 0.0, "", {})
        
        # Check reconnaissance -> exploitation pattern
        recon_exploit = self._check_reconnaissance_exploitation(recent_ops, current_operation, current_target)
        if recon_exploit[0]:
            return recon_exploit
        
        # Check escalation chain pattern
        escalation = self._check_escalation_chain(recent_ops, current_operation)
        if escalation[0]:
            return escalation
        
        # Check info gathering -> attack pattern
        info_attack = self._check_info_gathering_attack(recent_ops, current_operation)
        if info_attack[0]:
            return info_attack
        
        return (False, 0.0, "", {})
    
    def _check_reconnaissance_exploitation(
        self,
        recent_ops: List[Dict[str, Any]],
        current_operation: str,
        current_target: Optional[str]
    ) -> Tuple[bool, float, str, Dict[str, Any]]:
        """Check for reconnaissance followed by exploitation."""
        # Look for pattern: read protected -> list protected -> modify/delete protected
        protected_reads = []
        protected_lists = []
        
        for op in recent_ops:
            op_type = op.get("operation", "").lower()
            op_target = op.get("target", "")
            risk_level = op.get("risk_level", "")
            
            if "read" in op_type and risk_level in ["not_completely_safe", "extremely_unsafe"]:
                protected_reads.append(op)
            elif "list" in op_type and risk_level in ["not_completely_safe", "extremely_unsafe"]:
                protected_lists.append(op)
        
        # Check if current operation is destructive after reconnaissance
        is_destructive = any(kw in current_operation.lower() for kw in ["delete", "modify", "remove", "write", "edit"])
        
        if (protected_reads or protected_lists) and is_destructive:
            # Check if targets are related
            if current_target:
                for read_op in protected_reads:
                    read_target = read_op.get("target", "")
                    if read_target and current_target.startswith(read_target.split('/')[0]):
                        confidence = 0.85
                        return (
                            True,
                            confidence,
                            "reconnaissance_exploitation",
                            {
                                "reconnaissance_ops": protected_reads + protected_lists,
                                "exploitation_op": current_operation,
                                "pattern": "read/list protected -> modify/delete"
                            }
                        )
        
        return (False, 0.0, "", {})
    
    def _check_escalation_chain(
        self,
        recent_ops: List[Dict[str, Any]],
        current_operation: str
    ) -> Tuple[bool, float, str, Dict[str, Any]]:
        """Check for escalation chain: safe ops building up to unsafe op."""
        if len(recent_ops) < 3:
            return (False, 0.0, "", {})
        
        # Check if we have a pattern of safe -> safe -> unsafe
        risk_levels = [op.get("risk_level", "unknown") for op in recent_ops[-3:]]
        current_risk = "not_completely_safe" if any(kw in current_operation.lower() for kw in ["delete", "modify", "remove"]) else "completely_safe"
        
        if risk_levels[0] == "completely_safe" and risk_levels[1] == "completely_safe" and current_risk != "completely_safe":
            confidence = 0.70
            return (
                True,
                confidence,
                "escalation_chain",
                {
                    "pattern": "safe -> safe -> unsafe",
                    "recent_operations": recent_ops[-3:],
                    "current_operation": current_operation
                }
            )
        
        return (False, 0.0, "", {})
    
    def _check_info_gathering_attack(
        self,
        recent_ops: List[Dict[str, Any]],
        current_operation: str
    ) -> Tuple[bool, float, str, Dict[str, Any]]:
        """Check for info gathering followed by attack."""
        # Pattern: list -> read -> delete
        has_list = False
        has_read = False
        is_destructive = any(kw in current_operation.lower() for kw in ["delete", "remove", "modify"])
        
        for op in recent_ops[-5:]:  # Check last 5 operations
            op_type = op.get("operation", "").lower()
            if "list" in op_type:
                has_list = True
            elif "read" in op_type:
                has_read = True
        
        if (has_list or has_read) and is_destructive:
            confidence = 0.75
            return (
                True,
                confidence,
                "info_gathering_attack",
                {
                    "pattern": "list/read -> delete",
                    "info_gathering_ops": [op for op in recent_ops if "list" in op.get("operation", "").lower() or "read" in op.get("operation", "").lower()],
                    "attack_op": current_operation
                }
            )
        
        return (False, 0.0, "", {})
