import os
from typing import Optional

class Config:
    """增强型TTS API服务器配置类"""
    
    # MySQL数据库配置
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "mysql+aiomysql://tts_user:tts_password@localhost:3306/tts_db"
    )
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "tts_user")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "tts_password")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "tts_db")
    
    # Redis配置
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "false").lower() == "true"
    REDIS_QUEUE_PREFIX: str = os.getenv("REDIS_QUEUE_PREFIX", "tts_queue")
    
    # TTS模型配置
    MODEL_DIR: str = os.getenv('MODEL_DIR', '/path/to/IndexTeam/Index-TTS')
    GPU_MEMORY_UTILIZATION: float = float(os.getenv('GPU_MEMORY_UTILIZATION', '0.25'))
    
    # 服务器配置
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '11996'))
    
    # 文件存储配置
    AUDIO_OUTPUT_DIR: str = os.getenv('AUDIO_OUTPUT_DIR', './storage/audio')
    TEXT_STORAGE_DIR: str = os.getenv('TEXT_STORAGE_DIR', './storage/tasks')
    SRT_OUTPUT_DIR: str = os.getenv('SRT_OUTPUT_DIR', './storage/srt')
    
    # 任务配置
    MAX_ONLINE_TEXT_LENGTH: int = int(os.getenv('MAX_ONLINE_TEXT_LENGTH', '300'))
    MAX_LONG_TEXT_LENGTH: int = int(os.getenv('MAX_LONG_TEXT_LENGTH', '50000'))
    
    # 处理器配置
    WORKER_POLL_INTERVAL: float = float(os.getenv('WORKER_POLL_INTERVAL', '1.0'))
    MAX_RETRY_COUNT: int = int(os.getenv('MAX_RETRY_COUNT', '3'))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', None)
    LOG_MAX_SIZE: int = int(os.getenv('LOG_MAX_SIZE', '10'))  # MB
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # 安全配置
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
        # 检查必需的目录
        os.makedirs(cls.AUDIO_OUTPUT_DIR, exist_ok=True)
        os.makedirs(cls.TEXT_STORAGE_DIR, exist_ok=True)
        os.makedirs(cls.SRT_OUTPUT_DIR, exist_ok=True)
        if not os.path.exists(cls.MODEL_DIR):
            os.makedirs(cls.MODEL_DIR, exist_ok=True)
        
        # 验证数值
        assert cls.PORT > 0, "端口必须为正数"
        assert cls.GPU_MEMORY_UTILIZATION > 0 and cls.GPU_MEMORY_UTILIZATION <= 1, "GPU内存利用率必须在0-1之间"
        assert cls.MAX_ONLINE_TEXT_LENGTH > 0, "在线文本最大长度必须为正数"
        assert cls.MAX_LONG_TEXT_LENGTH > cls.MAX_ONLINE_TEXT_LENGTH, "长文本最大长度必须大于在线文本最大长度"
        
        return True

# 全局配置实例
config = Config()
config.validate()