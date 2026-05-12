"""Provider-aware LLM client for hybrid reasoning tasks."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx

from app.core.config import settings

LLMTaskSize = Literal["light", "heavy"]


class LLMClient:
    def __init__(self) -> None:
        self.timeout = settings.llm_timeout_seconds

    def enabled(self) -> bool:
        if settings.llm_mode == "deterministic" or not settings.llm_enabled:
            return False
        return bool(
            settings.groq_api_key or 
            settings.openrouter_api_key or 
            (settings.ollama_base_url and "localhost" in settings.ollama_base_url)
        )

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        task_size: LLMTaskSize = "light",
    ) -> dict[str, Any] | None:
        text = await self.complete_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size=task_size,
        )
        if not text:
            return None
        return self._extract_json(text)

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        task_size: LLMTaskSize = "light",
    ) -> str | None:
        if not self.enabled():
            return None

        # Try all available providers in order of preference
        providers = []
        if settings.groq_api_key:
            providers.append("groq")
        if settings.openrouter_api_key:
            providers.append("openrouter")
        # Ollama is our local hero fallback
        if settings.ollama_base_url:
            providers.append("ollama")
            
        for provider in providers:
            url, headers, model = self._provider_request(provider, task_size)
            payload = {
                "model": model,
                "temperature": settings.llm_default_temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

            try:
                # Use a slightly longer timeout for heavy local models if needed, 
                # but respect the global setting as baseline
                current_timeout = self.timeout
                if provider == "ollama" and task_size == "heavy":
                    current_timeout = max(current_timeout, 90.0)

                async with httpx.AsyncClient(timeout=current_timeout) as client:
                    response = await client.post(
                        f"{url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    
                    if response.status_code == 429:
                        print(f"Rate limit hit for {provider}. Switching providers...")
                        continue
                        
                    response.raise_for_status()
                    
                    payload_json = response.json()
                    choices = payload_json.get("choices", [])
                    if not choices:
                        print(f"Empty choices from {provider}")
                        continue
                    message = choices[0].get("message", {})
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                    # Handle multimodal if needed
                    if isinstance(content, list):
                        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
                        joined = "\n".join(part for part in text_parts if part).strip()
                        if joined:
                            return joined
                    
            except httpx.HTTPError as exc:
                # Improved error reporting
                error_detail = str(exc)
                if not error_detail and hasattr(exc, "__class__"):
                    error_detail = exc.__class__.__name__
                
                print(f"LLM Error ({provider}): {error_detail}")
                if hasattr(exc, "response") and exc.response:
                    try:
                        print(f"Response body: {exc.response.text}")
                    except Exception:
                        pass
                continue # Try next provider
            except Exception as exc:
                print(f"Unexpected LLM Client Error ({provider}): {exc}")
                continue
                
        return None


    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _provider_request(provider: str, task_size: LLMTaskSize) -> tuple[str, dict[str, str], str]:
        if provider == "groq":
            # Using modern Llama 3.1 8b for light tasks, and the versatile model for heavy
            model = settings.groq_heavy_model if task_size == "heavy" else "llama-3.1-8b-instant"
            return (
                settings.groq_base_url,
                {
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                model,
            )
        
        if provider == "ollama":
            model = settings.ollama_heavy_model if task_size == "heavy" else settings.ollama_light_model
            return (
                settings.ollama_base_url,
                {
                    "Content-Type": "application/json",
                },
                model,
            )
            
        model = settings.openrouter_heavy_model if task_size == "heavy" and hasattr(settings, 'openrouter_heavy_model') else settings.openrouter_light_model
        return (
            settings.openrouter_base_url,
            {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
            model,
        )
