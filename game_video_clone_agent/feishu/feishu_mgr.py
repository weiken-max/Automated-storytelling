import os
import json
from io import BytesIO
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from typing import Optional, Tuple

# 用户投喂剧本：单文件大小上限（字节）
MAX_SCRIPT_UPLOAD_BYTES = 800 * 1024

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

    def send_image_message(self, receive_id: str, receive_id_type: str, image_path: str) -> Optional[str]:
        """发送单张图片消息（先上传再投递），用于单批宫格预览等轻量场景。"""
        image_key = self.upload_image(image_path)
        if not image_key:
            return None
        message_content = json.dumps({"image_key": image_key}, ensure_ascii=False)
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(receive_id)
                          .msg_type("image")
                          .content(message_content)
                          .build()) \
            .build()
        resp = self._with_retry(self.client.im.v1.message.create, request)
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

    def download_message_file_bytes(self, message_id: str, file_key: str) -> Optional[bytes]:
        """
        下载会话消息中的用户上传文件（需与消息同会话，使用 message_id + file_key）。
        见开放平台：获取消息中的资源文件（type=file）。
        """
        if not message_id or not file_key:
            return None
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type("file") \
            .build()
        try:
            getter = getattr(self.client.im.v1, "message_resource", None)
            if getter is None:
                print("  [FeishuMgr] SDK 缺少 im.v1.message_resource，无法下载消息文件")
                return None
            resp = self._with_retry(getter.get, request)
        except Exception as e:
            print(f"  [FeishuMgr] download_message_file_bytes 异常: {e}")
            return None
        if not resp or not getattr(resp, "file", None):
            return None
        try:
            data = resp.file.read()
            return data if isinstance(data, (bytes, bytearray)) else None
        except Exception as e:
            print(f"  [FeishuMgr] 读取下载流失败: {e}")
            return None

    @staticmethod
    def script_text_from_upload_bytes(body: bytes, file_name: str) -> Tuple[Optional[str], str]:
        """
        将用户上传的文件解析为剧本纯文本。
        返回 (text, error_message)；成功时 error_message 为空字符串。
        """
        if not body:
            return None, "文件为空。"
        if len(body) > MAX_SCRIPT_UPLOAD_BYTES:
            return None, f"文件过大（>{MAX_SCRIPT_UPLOAD_BYTES // 1024}KB），请精简、分段发送或改用纯文字粘贴。"

        fn = (file_name or "").strip().lower()
        ext = Path(fn).suffix

        _binary_exts = (
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
            ".mp4", ".mov", ".avi", ".mkv", ".zip", ".rar", ".7z",
            ".pdf", ".xlsx", ".xls", ".ppt", ".pptx",
        )
        if ext in _binary_exts:
            return None, "剧本投喂仅支持 .txt / .md / .docx，或直接在聊天框粘贴文字；请勿上传图片/音视频/压缩包等。"

        if ext == ".docx":
            try:
                from docx import Document
            except ImportError:
                return None, "服务器未安装 python-docx，暂无法读取 .docx，请改用 .txt 或粘贴文字。"
            try:
                doc = Document(BytesIO(body))
                parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
                text = "\n".join(parts)
            except Exception as e:
                return None, f"无法解析 Word 文档：{e}"
            if not text.strip():
                return None, "Word 文档中未读到正文段落。"
            return text.strip(), ""

        if ext not in ("", ".txt", ".md", ".markdown", ".text", ".log"):
            return None, "不支持的文本扩展名，请上传 .txt / .md / .docx，或直接粘贴文字。"

        try:
            text = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = body.decode("gbk")
            except UnicodeDecodeError:
                return None, "无法用 UTF-8 或 GBK 解码该文件，请另存为 UTF-8 编码的 .txt 再上传。"

        if "\x00" in text[:2000]:
            return None, "文件内容不像纯文本，请将剧本保存为 .txt（UTF-8）再上传。"

        text = text.strip()
        if not text:
            return None, "文件内容为空。"
        return text, ""

