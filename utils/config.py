import os
from typing import Optional

class Config:
    # 数据库配置
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aigc_omni")
    
    # 动态构建数据库URL
    @property
    def database_url(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
    
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
    TEXT_STORAGE_DIR: str = os.getenv('TEXT_STORAGE_DIR', './storage/tasks')
    
    # 文本长度限制
    MAX_ONLINE_TEXT_LENGTH: int = int(os.getenv('MAX_ONLINE_TEXT_LENGTH', '1000'))
    MAX_LONG_TEXT_LENGTH: int = int(os.getenv('MAX_LONG_TEXT_LENGTH', '50000'))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', './logs/tts_service.log')
    LOG_MAX_SIZE: str = os.getenv('LOG_MAX_SIZE', '10MB')
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # 从LOG_FILE中提取日志目录
    @property
    def log_dir(self) -> str:
        if self.LOG_FILE:
            return os.path.dirname(os.path.abspath(self.LOG_FILE))
        return os.path.abspath('./logs')
    
    # 解析日志文件大小（支持MB单位）
    @property
    def log_max_size_bytes(self) -> int:
        size_str = self.LOG_MAX_SIZE.upper()
        if size_str.endswith('MB'):
            return int(size_str.replace('MB', '')) * 1024 * 1024
        elif size_str.endswith('KB'):
            return int(size_str.replace('KB', '')) * 1024
        elif size_str.endswith('GB'):
            return int(size_str.replace('GB', '')) * 1024 * 1024 * 1024
        else:
            # 默认按MB处理
            return int(size_str) * 1024 * 1024
    
    # API配置
    API_KEY: Optional[str] = os.getenv('API_KEY')
    ALLOWED_ORIGINS: list = os.getenv('ALLOWED_ORIGINS', '*').split(',')
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
    
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