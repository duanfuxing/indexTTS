import asyncio
import aioredis
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

class RedisManager:
    """Redis缓存和队列管理器"""
    
    def __init__(self):
        from ..config import config
        self.config = config
        self.redis = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """初始化Redis连接"""
        try:
            self.redis = await aioredis.from_url(
                self.config.REDIS_URL,
                encoding='utf-8',
                decode_responses=True,
                max_connections=20
            )
            
            # 测试连接
            await self.redis.ping()
            self.logger.info("Redis连接初始化成功")
            
        except Exception as e:
            self.logger.error(f"Redis连接初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭Redis连接"""
        if self.redis:
            await self.redis.close()
            self.logger.info("Redis连接已关闭")
    
    # 任务队列相关方法
    async def push_task_to_queue(self, task_type: str, task_data: Dict[str, Any], priority: int = 0) -> bool:
        """将任务推送到队列"""
        try:
            queue_key = f"{config.REDIS_QUEUE_PREFIX}:{task_type}"
            task_json = json.dumps(task_data)
            
            # 使用有序集合存储任务，按优先级和时间戳排序
            score = priority * 1000000 + int(datetime.now().timestamp())
            await self.redis.zadd(queue_key, {task_json: score})
            
            self.logger.info(f"任务 {task_data.get('task_id')} 已推送到队列 {queue_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"推送任务到队列失败: {e}")
            return False
    
    async def pop_task_from_queue(self, task_type: str) -> Optional[Dict[str, Any]]:
        """从队列中弹出任务"""
        try:
            queue_key = f"{config.REDIS_QUEUE_PREFIX}:{task_type}"
            
            # 获取优先级最高的任务
            result = await self.redis.zpopmax(queue_key)
            
            if result:
                task_json, score = result[0]
                task_data = json.loads(task_json)
                
                self.logger.info(f"从队列 {queue_key} 弹出任务 {task_data.get('task_id')}")
                return task_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"从队列弹出任务失败: {e}")
            return None
    
    async def get_queue_length(self, task_type: str) -> int:
        """获取队列长度"""
        try:
            queue_key = f"{config.REDIS_QUEUE_PREFIX}:{task_type}"
            return await self.redis.zcard(queue_key)
        except Exception as e:
            self.logger.error(f"获取队列长度失败: {e}")
            return 0
    
    # 缓存相关方法
    async def set_cache(self, key: str, value: Any, expire: int = 3600) -> bool:
        """设置缓存"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            await self.redis.setex(key, expire, value)
            return True
            
        except Exception as e:
            self.logger.error(f"设置缓存失败: {e}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            value = await self.redis.get(key)
            
            if value is None:
                return None
            
            # 尝试解析JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            self.logger.error(f"获取缓存失败: {e}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """删除缓存"""
        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"删除缓存失败: {e}")
            return False
    
    async def exists_cache(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            self.logger.error(f"检查缓存存在性失败: {e}")
            return False
    
    # 任务状态缓存
    async def cache_task_status(self, task_id: str, status_data: Dict[str, Any], expire: int = 7200) -> bool:
        """缓存任务状态"""
        cache_key = f"task_status:{task_id}"
        return await self.set_cache(cache_key, status_data, expire)
    
    async def get_task_status_cache(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态缓存"""
        cache_key = f"task_status:{task_id}"
        return await self.get_cache(cache_key)
    
    async def delete_task_status_cache(self, task_id: str) -> bool:
        """删除任务状态缓存"""
        cache_key = f"task_status:{task_id}"
        return await self.delete_cache(cache_key)
    
    # 音色配置缓存
    async def cache_voice_configs(self, voice_configs: List[Dict[str, Any]], expire: int = 3600) -> bool:
        """缓存音色配置"""
        cache_key = "voice_configs"
        return await self.set_cache(cache_key, voice_configs, expire)
    
    async def get_voice_configs_cache(self) -> Optional[List[Dict[str, Any]]]:
        """获取音色配置缓存"""
        cache_key = "voice_configs"
        return await self.get_cache(cache_key)
    
    # 统计信息缓存
    async def increment_counter(self, key: str, amount: int = 1) -> int:
        """增加计数器"""
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            self.logger.error(f"增加计数器失败: {e}")
            return 0
    
    async def get_counter(self, key: str) -> int:
        """获取计数器值"""
        try:
            value = await self.redis.get(key)
            return int(value) if value else 0
        except Exception as e:
            self.logger.error(f"获取计数器失败: {e}")
            return 0
    
    async def set_counter_expire(self, key: str, expire: int) -> bool:
        """设置计数器过期时间"""
        try:
            return await self.redis.expire(key, expire)
        except Exception as e:
            self.logger.error(f"设置计数器过期时间失败: {e}")
            return False
    
    # 分布式锁
    async def acquire_lock(self, lock_key: str, expire: int = 30) -> bool:
        """获取分布式锁"""
        try:
            result = await self.redis.set(f"lock:{lock_key}", "1", nx=True, ex=expire)
            return result is True
        except Exception as e:
            self.logger.error(f"获取分布式锁失败: {e}")
            return False
    
    async def release_lock(self, lock_key: str) -> bool:
        """释放分布式锁"""
        try:
            result = await self.redis.delete(f"lock:{lock_key}")
            return result > 0
        except Exception as e:
            self.logger.error(f"释放分布式锁失败: {e}")
            return False
    
    # 清理过期数据
    async def cleanup_expired_data(self) -> Dict[str, int]:
        """清理过期数据"""
        cleanup_stats = {
            'expired_tasks': 0,
            'expired_locks': 0,
            'expired_counters': 0
        }
        
        try:
            # 清理过期的任务状态缓存
            pattern = "task_status:*"
            async for key in self.redis.scan_iter(match=pattern):
                ttl = await self.redis.ttl(key)
                if ttl == -1:  # 没有过期时间的key
                    await self.redis.expire(key, 7200)  # 设置2小时过期
                elif ttl == -2:  # 已过期的key
                    cleanup_stats['expired_tasks'] += 1
            
            # 清理过期的锁
            pattern = "lock:*"
            async for key in self.redis.scan_iter(match=pattern):
                ttl = await self.redis.ttl(key)
                if ttl == -2:
                    cleanup_stats['expired_locks'] += 1
            
            self.logger.info(f"Redis清理完成: {cleanup_stats}")
            
        except Exception as e:
            self.logger.error(f"Redis清理失败: {e}")
        
        return cleanup_stats
    
    # 健康检查
    async def health_check(self) -> Dict[str, Any]:
        """Redis健康检查"""
        try:
            start_time = datetime.now()
            await self.redis.ping()
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            info = await self.redis.info()
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time, 2),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'redis_version': info.get('redis_version', 'unknown')
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }