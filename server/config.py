import os
from typing import Optional

class Config:
    # 数据库配置
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aigc_omni")
    
    # 动态构建数据库URL
    @property
    def database_url(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
    
    # 如果需要直接设置DATABASE_URL，可以通过环境变量覆盖
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Redis配置
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_USER: Optional[str] = os.getenv("REDIS_USER", None)
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "false").lower() == "true"
    REDIS_QUEUE_PREFIX: str = os.getenv("REDIS_QUEUE_PREFIX", "tts_queue")
    
    # 动态构建REDIS_URL，优先使用环境变量，否则根据其他Redis配置构建
    @property
    def redis_url(self) -> str:
        # 如果直接设置了REDIS_URL环境变量，优先使用
        env_redis_url = os.getenv("REDIS_URL")
        if env_redis_url:
            return env_redis_url
        
        # 否则根据其他配置动态构建
        protocol = "rediss" if self.REDIS_SSL else "redis"
        
        # 构建认证部分，支持用户名和密码
        auth_part = ""
        if self.REDIS_USER and self.REDIS_USER.strip():
            if self.REDIS_PASSWORD and self.REDIS_PASSWORD.strip():
                auth_part = f"{self.REDIS_USER}:{self.REDIS_PASSWORD}@"
            else:
                auth_part = f"{self.REDIS_USER}@"
        elif self.REDIS_PASSWORD and self.REDIS_PASSWORD.strip():
            # 只有密码没有用户名的情况（向后兼容）
            auth_part = f":{self.REDIS_PASSWORD}@"
        
        return f"{protocol}://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # TTS模型配置
    MODEL_DIR: str = os.getenv('MODEL_DIR', 'checkpoints/Index-TTS-1.5-vLLM')
    GPU_MEMORY_UTILIZATION: float = float(os.getenv('GPU_MEMORY_UTILIZATION', '0.40'))
    
    # 服务器配置
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '6006'))
    
    # 文件存储配置
    AUDIO_OUTPUT_DIR: str = os.getenv('AUDIO_OUTPUT_DIR', './storage/audio')
    TEXT_STORAGE_DIR: str = os.getenv('TEXT_STORAGE_DIR', './storage/tasks')
    SRT_OUTPUT_DIR: str = os.getenv('SRT_OUTPUT_DIR', './storage/srt')
    
    # 文本长度限制
    MAX_ONLINE_TEXT_LENGTH: int = int(os.getenv('MAX_ONLINE_TEXT_LENGTH', '300'))
    MAX_LONG_TEXT_LENGTH: int = int(os.getenv('MAX_LONG_TEXT_LENGTH', '50000'))
    
    # 工作器配置
    WORKER_POLL_INTERVAL: float = float(os.getenv('WORKER_POLL_INTERVAL', '1.0'))
    MAX_RETRY_COUNT: int = int(os.getenv('MAX_RETRY_COUNT', '3'))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', None)
    LOG_MAX_SIZE: int = int(os.getenv('LOG_MAX_SIZE', '10').replace('MB', ''))  # MB
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # API配置
    API_KEY: Optional[str] = os.getenv('API_KEY')
    ALLOWED_ORIGINS: list = os.getenv('ALLOWED_ORIGINS', '*').split(',')
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
    
    # 监控配置
    ENABLE_METRICS: bool = os.getenv('ENABLE_METRICS', 'false').lower() == 'true'
    METRICS_PORT: int = int(os.getenv('METRICS_PORT', '8000'))
    HEALTH_CHECK_INTERVAL: int = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))  # 秒
    
    # 清理配置
    CLEANUP_INTERVAL: int = int(os.getenv('CLEANUP_INTERVAL', '3600'))  # 秒
    CLEANUP_OLD_TASKS_DAYS: int = int(os.getenv('CLEANUP_OLD_TASKS_DAYS', '7'))
    CLEANUP_OLD_AUDIO_DAYS: int = int(os.getenv('CLEANUP_OLD_AUDIO_DAYS', '3'))

    @classmethod
    def validate(cls):
        """验证配置"""
        instance = cls()
        
        # 验证必需的配置
        if not instance.MYSQL_HOST:
            raise ValueError("MYSQL_HOST is required")
        
        if not instance.REDIS_HOST:
            raise ValueError("REDIS_HOST is required")
        
        # 验证端口范围
        if not (1 <= instance.MYSQL_PORT <= 65535):
            raise ValueError("MYSQL_PORT must be between 1 and 65535")
        
        if not (1 <= instance.REDIS_PORT <= 65535):
            raise ValueError("REDIS_PORT must be between 1 and 65535")
        
        if not (1 <= instance.PORT <= 65535):
            raise ValueError("PORT must be between 1 and 65535")

# 创建全局配置实例
config = Config()
config.validate()