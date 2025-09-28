#!/usr/bin/env python3
"""
数据库连接测试脚本
测试MySQL和Redis的连接状态
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目路径到sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.config import config
from server.database.db_manager import DatabaseManager
from server.cache.redis_manager import RedisManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_mysql_connection():
    """测试MySQL数据库连接"""
    logger.info("开始测试MySQL连接...")
    
    try:
        # 创建数据库管理器实例
        db_manager = DatabaseManager()
        
        # 初始化连接
        await db_manager.initialize()
        logger.info("✅ MySQL连接初始化成功")
        
        # 测试基本查询
        async with db_manager.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT VERSION()")
                version = await cursor.fetchone()
                logger.info(f"✅ MySQL版本: {version[0]}")
                
                # 测试数据库是否存在
                await cursor.execute("SELECT DATABASE()")
                database = await cursor.fetchone()
                logger.info(f"✅ 当前数据库: {database[0]}")
                
                # 检查表是否存在
                await cursor.execute("SHOW TABLES")
                tables = await cursor.fetchall()
                if tables:
                    logger.info(f"✅ 数据库中的表: {[table[0] for table in tables]}")
                else:
                    logger.warning("⚠️  数据库中没有表")
        
        # 关闭连接
        await db_manager.close()
        logger.info("✅ MySQL连接测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ MySQL连接测试失败: {e}")
        return False

async def test_redis_connection():
    """测试Redis连接"""
    logger.info("开始测试Redis连接...")
    
    try:
        # 创建Redis管理器实例
        redis_manager = RedisManager()
        
        # 初始化连接
        await redis_manager.initialize()
        logger.info("✅ Redis连接初始化成功")
        
        # 测试基本操作
        test_key = "test_connection"
        test_value = f"test_value_{datetime.now().timestamp()}"
        
        # 设置值
        await redis_manager.set_cache(test_key, test_value, expire=60)
        logger.info(f"✅ Redis设置缓存成功: {test_key} = {test_value}")
        
        # 获取值
        retrieved_value = await redis_manager.get_cache(test_key)
        if retrieved_value == test_value:
            logger.info(f"✅ Redis获取缓存成功: {retrieved_value}")
        else:
            logger.error(f"❌ Redis缓存值不匹配: 期望 {test_value}, 实际 {retrieved_value}")
            return False
        
        # 删除测试键
        await redis_manager.delete_cache(test_key)
        logger.info("✅ Redis清理测试数据成功")
        
        # 测试健康检查
        health_info = await redis_manager.health_check()
        logger.info(f"✅ Redis健康检查: {health_info}")
        
        # 关闭连接
        await redis_manager.close()
        logger.info("✅ Redis连接测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ Redis连接测试失败: {e}")
        return False

async def test_config():
    """测试配置信息"""
    logger.info("开始测试配置信息...")
    
    try:
        logger.info("=== MySQL配置 ===")
        logger.info(f"主机: {config.MYSQL_HOST}")
        logger.info(f"端口: {config.MYSQL_PORT}")
        logger.info(f"用户: {config.MYSQL_USER}")
        logger.info(f"数据库: {config.MYSQL_DATABASE}")
        logger.info(f"数据库URL: {config.database_url}")
        
        logger.info("=== Redis配置 ===")
        logger.info(f"主机: {config.REDIS_HOST}")
        logger.info(f"端口: {config.REDIS_PORT}")
        logger.info(f"数据库: {config.REDIS_DB}")
        logger.info(f"SSL: {config.REDIS_SSL}")
        logger.info(f"密码: {'已设置' if config.REDIS_PASSWORD else '未设置'}")
        logger.info(f"Redis URL: {config.redis_url}")
        
        logger.info("✅ 配置信息显示完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 配置测试失败: {e}")
        return False

async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("开始数据库连接测试")
    logger.info("=" * 50)
    
    results = {}
    
    # 测试配置
    results['config'] = await test_config()
    
    print()  # 空行分隔
    
    # 测试MySQL连接
    results['mysql'] = await test_mysql_connection()
    
    print()  # 空行分隔
    
    # 测试Redis连接
    results['redis'] = await test_redis_connection()
    
    # 输出总结
    logger.info("=" * 50)
    logger.info("测试结果总结:")
    logger.info("=" * 50)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name.upper()}: {status}")
    
    # 检查是否所有测试都通过
    all_passed = all(results.values())
    if all_passed:
        logger.info("🎉 所有连接测试通过!")
        return 0
    else:
        logger.error("💥 部分连接测试失败!")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生未预期的错误: {e}")
        sys.exit(1)