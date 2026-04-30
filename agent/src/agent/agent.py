"""
Tool-Calling Agent

This is the main agent implementation that:
- Maintains conversation history
- Calls the LLM to reason about the next step
- Executes tools when the LLM requests them
- Continues until the LLM provides a text response
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .tool_manager import ToolManager
from .config import TAU2_DOMAIN_DATA_PATH, agent_llm
import os 
from .prompt_injection_detector import PromptInjectionDetector, PromptInjectionError

@dataclass
class ToolCall:
    """Represents a tool call from the LLM"""
    id: str
    type: str
    function: Dict[str, Any]


@dataclass
class ModelMessage:
    """Represents a message in the conversation history"""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


class ToolCallingAgent:
    """
    A tool-calling agent that helps users by calling tools via MCP servers.

    The agent maintains a conversation history and repeatedly:
    1. Calls the LLM to decide what to do next
    2. Executes any tool calls the LLM requested
    3. Adds tool results back to the conversation

    This continues until the LLM provides a final text response without tool calls.
    """

    def __init__(
        self,
        tool_manager: ToolManager,
        max_steps: int = 5
    ):
        """
        Initialize the agent.

        Args:
            tool_manager: Manager for MCP tools
            max_steps: Maximum reasoning steps before giving up
        """
        self.tool_manager = tool_manager
        self.max_steps = max_steps
        self.messages: List[Dict[str, Any]] = []
        self.logger = logging.getLogger("agent.messages")
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()
        log_path = Path("messages.log")
        handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Add system prompt to start the conversation
        self._add_to_context({
            "role": "system",
            "content": self._create_system_prompt()
        })
        self.injection_detector = PromptInjectionDetector(
            api_key=None,
            use_lakera=True,
            fallback_to_local=True
        )
        
        # Action tracking for session
        self.action_history: List[Dict[str, Any]] = []


    def execute(self, task: str) -> str:
        """
        Execute a task using the tool-calling loop.

        Args:
            task: The user's request or question

        Returns:
            The agent's final response

        Raises:
            Exception: If max steps reached without completing the task
        """
        # Check for prompt injection in user input
        if self.injection_detector:
            is_injection, confidence, latency_ms, metadata = self.injection_detector.detect(task)

            if is_injection:
                self.logger.warning(f"Prompt injection detected.")
                raise PromptInjectionError(
                    f"Your request was flagged as potentially malicious."
                    f"Please rephrase your request."
                )

        self._add_to_context({"role": "user", "content": task})
        
        # Check if user is asking about actions taken
        action_query_keywords = [
            "what have you done",
            "show me what you've done",
            "list actions",
            "actions taken",
            "what actions",
            "what did you do",
            "show actions",
            "what have you completed"
        ]
        is_action_query = any(keyword in task.lower() for keyword in action_query_keywords)
        
        # If asking about actions, inject action history as context
        if is_action_query and self.action_history:
            action_summary = "\n".join(self.get_action_history())
            self._add_to_context({
                "role": "system",
                "content": f"ACTION HISTORY FOR THIS SESSION:\n{action_summary}\n\nWhen responding to the user's query about actions, refer only to the actions listed above. Do not claim actions were taken if they are not in this list. Only report actions that actually executed successfully."
            })

        # Agent loop
        for step in range(1, self.max_steps + 1):
            response = self._reason()

            # Check if LLM provided text response
            if response.get("text"):
                self._add_to_context({
                    "role": "assistant",
                    "content": response["text"]
                })

            # Check if LLM wants to use tools
            use_tools = response.get("tool_calls") and len(response["tool_calls"]) > 0

            if use_tools:
                # Add assistant message with tool calls
                self._add_to_context({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": response["tool_calls"]
                })

                # Execute tool calls and add results
                for tool_call in response["tool_calls"]:
                    result = self._act(tool_call)
                    self._add_to_context(result)

            # Exit condition: text response without tool calls
            if response.get("text") and not use_tools:
                return response["text"]

        # Max steps reached
        raise RuntimeError(
            f"Maximum steps ({self.max_steps}) reached without completing the task"
        )

    def _reason(self) -> Dict[str, Any]:
        """
        Call the LLM to reason about the next step.

        Returns:
            Dictionary with 'text' and/or 'tool_calls'
        """
        tools = self.tool_manager.get_tools()

        try:
            response = agent_llm(
                self.messages,
                tools
            )

            message = response.choices[0].message

            # Extract text and tool calls
            result = {
                "text": message.content if hasattr(message, 'content') else None,
                "tool_calls": []
            }

            # Parse tool calls if present
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            return result

        except Exception as e:
            self.logger.error(json.dumps({"error": str(e)}))
            raise RuntimeError("Failed to call LLM") from e

    def _act(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool_call: Tool call information from the LLM

        Returns:
            Tool message to add to conversation history
        """
        tool_name = tool_call["function"]["name"]
        tool_args_str = tool_call["function"]["arguments"]

        try:
            # Parse arguments (they come as a JSON string)
            tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str

            # Execute the tool
            result = self.tool_manager.execute_tool(tool_name, tool_args)

            if self.injection_detector:
                is_injection, confidence, latency_ms, metadata = self.injection_detector.detect(result)
                
                if is_injection:
                    self.logger.warning(
                        f"Indirect prompt injection detected in tool '{tool_name}' result "
                        f"(confidence: {confidence:.2f})"
                    )
                    # Sanitize the result instead of blocking
                    result = self.injection_detector.sanitize(result)
                    # Optionally add a warning marker
                    result = f"[⚠️ Content from external source, potentially unsafe]\n{result}"


            # Record successful action
            action_summary = self._parse_action_result(tool_name, tool_args, result, success=True)
            self._record_action(tool_name, tool_args, success=True, result_summary=action_summary)

            return {
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call["id"]
            }

        except Exception as error:
            error_message = str(error)

            # Record failed action
            action_summary = self._parse_action_result(tool_name, tool_args, error_message, success=False)
            self._record_action(tool_name, tool_args, success=False, result_summary=action_summary, error_message=error_message)

            return {
                "role": "tool",
                "content": f"Error: {error_message}",
                "tool_call_id": tool_call["id"]
            }

    def _add_to_context(self, message: Dict[str, Any]) -> None:
        """
        Add a message to the conversation history.

        Args:
            message: Message dictionary to add
        """
        self.messages.append(message)
        self._log_message_to_context(message)

    def _log_message_to_context(self, message: Dict[str, Any]) -> None:
        """Persist message history to the log file."""
        recorded = {key: value for key, value in message.items() if value is not None}
        try:
            self.logger.info(json.dumps(recorded, ensure_ascii=False))
        except Exception:
            # Fallback: ensure logging doesn't break agent flow
            self.logger.info(str(recorded))

    def disconnect(self):
        """Disconnect from all MCP servers"""
        self.tool_manager.disconnect()

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get the full conversation history"""
        return self.messages
    
    def get_action_history(self) -> List[str]:
        """
        Get formatted list of actions taken in this session.
        
        Returns:
            List of formatted action descriptions. Returns list with single message
            if no actions have been taken.
        """
        if not self.action_history:
            return ["No actions have been taken in this session yet."]
        
        formatted_actions = []
        for idx, action in enumerate(self.action_history, 1):
            status = "✓" if action["success"] else "✗"
            summary = action["result_summary"]
            
            # Format timestamp (just time portion for readability)
            timestamp = action.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S")
                except (ValueError, AttributeError):
                    time_str = ""
            else:
                time_str = ""
            
            if time_str:
                formatted_actions.append(f"{idx}. [{time_str}] {status} {summary}")
            else:
                formatted_actions.append(f"{idx}. {status} {summary}")
        
        return formatted_actions

    def _create_system_prompt(self) -> str:
        """
        Create the system prompt with instructions and policy.

        Returns:
            System prompt string
        """
        # Load policy from file
        policy_file = Path(__file__).parent / TAU2_DOMAIN_DATA_PATH / "policy.md"
        try:
            with open(policy_file, "r") as f:
                policy = f.read()
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Policy file not found at {policy_file}. "
                "Please ensure the policy is available before running the agent."
            ) from exc

        # Load system prompt template
        template_path = Path(__file__).parent / "prompts" / "system_prompt.txt"
        try:
            template = template_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"System prompt template not found at {template_path}. "
                "Please ensure the template file is available before running the agent."
            ) from exc

        return template.replace("$POLICY", policy)
    
    def _parse_action_result(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        result: str, 
        success: bool
    ) -> str:
        """
        Parse tool result to create a human-readable action summary.
        
        Args:
            tool_name: Name of the tool executed
            tool_args: Arguments passed to the tool
            result: Result from tool execution (or error message if failed)
            success: Whether execution succeeded
            
        Returns:
            Human-readable summary of the action
        """
        if not success:
            # Extract meaningful error information
            if "Policy violation" in result:
                return f"Failed: {result.split('.')[0]}"
            elif "requires explicit user confirmation" in result:
                return "Failed: Confirmation required but not provided"
            elif "Error:" in result:
                return f"Failed: {result.replace('Error: ', '')[:100]}"
            else:
                return f"Failed: {result[:100]}"
        
        # Parse successful results based on tool type
        try:
            if tool_name == "book_reservation":
                # Result is JSON with reservation details
                reservation_data = json.loads(result)
                reservation_id = reservation_data.get("reservation_id", "unknown")
                return f"Created reservation {reservation_id}"
                
            elif tool_name == "cancel_reservation":
                # Result is JSON with reservation details
                reservation_data = json.loads(result)
                reservation_id = reservation_data.get("reservation_id", "unknown")
                status = reservation_data.get("status", "")
                if status == "cancelled":
                    return f"Cancelled reservation {reservation_id}"
                else:
                    return f"Processed cancellation request for {reservation_id}"
                    
            elif tool_name == "update_reservation_baggages":
                # Result is JSON with reservation details
                reservation_data = json.loads(result)
                reservation_id = reservation_data.get("reservation_id", "unknown")
                total_baggages = reservation_data.get("total_baggages", 0)
                return f"Updated baggage to {total_baggages} items for reservation {reservation_id}"
                
            elif tool_name == "update_reservation_flights":
                # Result is JSON with reservation details
                reservation_data = json.loads(result)
                reservation_id = reservation_data.get("reservation_id", "unknown")
                return f"Updated flights in reservation {reservation_id}"
                
            elif tool_name == "send_certificate":
                # Result is a string message
                if "added to user" in result and "amount" in result:
                    # Extract amount and user_id from result
                    parts = result.split("amount ")
                    if len(parts) > 1:
                        amount_part = parts[1].split()[0] if parts[1].split() else "unknown"
                        user_id = tool_args.get("user_id", "unknown")
                        return f"Issued ${amount_part} certificate to user {user_id}"
                return "Issued certificate"
                
            elif tool_name in ["get_reservation_details", "get_user_details", "search_direct_flight", 
                              "search_onestop_flight", "get_flight_status", "list_all_airports", "calculate"]:
                # These are read-only queries, less critical but still tracked
                return f"Retrieved information: {tool_name}"
                
            elif tool_name == "update_reservation_passengers":
                reservation_data = json.loads(result)
                reservation_id = reservation_data.get("reservation_id", "unknown")
                return f"Updated passenger information for reservation {reservation_id}"
                
            else:
                # Generic success message
                return f"Executed {tool_name}"
                
        except (json.JSONDecodeError, KeyError, AttributeError):
            # If parsing fails, create generic summary
            if success:
                return f"Executed {tool_name} successfully"
            else:
                return f"Failed to execute {tool_name}"
    
    def _record_action(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
        result_summary: str,
        error_message: Optional[str] = None
    ) -> None:
        """
        Record an action in the action history.
        
        Args:
            tool_name: Name of the tool executed
            tool_args: Arguments passed to the tool
            success: Whether execution succeeded
            result_summary: Human-readable summary
            error_message: Error message if failed
        """
        action_record = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "success": success,
            "result_summary": result_summary,
            "timestamp": datetime.now().isoformat(),
        }
        
        if error_message:
            action_record["error_message"] = error_message
            
        self.action_history.append(action_record)
