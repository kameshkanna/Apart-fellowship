"""
Execution router with strict safety policy.
"""

from typing import Dict, Any, Optional, Tuple
from src.kernel.risk_engine import RiskEngine, SafetyLevel
from src.kernel.execution_history import ExecutionHistoryTracker
from src.kernel.attack_detector import AttackDetector
from src.kernel.refusal_generator import RefusalGenerator
from src.kernel.human_intervention import HumanInterventionHandler, InterventionRequest


class ExecutionRouter:
    """Routes operations based on strict safety assessment."""
    
    def __init__(
        self,
        risk_engine: RiskEngine,
        history_tracker: ExecutionHistoryTracker,
        attack_detector: AttackDetector,
        refusal_generator: RefusalGenerator,
        human_intervention: HumanInterventionHandler
    ):
        self.risk_engine = risk_engine
        self.history_tracker = history_tracker
        self.attack_detector = attack_detector
        self.refusal_generator = refusal_generator
        self.human_intervention = human_intervention
    
    def route_operation(
        self,
        operation: str,
        target: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Optional[InterventionRequest], Dict[str, Any]]:
        """
        Route an operation based on safety assessment.
        
        Returns:
            Tuple of (should_execute, refusal_signal, intervention_request, metadata)
        """
        metadata = {
            "operation": operation,
            "target": target,
            "safety_assessment": None,
            "attack_detected": False,
            "routing_decision": None
        }
        
        # Step 1: Assess operation safety
        safety_level, reason, details = self.risk_engine.assess_operation(
            operation, target, parameters
        )
        
        safety_assessment = {
            "level": safety_level.value,
            "reason": reason,
            "details": details
        }
        metadata["safety_assessment"] = safety_assessment
        
        # Step 2: Check for multi-step attack patterns
        is_attack, confidence, pattern_name, attack_details = self.attack_detector.detect_attack_pattern(
            operation, target
        )
        
        if is_attack:
            metadata["attack_detected"] = True
            metadata["attack_pattern"] = pattern_name
            metadata["attack_confidence"] = confidence
            metadata["attack_details"] = attack_details
            
            # Attack detected -> Extremely unsafe -> Human intervention
            safety_level = SafetyLevel.EXTREMELY_UNSAFE
            safety_assessment["level"] = "extremely_unsafe"
            safety_assessment["reason"] = f"Multi-step attack pattern detected: {pattern_name}"
        
        # Step 3: Route based on safety level
        if safety_level == SafetyLevel.COMPLETELY_SAFE:
            # Execute immediately
            metadata["routing_decision"] = "execute"
            self.history_tracker.record_operation(
                operation=operation,
                target=target,
                risk_level="completely_safe",
                executed=True,
                context=context
            )
            return (True, None, None, metadata)
        
        elif safety_level == SafetyLevel.EXTREMELY_UNSAFE:
            # Require human intervention
            metadata["routing_decision"] = "human_intervention"
            
            # Record blocked operation
            self.history_tracker.record_operation(
                operation=operation,
                target=target,
                risk_level="extremely_unsafe",
                executed=False,
                context=context
            )
            
            # Create intervention request
            risk_analysis = f"{reason}\nAttack Pattern: {pattern_name if is_attack else 'None'}"
            intervention_request = self.human_intervention.queue_intervention(
                operation=operation,
                target=target,
                risk_analysis=risk_analysis,
                context={
                    "safety_assessment": safety_assessment,
                    "attack_detected": is_attack,
                    "recent_operations": self.history_tracker.get_recent_operations(10),
                    **(context or {})
                }
            )
            
            return (False, None, intervention_request, metadata)
        
        else:  # NOT_COMPLETELY_SAFE
            # Trigger resampling (refusal signal)
            metadata["routing_decision"] = "resample"
            
            # Record refused operation
            self.history_tracker.record_operation(
                operation=operation,
                target=target,
                risk_level="not_completely_safe",
                executed=False,
                context=context
            )
            
            # Generate refusal signal
            refusal_signal = self.refusal_generator.generate_contextual_refusal(
                operation=operation,
                safety_assessment=safety_assessment,
                target=target
            )
            
            return (False, refusal_signal, None, metadata)
