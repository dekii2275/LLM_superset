import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.api.ai import ai_chat
from app.schemas.ai import AIChatRequest
from app.services import ai_settings


class AISettingsTests(unittest.TestCase):
    def setUp(self):
        self.test_engine = create_engine("sqlite://", poolclass=StaticPool)
        self.engine_patch = patch.object(ai_settings, "engine", self.test_engine)
        self.ready_patch = patch.object(ai_settings, "_table_ready", False)
        self.engine_patch.start()
        self.ready_patch.start()

    def tearDown(self):
        self.ready_patch.stop()
        self.engine_patch.stop()
        self.test_engine.dispose()

    def test_setting_defaults_on_and_persists_changes(self):
        self.assertTrue(ai_settings.is_llm_enabled())
        ai_settings.set_llm_enabled(False)
        self.assertFalse(ai_settings.is_llm_enabled())
        ai_settings.set_llm_enabled(True)
        self.assertTrue(ai_settings.is_llm_enabled())

class AIChatSettingTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_is_rejected_when_llm_is_disabled(self):
        with patch("app.api.ai.is_llm_enabled", return_value=False):
            with self.assertRaises(HTTPException) as error:
                await ai_chat(AIChatRequest(message="How many taxi trips were there?"))
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
