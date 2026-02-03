import re

from typing import Dict, Callable, Any

# NOTE: `parse_code` and `execute_code` are used to parse the output of the LLM, if the model
# returns code rather than a tool call.

# This is a simple implementation and does not provide a safe environment.
# We can swap this out with something like E2B to execute the code in a safe environment,
# and create a CodeSandbox environment to run the code in. That can handle the execution of the code,
# or direct tool use.
def parse_code(llm_output: str) -> str:
    """
    Extract code from LLM output. Uses a simple heuristic, checking for ```python and ``` markers.
    """
    code_match = re.search(r'```(?:python)?(.*?)```', llm_output, re.DOTALL)

    if code_match:
        return code_match.group(1).strip()

    raise ValueError("No code found in output")

def execute_code(code: str, tools: Dict[str, Callable]) -> Any:
    """
    Execute the code in a safe environment with access to tools.

    NOTE: This is a simple implementation and does not provide a safe environment.

    Use something like E2B to execute the code in a safe environment.
    """
    # Create namespace with tools dictionary and individual tools
    namespace = {
        'tools': tools,
        **tools,
        'final_answer': None
    }
    
    try:
        exec(code, namespace)
        return namespace.get('final_answer'), None
    except Exception as e:
        return None, f"Code execution error: {str(e)}"

def get_steps_since_last_plan(memory: "AgentMemory", current_step: int) -> str:
    """
    get a formatted string of steps executed since the last planning step.
    """
    if not memory.planning_memories:
        return "no previous steps"

    last_plan_step = self.memory.planning_memories[-1].step
    recent_steps = []

    for mem in self.memory.memories:
        if mem.step > last_plan_step and mem.step < current_step:
            result = f"observation: {mem.observation}"
            result += f"\nerror: {mem.error}"
            recent_steps.append(f"step {mem.step}:\naction: {mem.action}\n{result}")

    if not recent_steps:
        return "no steps executed since last plan"

    return "\n".join(recent_steps)
