from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://tahqaq:tahqaq@localhost:5432/tahqaq"

    # local | openai | hash  (hash is a deterministic stub for unit tests without network)
    embedder: str = "local"
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    openai_api_key: str = ""
    openai_embed_model: str = "text-embedding-3-small"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    # LLM provider chain for the explanation / transcription step (never for grading).
    # gemini | groq | openrouter | cerebras | anthropic | none  — fallbacks tried on 429/5xx/timeouts.
    llm_provider: str = "none"
    llm_fallbacks: str = ""
    llm_model: str = ""          # overrides the primary provider's default model
    llm_timeout: float = 15.0
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""

    review_webhook_url: str = ""
    # assistant voice (text to speech): Groq Orpheus voices are used when set (model terms accepted in the Groq console)
    tts_groq_voice_ar: str = ""
    tts_groq_voice_en: str = ""
    tts_gemini_voice: str = "Charon"   # a calm male voice for «سند»
    tts_gemini: bool = False           # Gemini TTS free tier allows only 10 requests a day: off by default
    tts_piper_dir: str = ""            # folder with the Piper voices (Docker: /opt/piper; local: ~/.cache/piper)
    tts_piper_voice_ar: str = "ar_JO-kareem-medium"
    tts_piper_voice_en: str = "en_US-ryan-medium"
    cors_origins: str = "http://localhost:3000"

    max_input_chars: int = 2000
    max_image_bytes: int = 10 * 1024 * 1024

    # Confidence thresholds (documented on the Sources page)
    threshold_verified: int = 90
    threshold_partial: int = 75
    threshold_uncertain: int = 50

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
