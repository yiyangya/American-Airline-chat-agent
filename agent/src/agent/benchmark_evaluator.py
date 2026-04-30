"""
Evaluator for Tau2 Benchmark Tasks

Evaluates agent performance against expected actions and natural language assertions.
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .config import benchmark_nl_evaluation_llm




# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

class Task:
    """A benchmark task (ignores extra fields from JSON)."""
    def __init__(self, id, description=None, user_scenario=None, ticket=None,
                 initial_state=None, evaluation_criteria=None, **kwargs):
        self.id = id
        self.description = description
        self.user_scenario = user_scenario
        self.ticket = ticket
        self.initial_state = initial_state
        self.evaluation_criteria = evaluation_criteria


@dataclass
class EvaluationResult:
    """Result of evaluating a task."""
    task_id: str
    success: bool
    actions_matched: bool
    nl_assertions_passed: bool
    details: List[str]
    conversation: List[Dict[str, Any]]


# ============================================================================
# EVALUATOR CLASS
# ============================================================================

class Evaluator:
    """Evaluates agent performance against task criteria."""

    def evaluate_task(
        self,
        task: Task,
        conversation: List[Dict[str, Any]]
    ) -> EvaluationResult:
        """
        Evaluate a task against the conversation between agent and user.

        Args:
            task: The task to evaluate
            conversation: Full conversation history

        Returns:
            Evaluation result
        """
        details = []
        actions_matched = True
        nl_assertions_passed = True

        # Evaluate actions if specified
        if task.evaluation_criteria and task.evaluation_criteria.get('actions'):
            action_result = self._evaluate_actions(
                task.evaluation_criteria['actions'],
                conversation
            )
            actions_matched = action_result['passed']
            details.extend(action_result['details'])

        # Evaluate NL assertions if specified
        if task.evaluation_criteria and task.evaluation_criteria.get('nl_assertions'):
            nl_result = self._evaluate_nl_assertions(
                task.evaluation_criteria['nl_assertions'],
                conversation
            )
            nl_assertions_passed = nl_result['passed']
            details.extend(nl_result['details'])

        success = actions_matched and nl_assertions_passed

        return EvaluationResult(
            task_id=task.id,
            success=success,
            actions_matched=actions_matched,
            nl_assertions_passed=nl_assertions_passed,
            details=details,
            conversation=conversation
        )

    def _evaluate_actions(
        self,
        expected_actions: List[Dict[str, Any]],
        conversation: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate if expected actions were performed by checking tool calls in conversation.

        Args:
            expected_actions: List of expected actions
            conversation: Full conversation history

        Returns:
            Dictionary with 'passed' and 'details' keys
        """
        results = []

        for expected in expected_actions:
            # Look for assistant messages with tool_calls
            found = False

            for msg in conversation:
                if msg.get('role') == 'assistant' and msg.get('tool_calls'):
                    for tool_call in msg['tool_calls']:
                        tool_name = tool_call['function']['name']

                        # Parse arguments
                        args_str = tool_call['function']['arguments']
                        if isinstance(args_str, str):
                            tool_args = json.loads(args_str)
                        else:
                            tool_args = args_str

                        # Check if this matches the expected action
                        if (tool_name == expected['name'] and
                            self._match_arguments(
                                tool_args,
                                expected['arguments'],
                                expected.get('compare_args')
                            )):
                            found = True
                            break

                if found:
                    break

            results.append({
                'found': found,
                'detail': (
                    f"✅ Action '{expected['name']}' performed"
                    if found
                    else f"❌ Action '{expected['name']}' with args {json.dumps(expected['arguments'])} not performed"
                )
            })

        return {
            'passed': all(r['found'] for r in results),
            'details': [r['detail'] for r in results]
        }

    def _match_arguments(
        self,
        actual: Dict[str, Any],
        expected: Dict[str, Any],
        compare_args: Optional[List[str]] = None
    ) -> bool:
        """
        Check if actual arguments match expected arguments.
        If compare_args specified, only compare those fields; otherwise compare all expected fields.

        Args:
            actual: Actual arguments passed to tool
            expected: Expected arguments
            compare_args: Optional list of fields to compare

        Returns:
            True if arguments match
        """
        keys_to_compare = compare_args if compare_args else list(expected.keys())
        return all(
            self._values_equal(actual.get(key), expected[key])
            for key in keys_to_compare
        )

    def _values_equal(self, actual: Any, expected: Any) -> bool:
        """Equality that tolerates JSON-encoded strings on the actual side."""
        if actual == expected:
            return True
        if isinstance(actual, str) and isinstance(expected, (list, dict)):
            try:
                return json.loads(actual) == expected
            except (json.JSONDecodeError, TypeError):
                return False
        return False

    def _evaluate_nl_assertions(
        self,
        nl_assertions: List[str],
        conversation: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate natural language assertions using LLM-as-a-judge.
        This evaluates whether the conversation satisfies the expected outcomes.

        Args:
            nl_assertions: List of natural language assertions to check
            conversation: Full conversation history

        Returns:
            Dictionary with 'passed' and 'details' keys
        """
        if not nl_assertions:
            return {'passed': True, 'details': []}

        # Format conversation for LLM (only user and assistant text messages)
        trajectory_lines = []
        for msg in conversation:
            role = msg.get('role')
            content = msg.get('content')

            if role in ('assistant', 'user') and content and isinstance(content, str):
                trajectory_lines.append(f"{role}: {content}")

        trajectory_str = "\n".join(trajectory_lines)

        system_prompt = """TASK
- You will be given a list of expected outcomes and a conversation that was collected during a test case run.
- The conversation is between an agent and a customer.
- Your job is to evaluate whether the agent satisfies each of the expected outcomes.
- Grade each expected outcome individually.

FORMAT
- Your response should be a JSON object with the following fields:
- `reasoning`: a short explanation for your classification
- `metExpectation`: `true` if the agent satisfies the expected outcomes, `false` otherwise
- `expectedOutcome`: repeat the expectation from the input that you are grading

Example response structure:
{
    "results": [
        {
            "expectedOutcome": "<one of the expected outcomes from the input>",
            "reasoning": "<reasoning trace>",
            "metExpectation": <false or true>
        }
    ]
}"""

        user_prompt = f"""conversation:
{trajectory_str}

expectedOutcomes:
{json.dumps(nl_assertions)}"""

        try:
            response = benchmark_nl_evaluation_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])

            response_text = response.choices[0].message.content

            # Parse JSON response
            try:
                result_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block if present
                if "```json" in response_text:
                    json_str = response_text.split("```json")[1].split("```")[0].strip()
                    result_data = json.loads(json_str)
                elif "```" in response_text:
                    json_str = response_text.split("```")[1].split("```")[0].strip()
                    result_data = json.loads(json_str)
                else:
                    raise

            results = result_data.get('results', [])

            details = [
                (
                    f"✅ NL assertion: \"{result['expectedOutcome']}\" - {result['reasoning']}"
                    if result['metExpectation']
                    else f"❌ NL assertion: \"{result['expectedOutcome']}\" - {result['reasoning']}"
                )
                for result in results
            ]

            all_met = all(result['metExpectation'] for result in results)

            return {'passed': all_met, 'details': details}

        except Exception as error:
            print(f"Error evaluating NL assertions: {error}")
            return {
                'passed': False,
                'details': [f"⚠️  Failed to evaluate: \"{assertion}\"" for assertion in nl_assertions]
            }
