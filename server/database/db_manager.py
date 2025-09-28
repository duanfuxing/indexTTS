import asyncio
import aiomysql
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import uuid
import os
import hashlib
from contextlib import asynccontextmanager
from ..utils.file_manager import TaskFileManager

class DatabaseManager:
    """TTS任务和音色配置的MySQL数据库管理器"""
    
    def __init__(self, database_url: str = None):
        from ..config import config
        self.config = config
        self.database_url = database_url or config.DATABASE_URL
        self.pool = None
        self.logger = logging.getLogger(__name__)
        # 初始化文件管理器
        self.file_manager = TaskFileManager()
    
    async def initialize(self):
        """初始化数据库连接池"""
        try:
            self.pool = await aiomysql.create_pool(
                host=self.config.MYSQL_HOST,
                port=self.config.MYSQL_PORT,
                user=self.config.MYSQL_USER,
                password=self.config.MYSQL_PASSWORD,
                db=self.config.MYSQL_DATABASE,
                charset='utf8mb4',
                minsize=2,
                maxsize=10,
                autocommit=True
            )
            self.logger.info("MySQL数据库连接池创建成功")
            
            # 检查表是否存在，如果不存在则由启动脚本创建
            tables_status = await self.check_tables_exist()
            
        except Exception as e:
            self.logger.error(f"MySQL数据库初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭数据库连接池"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.logger.info("MySQL数据库连接池已关闭")
    
    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接"""
        async with self.pool.acquire() as conn:
            yield conn
    
    async def check_tables_exist(self):
        """检查数据库表是否存在"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                # 检查tts_tasks表是否存在
                await cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = DATABASE() AND table_name = 'tts_tasks'
                """)
                tts_tasks_exists = (await cursor.fetchone())[0] > 0
                
                # 检查voice_configs表是否存在
                await cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = DATABASE() AND table_name = 'voice_configs'
                """)
                voice_configs_exists = (await cursor.fetchone())[0] > 0
                
                self.logger.info(f"表存在性检查: tts_tasks={tts_tasks_exists}, voice_configs={voice_configs_exists}")
                return {
                    'tts_tasks': tts_tasks_exists,
                    'voice_configs': voice_configs_exists
                }
    
    def _generate_short_id(self) -> str:
        """生成短ID（8位随机字符串）"""
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    async def _save_text_to_file(self, text: str, task_id: str) -> str:
        """将文本保存到文件，返回文件路径"""
        try:
            return self.file_manager.save_text_file(task_id, text)
        except Exception as e:
            self.logger.error(f"保存文本文件失败: {e}")
            return None
    
    def _get_text_preview(self, text: str) -> str:
        """获取文本预览（前200字符）"""
        return text[:200] if text else ""
    
    async def _read_text_from_file(self, task_id: str) -> str:
        """从文件读取文本内容"""
        try:
            content = self.file_manager.read_text_file(task_id)
            return content or ""
        except Exception as e:
            self.logger.error(f"读取文本文件失败: {e}")
            return ""
    
    async def get_task_text(self, task_data: Dict[str, Any]) -> str:
        """获取任务的完整文本内容"""
        if task_data.get('text_file_path'):
            return await self._read_text_from_file(task_data['task_id'])
        else:
            return task_data.get('text_preview', '')
    
    async def create_online_task(self, text: str, voice: str, payload: dict = None, callback_url: str = None) -> str:
        """创建在线TTS任务"""
        task_id = self._generate_short_id()
        text_preview = self._get_text_preview(text)
        
        # 创建任务目录
        task_directory = self.file_manager.create_task_directory(task_id)
        
        # 保存文本文件（所有任务都保存）
        text_file_path = await self._save_text_to_file(text, task_id)
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO tts_tasks (task_id, task_type, task_directory, text_file_path, text_preview, voice, payload, callback_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (task_id, 'online', task_directory, text_file_path, text_preview, voice, 
                     json.dumps(payload) if payload else None, callback_url)
                )
        
        self.logger.info(f"已创建在线TTS任务: {task_id}")
        return task_id
    
    async def create_long_text_task(self, text: str, voice: str, payload: dict = None, 
                                   callback_url: str = None) -> str:
        """创建长文本TTS任务"""
        task_id = self._generate_short_id()
        text_preview = self._get_text_preview(text)
        
        # 创建任务目录
        task_directory = self.file_manager.create_task_directory(task_id)
        
        # 保存文本文件
        text_file_path = await self._save_text_to_file(text, task_id)
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO tts_tasks (task_id, task_type, task_directory, text_file_path, text_preview, voice, payload, callback_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (task_id, 'long_text', task_directory, text_file_path, text_preview, voice, 
                     json.dumps(payload) if payload else None, callback_url)
                )
        
        self.logger.info(f"已创建长文本TTS任务: {task_id}")
        return task_id
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT * FROM tts_tasks WHERE task_id = %s",
                    (task_id,)
                )
                result = await cursor.fetchone()
                
                if result and result['payload']:
                    result['payload'] = json.loads(result['payload'])
                
                return result
    
    async def get_next_task(self, task_type: str = None) -> Optional[Dict[str, Any]]:
        """获取下一个待处理任务（已弃用，现在使用Redis队列）"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # 构建查询条件
                where_clause = "status = 'pending'"
                params = []
                
                if task_type:
                    where_clause += " AND task_type = %s"
                    params.append(task_type)
                
                # 获取并锁定任务
                await cursor.execute(f"""
                    SELECT * FROM tts_tasks 
                    WHERE {where_clause}
                    ORDER BY created_at ASC 
                    LIMIT 1 FOR UPDATE
                """, params)
                
                task_data = await cursor.fetchone()
                
                if task_data:
                    # 更新任务状态为处理中
                    await cursor.execute(
                        """
                        UPDATE tts_tasks 
                        SET status = 'processing', started_at = NOW()
                        WHERE task_id = %s
                        """,
                        (task_data['task_id'],)
                    )
                    
                    # 解析payload
                    if task_data['payload']:
                        task_data['payload'] = json.loads(task_data['payload'])
                    
                    self.logger.info(f"已获取任务 {task_data['task_id']} 进行处理")
                    return task_data
                
                return None
    
    async def update_task_status(self, task_id: str, status: str, audio_file_path: str = None,
                                audio_url: str = None, srt_file_path: str = None, srt_url: str = None, 
                                error_message: str = None, result: dict = None, srt: str = None,
                                processing_time: float = None, actual_duration: int = None, 
                                file_size: int = None, **kwargs) -> bool:
        """更新任务状态"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                update_fields = ["status = %s"]
                params = [status]
                
                if audio_file_path is not None:
                    update_fields.append("audio_file_path = %s")
                    params.append(audio_file_path)
                
                if audio_url is not None:
                    update_fields.append("audio_url = %s")
                    params.append(audio_url)
                
                if srt_file_path is not None:
                    update_fields.append("srt_file_path = %s")
                    params.append(srt_file_path)
                
                if srt_url is not None:
                    update_fields.append("srt_url = %s")
                    params.append(srt_url)
                
                if error_message is not None:
                    update_fields.append("error_message = %s")
                    params.append(error_message)
                
                if status in ['completed', 'failed']:
                    update_fields.append("completed_at = NOW()")
                
                params.append(task_id)
                
                await cursor.execute(f"""
                    UPDATE tts_tasks 
                    SET {', '.join(update_fields)}
                    WHERE task_id = %s
                """, params)
                
                success = cursor.rowcount > 0
                
                if success:
                    self.logger.info(f"已更新任务 {task_id} 状态为 {status}")
                else:
                    self.logger.warning(f"更新任务 {task_id} 失败 - 任务未找到")
                
                return success
    
    async def update_task_files(self, task_id: str, audio_file_path: str = None, 
                               audio_url: str = None, srt_file_path: str = None, srt_url: str = None) -> bool:
        """更新任务的文件路径"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                update_fields = []
                params = []
                
                if audio_file_path is not None:
                    update_fields.append("audio_file_path = %s")
                    params.append(audio_file_path)
                
                if audio_url is not None:
                    update_fields.append("audio_url = %s")
                    params.append(audio_url)
                
                if srt_file_path is not None:
                    update_fields.append("srt_file_path = %s")
                    params.append(srt_file_path)
                
                if srt_url is not None:
                    update_fields.append("srt_url = %s")
                    params.append(srt_url)
                
                if not update_fields:
                    return True
                
                update_fields.append("updated_at = NOW()")
                params.append(task_id)
                
                await cursor.execute(f"""
                    UPDATE tts_tasks 
                    SET {', '.join(update_fields)}
                    WHERE task_id = %s
                """, params)
                
                success = cursor.rowcount > 0
                
                if success:
                    self.logger.info(f"已更新任务 {task_id} 的文件路径")
                else:
                    self.logger.warning(f"更新任务 {task_id} 文件路径失败 - 任务未找到")
                
                return success
    
    def get_task_file_paths(self, task_id: str) -> Dict[str, str]:
        """获取任务的文件路径"""
        return {
            'task_directory': self.file_manager.get_task_directory(task_id),
            'text_file_path': self.file_manager.get_text_file_path(task_id),
            'audio_file_path': self.file_manager.get_audio_file_path(task_id),
            'srt_file_path': self.file_manager.get_srt_file_path(task_id),
            'audio_url': self.file_manager.get_audio_url(task_id)
        }
    
    async def get_task_list(self, status: str = None, task_type: str = None, 
                           limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取任务列表"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                where_conditions = []
                params = []
                
                if status:
                    where_conditions.append("status = %s")
                    params.append(status)
                
                if task_type:
                    where_conditions.append("task_type = %s")
                    params.append(task_type)
                
                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
                
                params.extend([limit, offset])
                
                await cursor.execute(f"""
                    SELECT * FROM tts_tasks 
                    WHERE {where_clause}
                    ORDER BY created_at DESC 
                    LIMIT %s OFFSET %s
                """, params)
                
                results = await cursor.fetchall()
                
                # 解析payload
                for result in results:
                    if result['payload']:
                        result['payload'] = json.loads(result['payload'])
                
                return results
    
    async def cleanup_old_tasks(self, days: int = 7) -> int:
        """清理旧任务"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM tts_tasks 
                    WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND status IN ('completed', 'failed')
                    """,
                    (days,)
                )
                
                deleted_count = cursor.rowcount
                self.logger.info(f"已清理 {deleted_count} 个旧任务")
                return deleted_count
    
    async def get_voice_configs(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """获取音色配置列表"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                where_clause = "is_active = TRUE" if active_only else "1=1"
                
                await cursor.execute(f"""
                    SELECT * FROM voice_configs 
                    WHERE {where_clause}
                    ORDER BY voice_name
                """)
                
                results = await cursor.fetchall()
                
                # 解析config
                for result in results:
                    if result['config']:
                        result['config'] = json.loads(result['config'])
                
                return results