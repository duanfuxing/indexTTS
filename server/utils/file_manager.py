#!/usr/bin/env python3
"""
文件管理工具类

负责管理TTS任务的文件存储，包括：
- 为每个任务创建独立的存储目录
- 管理文本文件、音频文件和字幕文件的存储
- 提供文件路径生成和访问功能
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import shutil
from ..config import config

class TaskFileManager:
    """任务文件管理器"""
    
    def __init__(self, storage_root: str = None):
        """初始化文件管理器
        
        Args:
            storage_root: 存储根目录，默认使用配置文件中的TEXT_STORAGE_DIR
        """
        if storage_root is None:
            storage_root = config.TEXT_STORAGE_DIR
        
        self.storage_root = Path(storage_root)
        self.logger = logging.getLogger(__name__)
        
        # 创建存储根目录
        self.storage_root.mkdir(exist_ok=True)
        
        # 创建子目录
        self.tasks_dir = self.storage_root / 'tasks'
        self.tasks_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"文件管理器初始化完成，存储根目录: {self.storage_root}")
    
    def get_task_directory(self, task_id: str) -> Path:
        """获取任务存储目录路径
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务存储目录路径
        """
        return self.tasks_dir / task_id
    
    def create_task_directory(self, task_id: str) -> str:
        """为任务创建存储目录
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务目录的绝对路径
        """
        task_dir = self.get_task_directory(task_id)
        task_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"已创建任务目录: {task_dir}")
        return str(task_dir)
    
    def get_text_file_path(self, task_id: str) -> str:
        """获取文本文件路径
        
        Args:
            task_id: 任务ID
            
        Returns:
            文本文件的绝对路径
        """
        task_dir = self.get_task_directory(task_id)
        return str(task_dir / f"{task_id}.txt")
    
    def get_audio_file_path(self, task_id: str, format: str = 'wav') -> str:
        """获取音频文件路径
        
        Args:
            task_id: 任务ID
            format: 音频格式，默认wav
            
        Returns:
            音频文件的绝对路径
        """
        task_dir = self.get_task_directory(task_id)
        return str(task_dir / f"{task_id}.{format}")
    
    def get_srt_file_path(self, task_id: str) -> str:
        """获取字幕文件路径
        
        Args:
            task_id: 任务ID
            
        Returns:
            字幕文件的绝对路径
        """
        task_dir = self.get_task_directory(task_id)
        return str(task_dir / f"{task_id}.srt")
    
    def save_text_file(self, task_id: str, text: str) -> str:
        """保存文本文件
        
        Args:
            task_id: 任务ID
            text: 文本内容
            
        Returns:
            文本文件的绝对路径
        """
        # 确保任务目录存在
        self.create_task_directory(task_id)
        
        text_file_path = self.get_text_file_path(task_id)
        
        try:
            with open(text_file_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            self.logger.info(f"已保存文本文件: {text_file_path}")
            return text_file_path
            
        except Exception as e:
            self.logger.error(f"保存文本文件失败: {e}")
            raise
    
    def read_text_file(self, task_id: str) -> str:
        """读取文本文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            文本内容
            
        Raises:
            FileNotFoundError: 文件不存在时抛出
        """
        text_file_path = self.get_text_file_path(task_id)
        
        if not os.path.exists(text_file_path):
            raise FileNotFoundError(f"文本文件不存在: {text_file_path}")
        
        try:
            with open(text_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"读取文本文件失败: {e}")
            raise
    
    def save_audio_file(self, task_id: str, audio_data: bytes, format: str = 'wav') -> str:
        """保存音频文件
        
        Args:
            task_id: 任务ID
            audio_data: 音频数据
            format: 音频格式，默认wav
            
        Returns:
            音频文件的绝对路径
        """
        # 确保任务目录存在
        self.create_task_directory(task_id)
        
        audio_file_path = self.get_audio_file_path(task_id, format)
        
        try:
            with open(audio_file_path, 'wb') as f:
                f.write(audio_data)
            
            self.logger.info(f"已保存音频文件: {audio_file_path}")
            return audio_file_path
            
        except Exception as e:
            self.logger.error(f"保存音频文件失败: {e}")
            raise
    
    def read_audio_file(self, task_id: str, format: str = 'wav') -> bytes:
        """读取音频文件
        
        Args:
            task_id: 任务ID
            format: 音频格式，默认wav
            
        Returns:
            音频数据
            
        Raises:
            FileNotFoundError: 文件不存在时抛出
        """
        audio_file_path = self.get_audio_file_path(task_id, format)
        
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_file_path}")
        
        try:
            with open(audio_file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"读取音频文件失败: {e}")
            raise
    
    def save_srt_file(self, task_id: str, srt_content: str) -> str:
        """保存字幕文件
        
        Args:
            task_id: 任务ID
            srt_content: 字幕内容
            
        Returns:
            字幕文件的绝对路径
        """
        # 确保任务目录存在
        self.create_task_directory(task_id)
        
        srt_file_path = self.get_srt_file_path(task_id)
        
        try:
            with open(srt_file_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            self.logger.info(f"已保存字幕文件: {srt_file_path}")
            return srt_file_path
            
        except Exception as e:
            self.logger.error(f"保存字幕文件失败: {e}")
            raise
    
    def read_srt_file(self, task_id: str) -> str:
        """读取字幕文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            字幕内容
            
        Raises:
            FileNotFoundError: 文件不存在时抛出
        """
        srt_file_path = self.get_srt_file_path(task_id)
        
        if not os.path.exists(srt_file_path):
            raise FileNotFoundError(f"字幕文件不存在: {srt_file_path}")
        
        try:
            with open(srt_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"读取字幕文件失败: {e}")
            raise
    
    def get_task_files_info(self, task_id: str) -> Dict[str, Any]:
        """获取任务文件信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含文件路径和存在状态的字典
        """
        task_dir = self.get_task_directory(task_id)
        
        text_file = self.get_text_file_path(task_id)
        audio_file = self.get_audio_file_path(task_id)
        srt_file = self.get_srt_file_path(task_id)
        
        return {
            'task_directory': str(task_dir),
            'task_directory_exists': task_dir.exists(),
            'text_file': text_file,
            'text_file_exists': os.path.exists(text_file),
            'audio_file': audio_file,
            'audio_file_exists': os.path.exists(audio_file),
            'srt_file': srt_file,
            'srt_file_exists': os.path.exists(srt_file)
        }
    
    def delete_task_files(self, task_id: str) -> bool:
        """删除任务的所有文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            删除是否成功
        """
        task_dir = self.get_task_directory(task_id)
        
        if not task_dir.exists():
            self.logger.warning(f"任务目录不存在: {task_dir}")
            return True
        
        try:
            shutil.rmtree(task_dir)
            self.logger.info(f"已删除任务目录: {task_dir}")
            return True
        except Exception as e:
            self.logger.error(f"删除任务目录失败: {e}")
            return False
    
    def get_audio_url(self, task_id: str, base_url: str = None) -> str:
        """获取音频文件的访问URL
        
        Args:
            task_id: 任务ID
            base_url: 基础URL，如果不提供则使用相对路径
            
        Returns:
            音频文件的访问URL
        """
        if base_url:
            return f"{base_url.rstrip('/')}/storage/tasks/{task_id}/{task_id}.wav"
        else:
            return f"/storage/tasks/{task_id}/{task_id}.wav"
    
    def get_file_paths(self, task_id: str) -> Dict[str, str]:
        """获取任务的所有文件路径
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含所有文件路径的字典
        """
        return {
            'text_file': self.get_text_file_path(task_id),
            'audio_file': self.get_audio_file_path(task_id),
            'srt_file': self.get_srt_file_path(task_id)
        }
    
    def get_file_info(self, task_id: str) -> Dict[str, Any]:
        """获取任务文件的详细信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含文件大小等信息的字典
        """
        file_paths = self.get_file_paths(task_id)
        info = {}
        
        for file_type, file_path in file_paths.items():
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                info[f'{file_type.replace("_file", "_size")}'] = stat.st_size
                info[f'{file_type.replace("_file", "_exists")}'] = True
            else:
                info[f'{file_type.replace("_file", "_size")}'] = 0
                info[f'{file_type.replace("_file", "_exists")}'] = False
        
        return info