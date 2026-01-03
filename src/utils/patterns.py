"""
Risk pattern definitions for dangerous operations.
"""

import re
from typing import List, Tuple, Pattern


class RiskPatterns:
    """Patterns for identifying dangerous operations."""
    
    # Critical patterns - extremely unsafe
    CRITICAL_PATTERNS: List[Tuple[str, Pattern]] = [
        ("rm_rf", re.compile(r'rm\s+-rf', re.IGNORECASE)),
        ("sudo_rm_rf", re.compile(r'sudo\s+rm\s+-rf', re.IGNORECASE)),
        ("sudo_rm", re.compile(r'sudo\s+rm', re.IGNORECASE)),
        ("delete_recursive", re.compile(r'delete.*recursive', re.IGNORECASE)),
        ("format", re.compile(r'format\s+', re.IGNORECASE)),
        ("fdisk", re.compile(r'fdisk', re.IGNORECASE)),
        ("dd_destructive", re.compile(r'dd\s+.*of=/', re.IGNORECASE)),
        ("chmod_777", re.compile(r'chmod\s+777', re.IGNORECASE)),
        ("chown_root", re.compile(r'chown\s+root', re.IGNORECASE)),
        ("rm_rf_pattern", re.compile(r'rm.*-rf', re.IGNORECASE)),  # Catch variations
    ]
    
    # High risk patterns - not completely safe
    HIGH_RISK_PATTERNS: List[Tuple[str, Pattern]] = [
        ("delete_file", re.compile(r'delete\s+', re.IGNORECASE)),
        ("remove_file", re.compile(r'remove\s+', re.IGNORECASE)),
        ("overwrite", re.compile(r'overwrite|write.*over', re.IGNORECASE)),
        ("modify_config", re.compile(r'modify.*config|edit.*config', re.IGNORECASE)),
        ("chmod", re.compile(r'chmod\s+', re.IGNORECASE)),
        ("chown", re.compile(r'chown\s+', re.IGNORECASE)),
    ]
    
    # Protected path patterns
    PROTECTED_PATH_PATTERNS: List[Pattern] = [
        re.compile(r'^/etc/'),
        re.compile(r'^/system/'),
        re.compile(r'^/protected/'),
        re.compile(r'^/root/'),
        re.compile(r'^/usr/bin/'),
        re.compile(r'^/usr/sbin/'),
        re.compile(r'\.config$'),
        re.compile(r'\.env$'),
    ]
    
    # Safe operation patterns
    SAFE_OPERATIONS: List[str] = [
        "read",
        "list",
        "ls",
        "cat",
        "view",
        "show",
        "display",
        "get",
    ]
    
    @classmethod
    def matches_critical_pattern(cls, operation: str) -> bool:
        """Check if operation matches critical risk patterns."""
        for name, pattern in cls.CRITICAL_PATTERNS:
            if pattern.search(operation):
                return True
        return False
    
    @classmethod
    def matches_high_risk_pattern(cls, operation: str) -> bool:
        """Check if operation matches high risk patterns."""
        for name, pattern in cls.HIGH_RISK_PATTERNS:
            if pattern.search(operation):
                return True
        return False
    
    @classmethod
    def is_protected_path(cls, path: str) -> bool:
        """Check if path matches protected patterns."""
        for pattern in cls.PROTECTED_PATH_PATTERNS:
            if pattern.search(path):
                return True
        return False
    
    @classmethod
    def is_safe_operation(cls, operation: str) -> bool:
        """Check if operation is inherently safe (read-only)."""
        operation_lower = operation.lower()
        return any(safe_op in operation_lower for safe_op in cls.SAFE_OPERATIONS)
