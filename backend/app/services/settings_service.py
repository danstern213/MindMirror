from typing import Dict, Any, Optional
from uuid import UUID
from supabase import Client
import logging

from ..core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class SettingsService:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    async def get_user_settings(self, user_id: UUID) -> Dict[str, Any]:
        """Get user settings, creating default if none exist."""
        try:
            response = self.supabase.table('user_settings')\
                .select('*')\
                .eq('user_id', str(user_id))\
                .single()\
                .execute()
            
            if not response.data:
                # Create default settings
                default_settings = {
                    'user_id': str(user_id),
                    'personal_info': '',
                    'memory': '',
                    'model': settings.OPENAI_MODEL,
                    'openai_api_key': None,  # User can provide their own key
                    'excluded_folders': [],
                    'suggested_prompts': [
                        "What are three small wins I can aim for today?",
                        "Help me reflect on my day. What went well, and what could have gone better?",
                        "Write a draft of my weekly review for this week",
                        "Summarize me as a person, including my strengths and growth opportunities",
                        "Let's gratitude journal together",
                        "Generate 5 creative writing prompts for me.",
                        "Summarize a concept or book I wrote about recently",
                        "Ask me a relevant thought-provoking question to journal about"
                    ]
                }
                
                response = self.supabase.table('user_settings')\
                    .insert(default_settings)\
                    .execute()
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"Error creating default settings: {response.error}")
                    return default_settings
                
                return response.data[0]
            
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching user settings: {e}")
            return {
                'user_id': str(user_id),
                'personal_info': '',
                'memory': '',
                'model': settings.OPENAI_MODEL
            }

    async def update_user_settings(
        self,
        user_id: UUID,
        settings_update: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update user settings."""
        try:
            # Remove any fields that shouldn't be updated
            settings_update.pop('user_id', None)
            settings_update.pop('id', None)
            
            response = self.supabase.table('user_settings')\
                .update(settings_update)\
                .eq('user_id', str(user_id))\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error updating settings: {response.error}")
                return None
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return None 