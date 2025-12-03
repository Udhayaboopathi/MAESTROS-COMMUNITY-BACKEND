from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # MongoDB
    mongodb_uri: str
    mongodb_db_name: str = "maestros_community"
    
    # Discord Bot
    discord_bot_token: str
    discord_guild_id: str
    command_prefix: str = "!"
    bot_status: str = "Maestros Community"
    ceo_role_id: str = ""
    manager_role_id: str = ""
    member_role_id: str = ""  # Regular member role, not management
    
    # Discord OAuth
    discord_client_id: str
    discord_client_secret: str
    discord_redirect_uri: str
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True
    
    # CORS
    cors_origins: str = "http://localhost:3000"
    
    # Frontend URL for OAuth redirects
    frontend_url: str = "http://localhost:3000"
    
    # Admin
    admin_discord_ids: str
    
    # AI Moderation
    openai_api_key: str = ""
    huggingface_api_key: str = ""
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(',')]
    
    @property
    def admin_ids_list(self) -> List[str]:
        return [id.strip() for id in self.admin_discord_ids.split(',')]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
