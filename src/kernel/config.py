"""
Configuration management for the Resilient Permission Kernel.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class SafetyPolicyConfig(BaseModel):
    """Safety policy configuration."""
    strict_mode: bool = True


class ExecutionHistoryConfig(BaseModel):
    """Execution history tracking configuration."""
    window_size: int = 50
    enable_pattern_detection: bool = True


class ProtectedResourcesConfig(BaseModel):
    """Protected resources configuration."""
    files: List[str] = Field(default_factory=list)
    directories: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list)


class AttackPatternConfig(BaseModel):
    """Attack pattern detection configuration."""
    pattern: List[str]
    threshold: float


class AttackPatternsConfig(BaseModel):
    """Attack patterns configuration."""
    reconnaissance_exploitation: List[AttackPatternConfig] = Field(default_factory=list)
    escalation_chain: List[AttackPatternConfig] = Field(default_factory=list)
    info_gathering_attack: List[AttackPatternConfig] = Field(default_factory=list)


class RefusalTemplatesConfig(BaseModel):
    """Refusal signal templates."""
    not_safe: str = "I cannot execute {operation} because {reason}. Instead, {alternative}."


class HumanInterventionConfig(BaseModel):
    """Human intervention configuration."""
    require_approval_for: List[str] = Field(default_factory=list)
    interface: str = "cli"


class SandboxConfig(BaseModel):
    """Sandbox configuration."""
    workspace_path: str = "./sandbox/workspace"
    protected_path: str = "./sandbox/protected"
    logs_path: str = "./sandbox/logs"
    isolation_level: str = "virtual"


class KernelConfig(BaseModel):
    """Main kernel configuration."""
    safety_policy: SafetyPolicyConfig
    execution_history: ExecutionHistoryConfig
    protected_resources: ProtectedResourcesConfig
    attack_patterns: AttackPatternsConfig
    refusal_templates: RefusalTemplatesConfig
    human_intervention: HumanInterventionConfig
    sandbox: SandboxConfig


def load_config(config_path: str = "config/kernel_config.yaml") -> KernelConfig:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    
    kernel_data = config_data.get('kernel', {})
    
    return KernelConfig(
        safety_policy=SafetyPolicyConfig(**kernel_data.get('safety_policy', {})),
        execution_history=ExecutionHistoryConfig(**kernel_data.get('execution_history', {})),
        protected_resources=ProtectedResourcesConfig(**kernel_data.get('protected_resources', {})),
        attack_patterns=AttackPatternsConfig(
            reconnaissance_exploitation=[
                AttackPatternConfig(**p) for p in kernel_data.get('attack_patterns', {}).get('reconnaissance_exploitation', [])
            ],
            escalation_chain=[
                AttackPatternConfig(**p) for p in kernel_data.get('attack_patterns', {}).get('escalation_chain', [])
            ],
            info_gathering_attack=[
                AttackPatternConfig(**p) for p in kernel_data.get('attack_patterns', {}).get('info_gathering_attack', [])
            ],
        ),
        refusal_templates=RefusalTemplatesConfig(**kernel_data.get('refusal_templates', {})),
        human_intervention=HumanInterventionConfig(**kernel_data.get('human_intervention', {})),
        sandbox=SandboxConfig(**kernel_data.get('sandbox', {}))
    )
