#!/usr/bin/env python3
"""
缓存文件定时清理脚本
通过查询数据库中的过期任务，删除对应的任务文件夹
"""

import os
import sys
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import traceback
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import config
from utils.db_manager import DatabaseManager
from utils.logger import IndexTTSLogger


class CacheCleanupService:
    """缓存清理服务"""
    
    def __init__(self):
        self.logger = IndexTTSLogger.get_module_logger(__file__)
        self.db_manager = DatabaseManager()
        self.storage_dir = Path(config.TEXT_STORAGE_DIR)
        
        # 从环境变量获取过期天数，默认7天
        self.expire_days = int(os.getenv('CACHE_EXPIRE_DAYS', '7'))
        
        self.logger.info(f"缓存清理服务初始化完成，过期时间: {self.expire_days}天")
        self.logger.info(f"存储目录: {self.storage_dir}")
    
    async def initialize(self):
        """初始化数据库连接"""
        try:
            await self.db_manager.initialize()
            self.logger.info("数据库连接初始化成功")
        except Exception as e:
            self.logger.error(f"数据库连接初始化失败: {str(e)}")
            raise
    
    async def get_expired_tasks(self):
        """获取过期的任务列表"""
        try:
            async with self.db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    # 只查询已完成状态且过期的任务
                    expire_date = datetime.now() - timedelta(days=self.expire_days)
                    
                    await cursor.execute("""
                        SELECT task_id, status, created_at, completed_at
                        FROM tts_tasks 
                        WHERE status = 'completed' 
                        AND completed_at < %s
                        ORDER BY created_at ASC
                    """, (expire_date,))
                    
                    results = await cursor.fetchall()
                    
                    expired_tasks = []
                    for row in results:
                        expired_tasks.append({
                            'task_id': row[0],
                            'status': row[1],
                            'created_at': row[2],
                            'completed_at': row[3]
                        })
                    
                    self.logger.info(f"找到 {len(expired_tasks)} 个过期任务")
                    return expired_tasks
                    
        except Exception as e:
            self.logger.error(f"查询过期任务失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []
    
    async def cleanup_task_files(self, task_id: str) -> bool:
        """根据任务ID清理storage目录中的文件夹"""
        try:
            # 在storage目录中查找以task_id命名的文件夹
            task_folder = self.storage_dir / task_id
            
            if not task_folder.exists():
                self.logger.info(f"任务 {task_id} 文件夹不存在: {task_folder}")
                return True
            
            # 删除文件夹及其所有内容
            if task_folder.is_dir():
                shutil.rmtree(task_folder)
                self.logger.info(f"已删除任务 {task_id} 文件夹: {task_folder}")
            else:
                task_folder.unlink()
                self.logger.info(f"已删除任务 {task_id} 文件: {task_folder}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"删除任务 {task_id} 文件夹失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return False
    
    async def cleanup_expired_tasks(self):
        """清理过期任务的文件夹"""
        try:
            # 获取过期任务列表
            expired_tasks = await self.get_expired_tasks()
            
            if not expired_tasks:
                self.logger.info("没有找到过期任务")
                return
            
            # 清理每个过期任务的文件夹
            cleaned_count = 0
            for task in expired_tasks:
                task_id = task['task_id']
                success = await self.cleanup_task_files(task_id)
                if success:
                    cleaned_count += 1
            
            self.logger.info(f"成功清理了 {cleaned_count}/{len(expired_tasks)} 个过期任务的文件夹")
            
        except Exception as e:
            self.logger.error(f"清理过期任务时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())
    
    async def cleanup_empty_directories(self):
        """清理空的任务目录"""
        try:
            if not self.storage_dir.exists():
                self.logger.warning(f"存储目录不存在: {self.storage_dir}")
                return
            
            empty_dirs = []
            
            # 遍历存储目录，查找空文件夹
            for item in self.storage_dir.iterdir():
                if item.is_dir():
                    try:
                        # 检查目录是否为空
                        if not any(item.iterdir()):
                            empty_dirs.append(item)
                    except PermissionError:
                        self.logger.warning(f"无权限访问目录: {item}")
                        continue
            
            # 删除空目录
            for empty_dir in empty_dirs:
                try:
                    empty_dir.rmdir()
                    self.logger.info(f"已删除空目录: {empty_dir}")
                except Exception as e:
                    self.logger.error(f"删除空目录失败 {empty_dir}: {str(e)}")
            
            if empty_dirs:
                self.logger.info(f"清理了 {len(empty_dirs)} 个空目录")
            else:
                self.logger.info("没有找到空目录")
                
        except Exception as e:
            self.logger.error(f"清理空目录时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())


async def main():
    """主函数"""
    cleanup_service = CacheCleanupService()
    
    try:
        # 初始化数据库连接
        await cleanup_service.initialize()
        
        # 清理过期任务的文件夹
        await cleanup_service.cleanup_expired_tasks()
        
        # 清理空目录
        await cleanup_service.cleanup_empty_directories()
        
        print("缓存清理任务完成")
        
    except Exception as e:
        print(f"缓存清理任务失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())