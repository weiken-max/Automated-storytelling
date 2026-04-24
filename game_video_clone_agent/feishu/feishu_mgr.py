import os
import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from typing import Optional, Dict

class FeishuManager:
    """飞书核心通讯员"""
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def _with_retry(self, func, *args, **kwargs):
        import time
        for i in range(3):
            try:
                resp = func(*args, **kwargs)
                if resp.success(): return resp
                # 如果是接口报错，暂时不重试，直接返回
                return resp
            except Exception as e:
                if i == 2: raise e
                print(f"  [FeishuMgr] 网络抖动(第{i+1}次), 正在重试: {e}")
                time.sleep(1)
        return None

    def send_text(self, receive_id: str, receive_id_type: str, content: str):
        message_content = json.dumps({"text": content}, ensure_ascii=False)
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(receive_id)
                          .msg_type("text")
                          .content(message_content)
                          .build()) \
            .build()
        return self._with_retry(self.client.im.v1.message.create, request)

    def send_card(self, receive_id: str, receive_id_type: str, card_content: dict):
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(receive_id)
                          .msg_type("interactive")
                          .content(json.dumps(card_content, ensure_ascii=False))
                          .build()) \
            .build()
        resp = self._with_retry(self.client.im.v1.message.create, request)
        # 返回 message_id 供后续 patch 使用
        if resp and resp.success() and resp.data:
            return resp.data.message_id
        return None

    def update_card(self, message_id: str, card_content: dict) -> bool:
        """原地更新已有卡片消息（patch），避免刷新时重新发一张新卡片"""
        try:
            request = PatchMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(PatchMessageRequestBody.builder()
                              .content(json.dumps(card_content, ensure_ascii=False))
                              .build()) \
                .build()
            resp = self._with_retry(self.client.im.v1.message.patch, request)
            return bool(resp and resp.success())
        except Exception as e:
            print(f"  [FeishuMgr] update_card 失败: {e}")
            return False

    def upload_image(self, image_path: str) -> Optional[str]:
        if not os.path.exists(image_path): return None
        
        # 定义一个内部函数供 _with_retry 调用，保证每次重试都重新读取文件流
        def _do_upload():
            with open(image_path, "rb") as f:
                request = CreateImageRequest.builder() \
                    .request_body(CreateImageRequestBody.builder()
                                  .image_type("message")
                                  .image(f)
                                  .build()) \
                    .build()
                return self.client.im.v1.image.create(request)
        
        resp = self._with_retry(_do_upload)
        if resp and resp.success():
            return resp.data.image_key
        return None

    def upload_video(self, video_path: str) -> Optional[str]:
        if not os.path.exists(video_path): return None
        
        def _do_upload():
            with open(video_path, "rb") as f:
                request = CreateFileRequest.builder() \
                    .request_body(CreateFileRequestBody.builder()
                                  .file_type("mp4")
                                  .file_name(os.path.basename(video_path))
                                  .file(f)
                                  .build()) \
                    .build()
                return self.client.im.v1.file.create(request)
        
        resp = self._with_retry(_do_upload)
        if resp and resp.success():
            return resp.data.file_key
        return None

