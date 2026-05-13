from typing import AsyncGenerator, Dict, Tuple
from pathlib import Path
from uuid import UUID
from datetime import datetime
import asyncio
import logging
import yaml
from openai import AsyncOpenAI

from ..models.search import SearchQuery
from ..services.search_service import SearchService
from ..services.settings_service import SettingsService
from ..core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SKILL_FILE = Path(__file__).parent.parent / "skills" / "daily_briefing.md"


def _load_skill() -> Tuple[dict, str]:
    """Load and parse the daily_briefing.md skill file. Returns (config, prompt_template)."""
    try:
        text = SKILL_FILE.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.error(f"Skill file not found: {SKILL_FILE}")
        return {}, "Generate a thoughtful daily briefing for the user based on:\n{theme_sections}"

    if not text.startswith('---'):
        return {}, text.strip()

    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text.strip()

    try:
        config = yaml.safe_load(parts[1]) or {}
    except Exception as e:
        logger.error(f"Failed to parse skill frontmatter: {e}")
        config = {}

    return config, parts[2].strip()


class BriefingService:
    def __init__(self, search_service: SearchService, settings_service: SettingsService):
        self.search_service = search_service
        self.settings_service = settings_service
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate(self, user_id: UUID) -> AsyncGenerator[str, None]:
        """Generate a daily briefing by searching themed notes and streaming an AI response."""
        config, prompt_template = _load_skill()
        themes = config.get('themes', [])
        max_results_per_theme = config.get('max_results_per_theme', 4)

        # Fetch user settings and run all theme searches concurrently
        user_settings_task = self.settings_service.get_user_settings(user_id)
        search_tasks = [
            self.search_service.search(SearchQuery(
                query=theme['query'],
                user_id=user_id,
                top_k=max_results_per_theme
            ))
            for theme in themes
        ]

        gathered = await asyncio.gather(user_settings_task, *search_tasks)
        user_settings: Dict = gathered[0]
        theme_results = gathered[1:]

        # Build theme sections for the prompt
        theme_section_parts = []
        for theme, results in zip(themes, theme_results):
            if not results:
                continue
            lines = [f"[{theme['label'].upper()}]"]
            for r in results[:max_results_per_theme]:
                lines.append(f"\nFrom [[{r.title}]]:\n{r.content[:500]}")
            theme_section_parts.append("\n".join(lines))

        theme_sections_text = "\n\n---\n\n".join(theme_section_parts) or "(no relevant notes found)"

        personal_info = user_settings.get('personal_info', '') or ''
        memory = user_settings.get('memory', '') or ''
        memory_section = f"Memory:\n{memory}" if memory else ""

        system_prompt = prompt_template
        for placeholder, value in [
            ('{date}', datetime.now().strftime("%A, %B %d, %Y")),
            ('{personal_info}', personal_info or '(not provided)'),
            ('{memory_section}', memory_section),
            ('{theme_sections}', theme_sections_text),
        ]:
            system_prompt = system_prompt.replace(placeholder, value)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please give me my daily briefing."},
        ]

        # Mirror the GPT-5 vs older model handling from chat_service
        model_lower = settings.OPENAI_MODEL.lower()
        is_gpt5 = "gpt-5" in model_lower or "chatgpt-5" in model_lower

        api_params = {
            "model": settings.OPENAI_MODEL,
            "messages": messages,
            "stream": True,
        }

        if is_gpt5:
            try:
                api_params["max_completion_tokens"] = 1000
                stream = await self.openai_client.chat.completions.create(**api_params)
            except TypeError:
                logger.warning(f"SDK doesn't support max_completion_tokens for {settings.OPENAI_MODEL}")
                api_params.pop("max_completion_tokens", None)
                stream = await self.openai_client.chat.completions.create(**api_params)
        else:
            api_params.update({
                "temperature": 0.7,
                "top_p": 1,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "max_tokens": 1000,
            })
            stream = await self.openai_client.chat.completions.create(**api_params)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
