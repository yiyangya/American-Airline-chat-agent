"""
Model Configuration

This file configures which LLM models to use for different tasks.
You can change the model string to use different providers (OpenAI, Anthropic, Google, etc.)
via LiteLLM, which provides a unified interface.
"""

from litellm import completion
from .rate_limiter import RateLimiter

#################################
# Model Configuration
#################################

# LiteLLM supports many providers - just change the model string:
# - OpenAI: "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"
# - Anthropic: "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"
# - Google: "gemini/gemini-2.0-flash-exp", "gemini/gemini-1.5-pro"
# See: https://docs.litellm.ai/docs/providers

# Rate limiter: 5 calls per 60 seconds (1 minute)
rate_limiter = RateLimiter(max_calls=60, period=60)


@rate_limiter
def agent_llm(messages, tools):
    """
    Get the LLM completion function for the agent model.

    Rate limited to 5 calls per minute to avoid API throttling.
    Will automatically wait when limit is reached.

    Args:
        messages: List of conversation messages
        tools: List of available tools

    Returns:
        LLM completion response
    """
    has_tools = len(tools) > 0
    return completion(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools if has_tools else None,
                tool_choice="auto" if has_tools else None,
                temperature=0.0,
            )

# Benchmark functions - by default uses same model as agent but without tool calling
def benchmark_user_simulation_llm(messages):
    return agent_llm(messages, tools=[])


@rate_limiter
def benchmark_nl_evaluation_llm(messages):
    return agent_llm(messages, tools=[])



#################################
# Tau2 data configuration for benchmarking
#################################

TAU2_DOMAIN = "airline"  # "airline" | "mock"
TAU2_DOMAIN_DATA_PATH = f"../../../data/{TAU2_DOMAIN}/"
