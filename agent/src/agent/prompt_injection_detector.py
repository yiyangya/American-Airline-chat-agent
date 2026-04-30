"""
Prompt Injection Detection using Lakera Guard.

Provides detection for prompt injection attacks using Lakera Guard API
or fallback local detection.
"""

import time
import re
import os
from typing import Dict, Any, Optional, Tuple
from enum import Enum


class InjectionType(Enum):
    NONE = "none"
    DIRECT = "direct"
    INDIRECT = "indirect"
    MAGIC_TOKEN = "magic_token"
    ROLE_PLAYING = "role_playing"
    INSTRUCTION_OVERRIDE = "instruction_override"


class PromptInjectionDetector:
    """Detects prompt injection attempts using Lakera Guard API or local patterns."""
    
    # Patterns for common injection techniques (fallback)
    INJECTION_PATTERNS = [
        # Magic tokens
        (r'##MAGIC##|###MAGIC###', InjectionType.MAGIC_TOKEN),
        
        # Instruction overrides
        (r'ignore (all|previous|above) (instructions?|rules?|policies?)', InjectionType.INSTRUCTION_OVERRIDE, re.IGNORECASE),
        (r'(forget|disregard|ignore) (everything|all|previous)', InjectionType.INSTRUCTION_OVERRIDE, re.IGNORECASE),
        (r'new instructions?:', InjectionType.INSTRUCTION_OVERRIDE, re.IGNORECASE),
        
        # Role playing attacks
        (r'you are (now|currently|a) (developer|admin|system|root)', InjectionType.ROLE_PLAYING, re.IGNORECASE),
        (r'act as (if you are|like|an?)\s+\w+', InjectionType.ROLE_PLAYING, re.IGNORECASE),
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        use_lakera: bool = True,
        fallback_to_local: bool = True
    ):
        """
        Initialize detector.
        
        Args:
            api_key: Lakera Guard API key (or from LAKERA_API_KEY env var)
            use_lakera: Whether to use Lakera Guard API
            fallback_to_local: Fall back to local detection if Lakera fails
        """
        self.api_key = api_key or os.getenv("LAKERA_API_KEY")
        self.use_lakera = use_lakera and self.api_key is not None
        self.fallback_to_local = fallback_to_local
        
        if self.use_lakera:
            try:
                import requests
                self.requests = requests
            except ImportError:
                print("Warning: requests not installed, falling back to local detection")
                self.use_lakera = False

    def detect_lakera(self, text: str) -> Tuple[bool, float, float, Dict[str, Any]]:
        """
        Detect prompt injection using Lakera Guard API.
        
        Args:
            text: Text to check    
        Returns:
            (is_injection, confidence, latency_ms, metadata)
        """
        import requests
        
        start_time = time.time()
        
        try:
            response = self.requests.post(
                "https://api.lakera.ai/v2/guard",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "messages": [
                        {
                            "content": text,
                            "role": "user"
                        }
                    ]
                },
                timeout=5.0
            )
            response.raise_for_status()
            
            result = response.json()
            latency_ms = (time.time() - start_time) * 1000
            
            # Lakera v2/guard response format (based on API docs):
            # {
            #   "flagged": true/false,
            #   "request_uuid": "...",
            #   "categories": {...}  # Optional detailed breakdown
            # }
            
            is_injection = result.get("flagged", False)
            confidence = 1.0 if is_injection else 0.0
            
            # Try to extract confidence from categories if available
            categories = result.get("categories", {})
            if categories and is_injection:
                # Use highest category score as confidence
                scores = [v for v in categories.values() if isinstance(v, (int, float))]
                if scores:
                    confidence = max(scores) / 100.0 if max(scores) > 1.0 else max(scores)
            
            metadata = {
                "method": "lakera",
                "request_uuid": result.get("request_uuid"),
                "categories": categories
            }
            
            return is_injection, confidence, latency_ms, metadata
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            
            if self.fallback_to_local:
                # Fallback to local detection
                is_injected, injection_type, local_confidence = self.detect_local(text)
                return is_injected, local_confidence, latency_ms, {"error": str(e), "fallback": True}
            else:
                raise RuntimeError(f"Lakera API call failed: {e}")


    def detect_local(self, text: str) -> Tuple[bool, InjectionType, float]:
        """
        Local detection using pattern matching (fallback).
        
        Args:
            text: Text to check
            
        Returns:
            (is_injection, injection_type, confidence)
        """
        # Check patterns
        for pattern, injection_type, *flags in self.INJECTION_PATTERNS:
            regex_flags = flags[0] if flags else 0
            if re.search(pattern, text, regex_flags):
                return True, injection_type, 0.9
        
        return False, InjectionType.NONE, 0.0
    
    def detect(self, text: str) -> Tuple[bool, float, float, Dict[str, Any]]:
        """
        Detect prompt injection (main entry point).
        
        Args:
            text: Text to check
            
        Returns:
            (is_injection, confidence, latency_ms, metadata)
        """
        if self.use_lakera:
            return self.detect_lakera(text)
        else:
            start_time = time.time()
            is_injected, injection_type, confidence = self.detect_local(text)
            latency_ms = (time.time() - start_time) * 1000
            return is_injected, confidence, latency_ms, {
                "method": "local",
                "injection_type": injection_type.value
            }
    
    def sanitize(self, text: str) -> str:
        """
        Sanitize text by removing suspicious patterns.
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text
        """
        sanitized = text
        
        # Remove magic tokens
        sanitized = re.sub(r'##MAGIC##|###MAGIC###', '', sanitized, flags=re.IGNORECASE)
        
        # Remove instruction tags
        sanitized = re.sub(r'<instructions?>.*?</instructions?>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r'<system>.*?</system>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        return sanitized.strip()


class PromptInjectionError(Exception):
    """Raised when prompt injection is detected."""
    pass