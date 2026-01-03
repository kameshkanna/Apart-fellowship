"""
Main entry point for Resilient Permission Kernel demonstration.
"""

import os
import sys
from src.kernel.kernel import ResilientPermissionKernel


def main():
    """Main demonstration function."""
    # Get API key from environment or use None to let wrapper use default
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Initialize kernel (will use default API key from wrapper if not provided)
    print("Initializing Resilient Permission Kernel...")
    kernel = ResilientPermissionKernel(api_key=api_key)
    print("Kernel initialized successfully!\n")
    
    # Demonstration loop
    print("="*60)
    print("Resilient Permission Kernel - Interactive Demo")
    print("="*60)
    print("Type 'exit' to quit")
    print("Type 'history' to see execution history")
    print("Type 'rate' to see rate limit status")
    print("Rate Limit: 10 API calls per minute")
    print("="*60)
    print()
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() == "exit":
                break
            
            if user_input.lower() == "history":
                history = kernel.get_execution_history()
                print(f"\nExecution History ({len(history)} operations):")
                for op in history[-10:]:  # Show last 10
                    print(f"  - {op.get('operation')} on {op.get('target')} [{op.get('risk_level')}]")
                print()
                continue
            
            if user_input.lower() == "rate":
                status = kernel.gemini.get_rate_limit_status()
                print(f"\nRate Limit Status:")
                print(f"  Limit: {status['rate_limit']} calls per {status['rate_window_seconds']} seconds")
                print(f"  Calls in current window: {status['calls_in_window']}")
                print(f"  Remaining calls: {status['remaining_calls']}")
                if status['time_until_reset_seconds'] > 0:
                    print(f"  Time until reset: {status['time_until_reset_seconds']:.1f} seconds")
                else:
                    print(f"  Window is clear")
                print()
                continue
            
            if not user_input:
                continue
            
            # Process message
            try:
                response = kernel.process_user_message(user_input)
                if response:
                    print(f"\nAgent: {response}\n")
                else:
                    print("\nAgent: No response received.\n")
            except RuntimeError as e:
                if "Rate limit exceeded" in str(e):
                    status = kernel.gemini.get_rate_limit_status()
                    print(f"\n[Rate Limit] {e}")
                    print(f"Please wait {status['time_until_reset_seconds']:.1f} seconds before trying again.\n")
                else:
                    raise
        
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else repr(e)
            print(f"Error: {error_msg}")
            # Print full traceback for debugging
            traceback.print_exc()
            print()
    
    print("Kernel shutdown complete.")


if __name__ == "__main__":
    main()
