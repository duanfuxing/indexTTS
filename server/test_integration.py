#!/usr/bin/env python3
"""
TTS系统集成测试脚本

测试整个TTS系统的文件存储功能：
- 在线TTS API的文件存储
- 长文本TTS任务的文件存储
- 数据库与文件系统的一致性
"""

import os
import sys
import time
import requests
import json
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent))

from server.utils.file_manager import TaskFileManager
from server.database.db_manager import DatabaseManager

def test_online_tts_integration():
    """测试在线TTS API的集成功能"""
    print("\n=== 测试在线TTS API集成功能 ===")
    
    # 测试数据
    test_data = {
        "text": "这是一个集成测试，验证在线TTS API的文件存储功能。",
        "voice": "yunxi",
        "seed": 8
    }
    
    try:
        # 发送TTS请求
        print("1. 发送在线TTS请求...")
        response = requests.post(
            "http://localhost:6006/tts/online",
            json=test_data,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"   ❌ API请求失败: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
        
        # 解析响应
        result = response.json()
        task_id = result.get('task_id')
        
        if not task_id:
            print("   ❌ 响应中缺少task_id")
            return False
        
        print(f"   ✅ TTS请求成功，任务ID: {task_id}")
        
        # 验证数据库记录
        print("2. 验证数据库记录...")
        db_manager = DatabaseManager()
        task_info = db_manager.get_task_file_paths(task_id)
        
        if not task_info:
            print("   ❌ 数据库中未找到任务记录")
            return False
        
        print(f"   ✅ 数据库记录存在: {task_info}")
        
        # 验证文件存在
        print("3. 验证文件存在性...")
        file_manager = TaskFileManager()
        file_info = file_manager.get_file_info(task_id)
        
        if not file_info.get('audio_exists'):
            print("   ❌ 音频文件不存在")
            return False
        
        if not file_info.get('srt_exists'):
            print("   ❌ 字幕文件不存在")
            return False
        
        print(f"   ✅ 文件验证通过: {file_info}")
        
        # 清理测试数据
        print("4. 清理测试数据...")
        file_manager.delete_task_files(task_id)
        print("   ✅ 测试数据已清理")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"   ❌ 网络请求失败: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_long_text_tts_integration():
    """测试长文本TTS的集成功能"""
    print("\n=== 测试长文本TTS集成功能 ===")
    
    # 测试数据
    test_data = {
        "text": "这是一个长文本TTS集成测试。" * 20,  # 重复20次创建长文本
        "voice": "yunxi",
        "callback_url": "http://localhost:6006/test-callback",
        "metadata": {"test": "long_text_integration"}
    }
    
    try:
        # 提交长文本TTS任务
        print("1. 提交长文本TTS任务...")
        response = requests.post(
            "http://localhost:6006/tts/long-text/submit",
            json=test_data,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"   ❌ 任务提交失败: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
        
        result = response.json()
        task_id = result.get('task_id')
        
        if not task_id:
            print("   ❌ 响应中缺少task_id")
            return False
        
        print(f"   ✅ 任务提交成功，任务ID: {task_id}")
        
        # 等待任务完成
        print("2. 等待任务完成...")
        max_wait_time = 60  # 最多等待60秒
        wait_time = 0
        
        while wait_time < max_wait_time:
            time.sleep(2)
            wait_time += 2
            
            # 检查任务状态
            status_response = requests.get(
                f"http://localhost:6006/tts/long-text/result/{task_id}",
                timeout=10
            )
            
            if status_response.status_code == 200:
                print(f"   ✅ 任务完成，等待时间: {wait_time}秒")
                break
            elif status_response.status_code == 202:
                print(f"   ⏳ 任务进行中... ({wait_time}s)")
                continue
            else:
                print(f"   ❌ 任务状态检查失败: {status_response.status_code}")
                return False
        
        if wait_time >= max_wait_time:
            print("   ❌ 任务超时")
            return False
        
        # 验证数据库记录
        print("3. 验证数据库记录...")
        db_manager = DatabaseManager()
        task_info = db_manager.get_task_file_paths(task_id)
        
        if not task_info:
            print("   ❌ 数据库中未找到任务记录")
            return False
        
        print(f"   ✅ 数据库记录存在: {task_info}")
        
        # 验证文件存在
        print("4. 验证文件存在性...")
        file_manager = TaskFileManager()
        file_info = file_manager.get_file_info(task_id)
        
        if not file_info.get('text_exists'):
            print("   ❌ 文本文件不存在")
            return False
        
        if not file_info.get('audio_exists'):
            print("   ❌ 音频文件不存在")
            return False
        
        if not file_info.get('srt_exists'):
            print("   ❌ 字幕文件不存在")
            return False
        
        print(f"   ✅ 文件验证通过: {file_info}")
        
        # 测试字幕文件下载
        print("5. 测试字幕文件下载...")
        srt_response = requests.get(
            f"http://localhost:6006/tts/long-text/srt/{task_id}",
            timeout=10
        )
        
        if srt_response.status_code != 200:
            print(f"   ❌ 字幕文件下载失败: {srt_response.status_code}")
            return False
        
        srt_content = srt_response.text
        if len(srt_content) == 0:
            print("   ❌ 字幕文件内容为空")
            return False
        
        print(f"   ✅ 字幕文件下载成功，内容长度: {len(srt_content)}")
        
        # 清理测试数据
        print("6. 清理测试数据...")
        file_manager.delete_task_files(task_id)
        print("   ✅ 测试数据已清理")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"   ❌ 网络请求失败: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_services():
    """检查服务是否运行"""
    print("检查服务状态...")
    
    try:
        # 检查API服务
        response = requests.get("http://localhost:6006/health", timeout=5)
        if response.status_code == 200:
            print("✅ API服务运行正常")
            return True
        else:
            print(f"❌ API服务状态异常: {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print("❌ API服务未运行，请先启动服务")
        print("   提示: 运行 'python -m server.api_server' 启动API服务")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("TTS系统集成测试")
    print("=" * 60)
    
    # 检查服务状态
    if not check_services():
        print("\n💥 服务未运行，无法进行集成测试")
        sys.exit(1)
    
    # 运行在线TTS集成测试
    online_test_passed = test_online_tts_integration()
    
    # 运行长文本TTS集成测试
    long_text_test_passed = test_long_text_tts_integration()
    
    print("\n" + "=" * 60)
    print("集成测试结果汇总:")
    print(f"在线TTS集成测试: {'✅ 通过' if online_test_passed else '❌ 失败'}")
    print(f"长文本TTS集成测试: {'✅ 通过' if long_text_test_passed else '❌ 失败'}")
    
    if online_test_passed and long_text_test_passed:
        print("\n🎉 所有集成测试通过！TTS系统文件存储功能完全正常。")
        sys.exit(0)
    else:
        print("\n💥 部分集成测试失败，请检查系统配置。")
        sys.exit(1)