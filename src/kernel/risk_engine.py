"""
Binary safety assessment engine for operation risk classification.
"""

from typing import Dict, Any, Optional, Tuple
from enum import Enum
from src.utils.patterns import RiskPatterns
from src.sandbox.protection import ProtectionManager


class SafetyLevel(Enum):
    """Safety classification levels."""
    COMPLETELY_SAFE = "completely_safe"
    NOT_COMPLETELY_SAFE = "not_completely_safe"
    EXTREMELY_UNSAFE = "extremely_unsafe"


class RiskEngine:
    """Binary safety assessment engine."""
    
    def __init__(self, protection_manager: ProtectionManager):
        self.protection_manager = protection_manager
        self.patterns = RiskPatterns()
    
    def assess_operation(
        self,
        operation: str,
        target: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[SafetyLevel, str, Dict[str, Any]]:
        """
        Assess operation safety using binary classification.
        
        Returns:
            Tuple of (SafetyLevel, reason, details)
        """
        operation_lower = operation.lower()
        details = {
            "operation": operation,
            "target": target,
            "matched_patterns": [],
            "protection_check": None
        }
        
        # Check for critical patterns (extremely unsafe) - check both operation and target
        operation_and_target = f"{operation} {target or ''}"
        if self.patterns.matches_critical_pattern(operation_and_target) or self.patterns.matches_critical_pattern(operation):
            details["matched_patterns"].append("critical_pattern")
            return (
                SafetyLevel.EXTREMELY_UNSAFE,
                f"Operation matches critical risk pattern: {operation}",
                details
            )
        
        # Also check target for critical patterns (e.g., if target contains "sudo rm -rf")
        if target and self.patterns.matches_critical_pattern(target):
            details["matched_patterns"].append("critical_pattern_in_target")
            return (
                SafetyLevel.EXTREMELY_UNSAFE,
                f"Target contains critical risk pattern: {target}",
                details
            )
        
        # Check if target is protected
        if target:
            if self.protection_manager.is_protected(target):
                protection_reason = self.protection_manager.get_protection_reason(target)
                details["protection_check"] = protection_reason
                
                # Protected resource access is extremely unsafe
                return (
                    SafetyLevel.EXTREMELY_UNSAFE,
                    f"Target is protected: {protection_reason}",
                    details
                )
            
            # Check protected path patterns
            if self.patterns.is_protected_path(target):
                details["matched_patterns"].append("protected_path")
                return (
                    SafetyLevel.EXTREMELY_UNSAFE,
                    f"Target path matches protected pattern: {target}",
                    details
                )
        
        # Check for high-risk patterns (not completely safe)
        if self.patterns.matches_high_risk_pattern(operation):
            details["matched_patterns"].append("high_risk_pattern")
            return (
                SafetyLevel.NOT_COMPLETELY_SAFE,
                f"Operation matches high-risk pattern: {operation}",
                details
            )
        
        # Check if operation is inherently safe (read-only)
        if self.patterns.is_safe_operation(operation):
            # Additional check: even read operations on protected files are unsafe
            if target and self.protection_manager.is_protected(target):
                return (
                    SafetyLevel.NOT_COMPLETELY_SAFE,
                    f"Read operation on protected resource: {target}",
                    details
                )
            
            # Read-only operations on non-protected resources are completely safe
            return (
                SafetyLevel.COMPLETELY_SAFE,
                f"Read-only operation on safe resource",
                details
            )
        
        # Write operations (creating new files) are safe
        # Only overwriting existing files or modifying is unsafe
        if operation_lower == "write":
            # Check if this is overwriting an existing file
            if target:
                # For now, treat write as safe (creating new files)
                # Overwrite protection can be added later if needed
                return (
                    SafetyLevel.COMPLETELY_SAFE,
                    f"Write operation (file creation) is safe",
                    details
                )
            return (
                SafetyLevel.COMPLETELY_SAFE,
                f"Write operation is safe",
                details
            )
        
        # Delete operations are not completely safe (but not extremely unsafe unless sudo/recursive)
        if operation_lower in ["delete", "remove"]:
            # Check if it's a critical delete pattern (sudo rm -rf, etc.)
            if self.patterns.matches_critical_pattern(operation):
                return (
                    SafetyLevel.EXTREMELY_UNSAFE,
                    f"Critical delete operation detected: {operation}",
                    details
                )
            # Regular delete is not completely safe (requires resampling)
            details["matched_patterns"].append("destructive_operation")
            return (
                SafetyLevel.NOT_COMPLETELY_SAFE,
                f"Delete operation requires confirmation",
                details
            )
        
        # Other destructive operations (modify, edit, change, update) are not completely safe
        destructive_keywords = ["modify", "edit", "change", "update", "overwrite"]
        if any(keyword in operation_lower for keyword in destructive_keywords):
            details["matched_patterns"].append("destructive_operation")
            return (
                SafetyLevel.NOT_COMPLETELY_SAFE,
                f"Modification operation requires confirmation: {operation}",
                details
            )
        
        # Default: if we can't confirm it's safe, it's not completely safe
        return (
            SafetyLevel.NOT_COMPLETELY_SAFE,
            f"Operation safety cannot be confirmed: {operation}",
            details
        )
    
    def is_completely_safe(
        self,
        operation: str,
        target: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Quick check if operation is completely safe."""
        safety_level, _, _ = self.assess_operation(operation, target, parameters)
        return safety_level == SafetyLevel.COMPLETELY_SAFE
    
    def is_extremely_unsafe(
        self,
        operation: str,
        target: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Quick check if operation is extremely unsafe."""
        safety_level, _, _ = self.assess_operation(operation, target, parameters)
        return safety_level == SafetyLevel.EXTREMELY_UNSAFE
