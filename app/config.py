from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --------------------
    # MongoDB
    # --------------------
    mongodb_uri: str
    mongodb_db_name: str = "maestros_community"

    # --------------------
    # Discord Bot
    # --------------------
    discord_bot_token: str
    discord_guild_id: str

    command_prefix: str = "!"
    bot_status: str = "Maestros Community"

    ceo_role_id: str = ""
    manager_role_id: str = ""
    member_role_id: str = ""
    application_pending_role_id: str = ""

    rules_category_id: str = ""
    rp_invite_channel_id: str = ""
    community_category_id: str = ""
    everyone_role_id: str = ""

    # --------------------
    # Application System Channels
    # --------------------
    application_channel_id: str = ""
    accepted_log_channel_id: str = ""
    rejected_log_channel_id: str = ""
    audit_log_channel_id: str = ""

    # --------------------
    # Server Invite
    # --------------------
    server_invite_link: str = ""

    # --------------------
    # FiveM Server
    # --------------------
    fivem_server_ip: str = ""
    fivem_server_name: str = "Maestros RP"
    fivem_stats_channel_id: str = ""
    member_count_channel_id: str = ""
    fivem_stats_text_channel_id: str = ""

    # --------------------
    # Discord OAuth
    # --------------------
    discord_client_id: str
    discord_client_secret: str
    discord_redirect_uri: str

    # --------------------
    # JWT
    # --------------------
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60  # 1 hour session

    # --------------------
    # API
    # --------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False  # IMPORTANT: should be False in production

    # --------------------
    # CORS
    # --------------------
    cors_origins: str

    # --------------------
    # Frontend
    # --------------------
    frontend_url: str = ""

    # --------------------
    # Admin
    # --------------------
    admin_discord_ids: str

    # --------------------
    # AI Moderation (Optional)
    # --------------------
    openai_api_key: str = ""
    huggingface_api_key: str = ""

    # --------------------
    # Rate Limiting
    # --------------------
    rate_limit_per_minute: int = 60

    # --------------------
    # Helpers
    # --------------------
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_ids_list(self) -> List[int]:
        return [int(i.strip()) for i in self.admin_discord_ids.split(",") if i.strip()]

    # --------------------
    # Pydantic Settings Config
    # --------------------
    model_config = SettingsConfigDict(
        env_file="env/.env",
        case_sensitive=False,  # <-- THIS FIXES YOUR AZURE ERROR
        extra="ignore",
    )


settings = Settings()

