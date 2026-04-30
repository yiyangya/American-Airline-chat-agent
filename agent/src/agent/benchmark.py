#!/usr/bin/env python3
"""
Tau2 Benchmark Runner

Loads tasks from tau2-bench and runs evaluations using the agent with MCP server support.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


from .agent import ToolCallingAgent
from .tool_manager import ToolManager
from .config import TAU2_DOMAIN_DATA_PATH, benchmark_user_simulation_llm
from .benchmark_evaluator import Task, Evaluator, EvaluationResult


# ============================================================================
# USER SIMULATOR
# ============================================================================

class UserSimulator:
    """Simulates a user in a conversation with an agent."""

    def __init__(self, simulation_system_prompt: str, user_scenario: str):
        """
        Initialize the user simulator.

        Args:
            simulation_system_prompt: System prompt for the user simulator
            user_scenario: Specific scenario instructions for this user
        """
        # Conversation from user's side (won't see internal tool messages)
        system_prompt = f"""{simulation_system_prompt}

<scenario>
{user_scenario}
</scenario>"""

        self.user_conversation_history: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    def generate_user_response(self, agent_message: str) -> str:
        """
        Generate the user's response to an agent message.

        Args:
            agent_message: Message from the agent

        Returns:
            User's response
        """
        self.user_conversation_history.append({
            "role": "user",
            "content": agent_message
        })

        response = benchmark_user_simulation_llm(self.user_conversation_history)

        user_response = response.choices[0].message.content

        # Add user response to history
        self.user_conversation_history.append({
            "role": "assistant",
            "content": user_response
        })

        return user_response


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class Orchestrator:
    """Runs the full conversation between agent and user simulator."""

    def run(
        self,
        agent: ToolCallingAgent,
        user_sim: UserSimulator,
        max_turns: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Run a conversation between agent and user simulator.

        Args:
            agent: The tool-calling agent
            user_sim: The user simulator
            max_turns: Maximum number of conversation turns

        Returns:
            Full conversation from the agent's side (including tool calls)
        """
        greeting = "Hi! How can I help you today?"
        print(f"\n🤖 Agent: {greeting}")
        last_user_message = user_sim.generate_user_response(greeting)
        print(f"👤 User: {last_user_message}")

        # Main conversation loop
        for turn in range(max_turns):
            try:
                agent_response = agent.execute(last_user_message)
                print(f"🤖 Agent: {agent_response}")

                # User's turn
                last_user_message = user_sim.generate_user_response(agent_response)
                print(f"👤 User: {last_user_message}")

                if self._is_stop_signal(last_user_message):
                    break

            except Exception as error:
                print(f"Error during orchestrator run: {error}")
                break

        return agent.get_messages()

    def _is_stop_signal(self, message: str) -> bool:
        """Check if message contains a stop signal."""
        return (
            "###STOP###" in message or
            "###TRANSFER###" in message or
            "###OUT-OF-SCOPE###" in message
        )


# ============================================================================
# TASK UTILITIES
# ============================================================================

def format_user_scenario(task: Task) -> str:
    """
    Format user scenario from task data into a readable string.

    Args:
        task: Task with user scenario data

    Returns:
        Formatted user scenario string
    """
    if not task.user_scenario:
        return ""

    lines = []
    for key, value in task.user_scenario.items():
        if value is not None:
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


def filter_tasks(tasks: List[Task]) -> List[Task]:
    """
    Filter tasks based on benchmark requirements.
    Currently filters out tasks with initial_state and tasks without user_scenario.

    Args:
        tasks: List of all tasks

    Returns:
        Filtered list of tasks
    """
    filtered = tasks

    # Filter out tasks with initial_state
    without_initial_state = [t for t in filtered if not t.initial_state]
    if len(filtered) != len(without_initial_state):
        print(f"🚫 Filtered out {len(filtered) - len(without_initial_state)} tasks with initial_state")
    filtered = without_initial_state

    # Filter out tasks without user_scenario
    with_user_scenario = [t for t in filtered if t.user_scenario]
    if len(filtered) != len(with_user_scenario):
        print(f"🚫 Filtered out {len(filtered) - len(with_user_scenario)} tasks without user_scenario")
    filtered = with_user_scenario

    return filtered


# ============================================================================
# FILE I/O
# ============================================================================

def load_tasks(tasks_path: str) -> List[Task]:
    """Load tasks from JSON file."""
    with open(tasks_path, 'r') as f:
        data = json.load(f)
    return [Task(**task) for task in data]


def load_text_file(path: str) -> str:
    """Load text content from file."""
    with open(path, 'r') as f:
        return f.read()


# ============================================================================
# BENCHMARK RUNNER
# ============================================================================

