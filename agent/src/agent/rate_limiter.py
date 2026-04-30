"""
Simple Rate Limiter

Limits function calls to a maximum number per time period.
Automatically waits when the limit is reached and prints a message.
"""

import time
from collections import deque
from functools import wraps


class RateLimiter:
    """
    Simple rate limiter that tracks calls and enforces a maximum rate.

    When the rate limit is reached, it automatically waits until the next
    call can be made and prints a message to inform the user.
    """

    def __init__(self, max_calls: int, period: int):
        """
        Initialize the rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def __call__(self, func):
        """
        Decorator that applies rate limiting to a function.

        Args:
            func: Function to rate limit

        Returns:
            Wrapped function with rate limiting
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()

            # Remove old calls outside the time window
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()

            # Check if we need to wait
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] + self.period - now
                print(f"⏱️  Rate limit reached ({self.max_calls} calls per {self.period}s). Waiting {int(sleep_time + 1)} seconds...")
                time.sleep(sleep_time)
                # Remove the oldest call after waiting
                self.calls.popleft()

            # Record this call
            self.calls.append(time.time())
            return func(*args, **kwargs)

        return wrapper
