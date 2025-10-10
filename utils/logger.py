#!/usr/bin/env python3
"""
统一的日志管理器

提供统一的日志记录功能，支持：
- 文件输出和控制台输出
- 颜色格式化
- 不同的错误级别
- 自动日志文件轮转
- 线程安全
"""

import os
import sys
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import colorama
from colorama import Fore, Back, Style

# 初始化colorama
colorama.init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    # 定义颜色映射
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE + Style.BRIGHT,
    }
    
    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors
    
    def format(self, record):
        if self.use_colors and record.levelname in self.COLORS:
            # 为日志级别添加颜色
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Style.RESET_ALL}"
            
            # 为模块名添加颜色
            if hasattr(record, 'name'):
                record.name = f"{Fore.BLUE}{record.name}{Style.RESET_ALL}"
        
        return super().format(record)

class IndexTTSLogger:
    """IndexTTS统一日志管理器"""
    
    _instances: Dict[str, logging.Logger] = {}
    _initialized = False
    
    @classmethod
    def setup_logging(cls, 
                     log_dir: str = "/root/autodl-tmp/indexTTS/logs",
                     log_level: str = "INFO",
                     max_file_size: int = 10 * 1024 * 1024,  # 10MB
                     backup_count: int = 5,
                     console_output: bool = True,
                     file_output: bool = True,
                     use_colors: bool = True):
        """
        设置全局日志配置
        
        Args:
            log_dir: 日志文件目录
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_file_size: 单个日志文件最大大小（字节）
            backup_count: 保留的日志文件备份数量
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
            use_colors: 控制台输出是否使用颜色
        """
        if cls._initialized:
            return
        
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # 设置全局配置
        cls.log_dir = log_dir
        cls.log_level = getattr(logging, log_level.upper())
        cls.max_file_size = max_file_size
        cls.backup_count = backup_count
        cls.console_output = console_output
        cls.file_output = file_output
        cls.use_colors = use_colors
        
        # 设置根日志器级别
        logging.getLogger().setLevel(cls.log_level)
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str, 
                  log_file: Optional[str] = None,
                  console_output: Optional[bool] = None,
                  file_output: Optional[bool] = None,
                  use_colors: Optional[bool] = None) -> logging.Logger:
        """
        获取或创建日志器实例
        
        Args:
            name: 日志器名称，通常使用模块名
            log_file: 自定义日志文件名，如果不指定则使用name
            console_output: 是否输出到控制台，覆盖全局设置
            file_output: 是否输出到文件，覆盖全局设置
            use_colors: 是否使用颜色，覆盖全局设置
            
        Returns:
            配置好的日志器实例
        """
        # 确保已初始化
        if not cls._initialized:
            cls.setup_logging()
        
        # 如果已存在则直接返回
        if name in cls._instances:
            return cls._instances[name]
        
        # 创建新的日志器
        logger = logging.getLogger(name)
        logger.setLevel(cls.log_level)
        
        # 清除已有的处理器（避免重复）
        logger.handlers.clear()
        
        # 使用参数覆盖全局设置
        _console_output = console_output if console_output is not None else cls.console_output
        _file_output = file_output if file_output is not None else cls.file_output
        _use_colors = use_colors if use_colors is not None else cls.use_colors
        
        # 定义日志格式
        detailed_format = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "[%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s"
        )
        simple_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # 添加控制台处理器
        if _console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(cls.log_level)
            
            if _use_colors:
                console_formatter = ColoredFormatter(
                    fmt=simple_format,
                    datefmt="%Y-%m-%d %H:%M:%S",
                    use_colors=True
                )
            else:
                console_formatter = logging.Formatter(
                    fmt=simple_format,
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # 添加文件处理器
        if _file_output:
            # 确定日志文件名
            if log_file:
                log_filename = log_file if log_file.endswith('.log') else f"{log_file}.log"
            else:
                # 从模块名生成文件名
                module_name = name.split('.')[-1] if '.' in name else name
                log_filename = f"{module_name}.log"
            
            log_filepath = Path(cls.log_dir) / log_filename
            
            # 使用RotatingFileHandler实现日志轮转
            file_handler = logging.handlers.RotatingFileHandler(
                filename=str(log_filepath),
                maxBytes=cls.max_file_size,
                backupCount=cls.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(cls.log_level)
            
            # 文件输出使用详细格式，不使用颜色
            file_formatter = logging.Formatter(
                fmt=detailed_format,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        # 防止日志传播到根日志器（避免重复输出）
        logger.propagate = False
        
        # 缓存日志器实例
        cls._instances[name] = logger
        
        return logger
    
    @classmethod
    def get_module_logger(cls, module_file: str, **kwargs) -> logging.Logger:
        """
        根据模块文件路径获取日志器
        
        Args:
            module_file: 模块文件路径，通常传入 __file__
            **kwargs: 其他参数传递给 get_logger
            
        Returns:
            配置好的日志器实例
        """
        # 从文件路径提取模块名
        module_path = Path(module_file)
        module_name = module_path.stem
        
        # 如果在utils目录下，添加utils前缀
        if 'utils' in module_path.parts:
            module_name = f"utils.{module_name}"
        
        return cls.get_logger(module_name, **kwargs)
    
    @classmethod
    def set_level(cls, level: str):
        """
        动态设置所有日志器的级别
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        new_level = getattr(logging, level.upper())
        cls.log_level = new_level
        
        # 更新所有已创建的日志器
        for logger in cls._instances.values():
            logger.setLevel(new_level)
            for handler in logger.handlers:
                handler.setLevel(new_level)
    
    @classmethod
    def add_custom_handler(cls, name: str, handler: logging.Handler):
        """
        为指定的日志器添加自定义处理器
        
        Args:
            name: 日志器名称
            handler: 自定义处理器
        """
        if name in cls._instances:
            cls._instances[name].addHandler(handler)
    
    @classmethod
    def remove_handler(cls, name: str, handler_type: type):
        """
        移除指定类型的处理器
        
        Args:
            name: 日志器名称
            handler_type: 处理器类型
        """
        if name in cls._instances:
            logger = cls._instances[name]
            handlers_to_remove = [h for h in logger.handlers if isinstance(h, handler_type)]
            for handler in handlers_to_remove:
                logger.removeHandler(handler)
    
    @classmethod
    def shutdown(cls):
        """关闭所有日志器并清理资源"""
        for logger in cls._instances.values():
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
        
        cls._instances.clear()
        cls._initialized = False
        logging.shutdown()

# 便捷函数
def get_logger(name: str = None, **kwargs) -> logging.Logger:
    """
    便捷函数：获取日志器实例
    
    Args:
        name: 日志器名称，如果不指定则使用调用者的模块名
        **kwargs: 其他参数传递给 IndexTTSLogger.get_logger
        
    Returns:
        配置好的日志器实例
    """
    if name is None:
        # 自动获取调用者的模块名
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    return IndexTTSLogger.get_logger(name, **kwargs)

def setup_logging(**kwargs):
    """便捷函数：设置全局日志配置"""
    IndexTTSLogger.setup_logging(**kwargs)

# 模块级别的默认配置
if not IndexTTSLogger._initialized:
    IndexTTSLogger.setup_logging()