def run_single_task(
    task: Task,
    tool_manager: ToolManager,
    simulation_guidelines: str,
    orchestrator: Orchestrator,
    evaluator: Evaluator
) -> EvaluationResult:
    """
    Run a single task through the full agent-user simulation and evaluation pipeline.

    Args:
        task: The task to run
        tool_manager: Manager for MCP tools
        simulation_guidelines: Guidelines for user simulation
        orchestrator: Orchestrator for agent-user conversation
        evaluator: Evaluator for task results

    Returns:
        Evaluation result for the task
    """
    # Reset MCP servers before each task
    if not tool_manager.reset_all():
        raise RuntimeError("Failed to reset MCP servers")

    # Create agent
    agent = ToolCallingAgent(tool_manager)

    # Create user simulator
    user_scenario = format_user_scenario(task)
    user_sim = UserSimulator(simulation_guidelines, user_scenario)

    # Run conversation
    conversation = orchestrator.run(agent, user_sim)

    # Evaluate results
    return evaluator.evaluate_task(task, conversation)


def print_summary(results: List[EvaluationResult]) -> None:
    """
    Print a summary of benchmark results.

    Args:
        results: List of evaluation results
    """
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")

    passed = sum(1 for r in results if r.success)
    total = len(results)

    print(f"\nTotal: {total} tasks")
    print(f"Passed: {passed} ({(passed / total * 100):.1f}%)")
    print(f"Failed: {total - passed}\n")

    for result in results:
        icon = "✅" if result.success else "❌"
        print(f"{icon} {result.task_id}")

    print()


def run_benchmark(
    tasks_path: str,
    policy_path: str,
    simulation_guidelines_path: str,
    mcp_servers: List[str],
    task_filter: Optional[str] = None
) -> None:
    """
    Main benchmark runner function.

    Args:
        tasks_path: Path to tasks.json
        policy_path: Path to policy.md
        simulation_guidelines_path: Path to simulation guidelines
        mcp_servers: List of MCP server URLs
        task_filter: Optional filter to run specific tasks
    """
    print("🚀 Starting Tau2 Benchmark\n")

    # Load resources
    tasks = load_tasks(tasks_path)
    simulation_guidelines = load_text_file(simulation_guidelines_path)

    print(f"📋 Loaded {len(tasks)} tasks")

    # Initialize tool manager
    tool_manager = ToolManager.from_servers(mcp_servers)
    # Filter tasks
    tasks = filter_tasks(tasks)

    # Apply user filter if specified
    if task_filter:
        tasks = [t for t in tasks if task_filter in t.id]
    
    print(f"🎯 Running {len(tasks)} tasks\n")

    # Initialize shared components
    orchestrator = Orchestrator()
    evaluator = Evaluator()
    results = []

    # Run each task
    for i, task in enumerate(tasks):
        # Print task header
        print(f"\n{'=' * 80}")
        print(f"Task {i + 1}/{len(tasks)}: {task.id}")
        print(f"{'=' * 80}")
        if task.description:
            print(f"Purpose: {task.description.get('purpose', '')}")

        try:
            # Run task
            result = run_single_task(
                task,
                tool_manager,
                simulation_guidelines,
                orchestrator,
                evaluator
            )
            results.append(result)

            # Print result
            print(f"\n📊 Evaluation Result:")
            print(f"   Success: {'✅' if result.success else '❌'}")
            for detail in result.details:
                print(f"   {detail}")

        except Exception as error:
            print(f"\n❌ Error running task: {error}")
            results.append(EvaluationResult(
                task_id=task.id,
                success=False,
                actions_matched=False,
                nl_assertions_passed=False,
                details=[f"Error: {error}"],
                conversation=[]
            ))
            raise

    # Print summary
    print_summary(results)


# ============================================================================
# CLI
# ============================================================================

def main():
    """Main entry point for the benchmark CLI."""
    parser = argparse.ArgumentParser(
        description="Run Tau2 benchmark with MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python -m agent.benchmark "http://localhost:3000/mcp"

Environment variables:
  TASK_FILTER - Filter tasks by ID substring
        """
    )

    parser.add_argument(
        "mcp_servers",
        nargs="+",
        help="MCP server URLs or commands"
    )

    args = parser.parse_args()

    # Get package root (src/agent/)
    package_root = Path(__file__).parent
    data_path = package_root / TAU2_DOMAIN_DATA_PATH

    # Configure paths
    tasks_path = str(data_path / "tasks.json")
    policy_path = str(data_path / "policy.md")
    simulation_guidelines_path = str(package_root / "prompts" / "simulation_guidelines.md")

    # Get task filter from environment
    task_filter = os.environ.get("TASK_FILTER")

    # Run benchmark
    run_benchmark(
        tasks_path=tasks_path,
        policy_path=policy_path,
        simulation_guidelines_path=simulation_guidelines_path,
        mcp_servers=args.mcp_servers,
        task_filter=task_filter
    )


if __name__ == "__main__":
    main()
