import os
import tos
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tos import DataTransferType
from tos.utils import SizeAdapter, MergeProcess
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class TOSUploader:
    def __init__(self, tos_config: dict):
        """初始化 TOS 上传器
        
        Args:
            tos_config (dict): TOS配置字典，包含access_key, secret_key, endpoint, region, bucket等
        """
        # 初始化日志器
        self.logger = logging.getLogger(__name__)
        
        try:
            self.client = tos.TosClientV2(
                tos_config['access_key'],
                tos_config['secret_key'],
                tos_config['endpoint'],
                tos_config['region']
            )
            self.bucket = tos_config['bucket']
            self.remote_path = tos_config.get('remote_path', 'tts_files')
            self.logger.info("TOS上传器初始化成功")
        except Exception as e:
            self.logger.error(f"TOS上传器初始化失败: {str(e)}")
            raise
    
    @classmethod
    def from_env(cls):
        """从环境变量创建TOS上传器实例
        
        Returns:
            TOSUploader: TOS上传器实例
            
        Raises:
            ValueError: 环境变量配置不完整
        """
        required_env_vars = {
            'access_key': 'TOS_ACCESS_KEY',
            'secret_key': 'TOS_SECRET_KEY', 
            'endpoint': 'TOS_ENDPOINT',
            'region': 'TOS_REGION',
            'bucket': 'TOS_BUCKET'
        }
        
        tos_config = {}
        missing_vars = []
        
        for key, env_var in required_env_vars.items():
            value = os.getenv(env_var)
            if not value:
                missing_vars.append(env_var)
            else:
                tos_config[key] = value
        
        if missing_vars:
            raise ValueError(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        
        # 可选的远程路径配置
        tos_config['remote_path'] = os.getenv('TOS_REMOTE_PATH', 'tts_files')
        
        return cls(tos_config)

    def upload(self, local_path: str, max_retries: int = 3) -> str:
        """上传视频到TOS并在上传成功
        
        Args:
            local_path (str): 本地文件路径
            max_retries (int): 最大重试次数，默认3次
        
        Returns:
            str: object_key
            
        Raises:
            FileNotFoundError: 文件不存在
            Exception: 上传失败或其他错误
        """
        from tos import DataTransferType
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        # 重试逻辑
        last_exception = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.logger.info(f"第 {attempt + 1} 次重试上传文件: {local_path}")
                return self._do_upload(local_path)
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.warning(f"上传失败，{wait_time}秒后重试: {str(e)}")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"上传失败，已达到最大重试次数 {max_retries}: {str(e)}")
        
        raise last_exception
    
    def _do_upload(self, local_path: str) -> str:
        """执行实际的上传操作"""
        try:

            # 获取文件名
            file_name = os.path.basename(local_path)
            # 生成对象键名：目录/文件名
            object_key = f"{self.remote_path}/{file_name}"
            
            # 获取文件大小用于进度显示
            total_size = os.path.getsize(local_path)
            self.logger.info(f"开始上传文件到TOS: {object_key}, 文件大小: {total_size} bytes")
            
            # 进度回调函数
            import time
            start_time = time.time()
            last_logged_rate = [0]  # 使用列表来存储可变值
            def progress_callback(consumed_bytes: int, total_bytes: int, rw_once_bytes: int, type: DataTransferType):
                if total_bytes:
                    rate = int(100 * float(consumed_bytes) / float(total_bytes))
                    # 计算上传速度 (bytes/s)
                    elapsed_time = time.time() - start_time
                    upload_speed = consumed_bytes / elapsed_time if elapsed_time > 0 else 0
                    # 转换为更友好的单位 (KB/s, MB/s)
                    if upload_speed > 1024 * 1024:
                        upload_speed_str = f'{upload_speed / (1024 * 1024):.2f} MB/s'
                    elif upload_speed > 1024:
                        upload_speed_str = f'{upload_speed / 1024:.2f} KB/s'
                    else:
                        upload_speed_str = f'{upload_speed:.2f} B/s'
                    # 每10%更新一次进度，避免日志过于频繁
                    if rate - last_logged_rate[0] >= 10 or rate == 100:
                        self.logger.info(f"普通上传进度: {rate}%, 已上传: {consumed_bytes}/{total_bytes} bytes, 速度: {upload_speed_str}")
                        last_logged_rate[0] = rate
            
            # 上传文件
            result = self.client.put_object_from_file(
                self.bucket,
                object_key,
                local_path,
                data_transfer_listener=progress_callback
            )
            
            # 检查上传结果
            if result.status_code != 200:
                raise Exception(f"文件上传失败，状态码: {result.status_code}")
                
            self.logger.info(f"文件上传成功: {object_key}")
            return object_key
                
        except tos.exceptions.TosClientError as e:
            self.logger.error(f"TOS客户端错误: {e.message}, 原因: {e.cause}")
            raise
            
        except tos.exceptions.TosServerError as e:
            self.logger.error(
                f"TOS服务器错误:\n"
                f"- 状态码: {e.status_code}\n"
                f"- 错误码: {e.code}\n"
                f"- 消息: {e.message}\n"
                f"- 请求ID: {e.request_id}\n"
                f"- 请求URL: {e.request_url}"
            )
            raise
            
        except Exception as e:
            self.logger.error(f"上传过程中发生未知错误: {str(e)}")
            raise

    def multipart_upload(self, local_path: str, part_size: int = 20 * 1024 * 1024, max_workers: int = 8, max_retries: int = 3) -> str:
        """分片上传视频到TOS并在上传成功
        
        Args:
            local_path (str): 本地文件路径
            part_size (int): 分片大小，默认20MB
            max_workers (int): 最大并发线程数，默认8
            max_retries (int): 单个分片最大重试次数，默认3
        
        Returns:
            str: object_key
            
        Raises:
            FileNotFoundError: 文件不存在
            Exception: 上传失败或其他错误
        """
        
        upload_id = None
        object_key = ""
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        try:

            # 获取文件信息
            file_name = os.path.basename(local_path)
            object_key = f"{self.remote_path}/{file_name}"
            total_size = os.path.getsize(local_path)
            
            self.logger.info(f"开始分片上传文件到TOS: {object_key}, 文件大小: {total_size} bytes")
            
            # 进度跟踪
            start_time = time.time()
            uploaded_bytes = [0]  # 使用列表来存储可变值
            last_logged_rate = [0]
            progress_lock = threading.Lock()
            
            def update_progress(bytes_uploaded: int):
                with progress_lock:
                    uploaded_bytes[0] += bytes_uploaded
                    rate = int(100 * float(uploaded_bytes[0]) / float(total_size))
                    elapsed_time = time.time() - start_time
                    upload_speed = uploaded_bytes[0] / elapsed_time if elapsed_time > 0 else 0
                    
                    if upload_speed > 1024 * 1024:
                        upload_speed_str = f'{upload_speed / (1024 * 1024):.2f} MB/s'
                    elif upload_speed > 1024:
                        upload_speed_str = f'{upload_speed / 1024:.2f} KB/s'
                    else:
                        upload_speed_str = f'{upload_speed:.2f} B/s'
                    
                    if rate - last_logged_rate[0] >= 5 or rate == 100:
                        self.logger.info(f"分片上传进度: {rate}%, 已上传: {uploaded_bytes[0]}/{total_size} bytes, 速度: {upload_speed_str}")
                        last_logged_rate[0] = rate
            
            # 初始化分片上传任务
            multi_result = self.client.create_multipart_upload(
                self.bucket, 
                object_key, 
                acl=tos.ACLType.ACL_Public_Read,
                storage_class=tos.StorageClassType.Storage_Class_Standard
            )
            upload_id = multi_result.upload_id
            self.logger.info(f"分片上传任务初始化成功，upload_id: {upload_id}")
            
            # 预读文件分片数据到内存
            parts_data = []
            with open(local_path, 'rb') as f:
                part_number = 1
                offset = 0
                while offset < total_size:
                    num_to_upload = min(part_size, total_size - offset)
                    f.seek(offset)
                    part_data = f.read(num_to_upload)
                    parts_data.append((part_number, part_data, offset, num_to_upload))
                    offset += num_to_upload
                    part_number += 1
            
            self.logger.info(f"文件分片完成，共{len(parts_data)}个分片，开始并发上传")
            
            # 并发上传分片
            parts = [None] * len(parts_data)  # 预分配结果数组
            
            def upload_part_with_retry(part_info):
                part_number, part_data, offset, size = part_info
                
                for retry in range(max_retries):
                    try:
                        self.logger.debug(f"上传分片 {part_number}/{len(parts_data)}, 偏移: {offset}, 大小: {size}, 重试: {retry + 1}/{max_retries}")
                        
                        part_result = self.client.upload_part(
                            self.bucket,
                            object_key,
                            upload_id,
                            part_number,
                            content=part_data
                        )
                        
                        # 更新进度
                        update_progress(size)
                        
                        return part_number - 1, part_result  # 返回索引和结果
                        
                    except Exception as e:
                        self.logger.warning(f"分片 {part_number} 上传失败 (重试 {retry + 1}/{max_retries}): {str(e)}")
                        if retry == max_retries - 1:
                            raise Exception(f"分片 {part_number} 上传失败，已达最大重试次数: {str(e)}")
                        time.sleep(2 ** retry)  # 指数退避
            
            # 使用线程池并发上传
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_part = {executor.submit(upload_part_with_retry, part_info): part_info for part_info in parts_data}
                
                for future in as_completed(future_to_part):
                    try:
                        index, part_result = future.result()
                        parts[index] = part_result
                    except Exception as e:
                        self.logger.error(f"分片上传失败: {str(e)}")
                        raise

            # 完成分片上传任务
            self.client.complete_multipart_upload(self.bucket, object_key, upload_id, parts)
            self.logger.info(f"分片上传完成: {object_key}")
            return object_key
            
        except tos.exceptions.TosClientError as e:
            self.logger.error(f"TOS客户端错误: {e.message}, 原因: {e.cause}")
            # 取消分片上传
            if upload_id:
                self._abort_multipart_upload(object_key, upload_id)
            raise
            
        except tos.exceptions.TosServerError as e:
            self.logger.error(
                f"TOS服务器错误:\n"
                f"- 状态码: {e.status_code}\n"
                f"- 错误码: {e.code}\n"
                f"- 消息: {e.message}\n"
                f"- 请求ID: {e.request_id}\n"
                f"- 请求URL: {e.request_url}"
            )
            # 取消分片上传
            if upload_id:
                self._abort_multipart_upload(object_key, upload_id)
            raise
            
        except Exception as e:
            self.logger.error(f"分片上传过程中发生未知错误: {str(e)}")
            # 取消分片上传
            if upload_id:
                self._abort_multipart_upload(object_key, upload_id)
            raise
    
    def _abort_multipart_upload(self, object_key: str, upload_id: str):
        """取消分片上传任务
        
        Args:
            object_key (str): 对象键名
            upload_id (str): 上传任务ID
        """
        try:
            self.client.abort_multipart_upload(self.bucket, object_key, upload_id)
            self.logger.info(f"已取消分片上传任务: {object_key}, upload_id: {upload_id}")
        except tos.exceptions.TosClientError as e:
            self.logger.error(f"取消分片上传失败 - 客户端错误: {e.message}, 原因: {e.cause}")
        except tos.exceptions.TosServerError as e:
            self.logger.error(
                f"取消分片上传失败 - 服务器错误:\n"
                f"- 状态码: {e.status_code}\n"
                f"- 错误码: {e.code}\n"
                f"- 消息: {e.message}\n"
                f"- 请求ID: {e.request_id}\n"
                f"- 请求URL: {e.request_url}"
            )
        except Exception as e:
            self.logger.error(f"取消分片上传时发生未知错误: {str(e)}")