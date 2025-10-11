#!/usr/bin/env python3
"""
缓存文件定时清理脚本
支持两种模式：
1. 单次执行模式：直接执行清理任务后退出
2. 调度器模式：作为常驻进程，每日定时执行清理任务
"""

import os
import sys
import asyncio
import traceback
import argparse
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


class CacheCleanupScheduler:
    """缓存清理定时调度器"""
    
    def __init__(self):
        self.logger = IndexTTSLogger.get_module_logger(__file__)
        self.cleanup_service = None
        
        # 从环境变量获取执行时间，默认凌晨2点
        self.cleanup_hour = int(os.getenv('CACHE_CLEANUP_HOUR', '2'))
        self.cleanup_minute = int(os.getenv('CACHE_CLEANUP_MINUTE', '0'))
        
        self.logger.info(f"缓存清理调度器初始化完成")
        self.logger.info(f"每日执行时间: {self.cleanup_hour:02d}:{self.cleanup_minute:02d}")
    
    def get_next_cleanup_time(self):
        """计算下次清理时间"""
        now = datetime.now()
        
        # 今天的清理时间
        today_cleanup = now.replace(
            hour=self.cleanup_hour, 
            minute=self.cleanup_minute, 
            second=0, 
            microsecond=0
        )
        
        # 如果今天的清理时间已过，则安排明天
        if now >= today_cleanup:
            next_cleanup = today_cleanup + timedelta(days=1)
        else:
            next_cleanup = today_cleanup
        
        return next_cleanup
    
    def calculate_sleep_seconds(self):
        """计算需要睡眠的秒数"""
        next_cleanup = self.get_next_cleanup_time()
        now = datetime.now()
        sleep_seconds = (next_cleanup - now).total_seconds()
        
        self.logger.info(f"下次清理时间: {next_cleanup.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"距离下次清理还有: {sleep_seconds/3600:.1f} 小时")
        
        return sleep_seconds
    
    async def run_cleanup(self):
        """执行清理任务"""
        try:
            self.logger.info("开始执行缓存清理任务")
            
            # 初始化清理服务
            if not self.cleanup_service:
                self.cleanup_service = CacheCleanupService()
                await self.cleanup_service.initialize()
            
            # 执行清理
            await self.cleanup_service.cleanup_expired_tasks()
            await self.cleanup_service.cleanup_empty_directories()
            
            self.logger.info("缓存清理任务执行完成")
            
        except Exception as e:
            self.logger.error(f"执行缓存清理任务时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())
    
    async def run_scheduler(self):
        """运行调度器主循环"""
        self.logger.info("缓存清理调度器启动")
        
        while True:
            try:
                # 计算睡眠时间
                sleep_seconds = self.calculate_sleep_seconds()
                
                # 如果睡眠时间太长（超过24小时），分段睡眠以便响应停止信号
                if sleep_seconds > 3600:  # 超过1小时
                    # 每小时检查一次
                    check_interval = 3600
                    remaining_sleep = sleep_seconds
                    
                    while remaining_sleep > 0:
                        current_sleep = min(check_interval, remaining_sleep)
                        self.logger.debug(f"睡眠 {current_sleep/60:.1f} 分钟...")
                        await asyncio.sleep(current_sleep)
                        remaining_sleep -= current_sleep
                        
                        # 重新计算剩余时间，防止时间漂移
                        if remaining_sleep > check_interval:
                            sleep_seconds = self.calculate_sleep_seconds()
                            remaining_sleep = sleep_seconds
                else:
                    # 睡眠时间较短，直接睡眠
                    self.logger.info(f"等待 {sleep_seconds/60:.1f} 分钟后执行清理...")
                    await asyncio.sleep(sleep_seconds)
                
                # 执行清理任务
                await self.run_cleanup()
                
            except KeyboardInterrupt:
                self.logger.info("收到停止信号，调度器正在退出...")
                break
            except Exception as e:
                self.logger.error(f"调度器运行时发生错误: {str(e)}")
                self.logger.error(traceback.format_exc())
                # 发生错误时等待5分钟后重试
                await asyncio.sleep(300)


async def run_once():
    """单次执行模式"""
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


async def run_scheduler():
    """调度器模式"""
    scheduler = CacheCleanupScheduler()
    
    try:
        await scheduler.run_scheduler()
    except KeyboardInterrupt:
        print("调度器已停止")
    except Exception as e:
        print(f"调度器运行失败: {str(e)}")
        sys.exit(1)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='缓存清理脚本')
    parser.add_argument('--scheduler', action='store_true', 
                       help='以调度器模式运行（每日定时执行）')
    parser.add_argument('--once', action='store_true', 
                       help='单次执行模式（立即执行一次清理）')
    
    args = parser.parse_args()
    
    # 如果没有指定参数，默认为单次执行模式
    if not args.scheduler and not args.once:
        args.once = True
    
    if args.scheduler:
        print("启动缓存清理调度器...")
        await run_scheduler()
    elif args.once:
        print("执行单次缓存清理...")
        await run_once()


if __name__ == "__main__":
    asyncio.run(main())