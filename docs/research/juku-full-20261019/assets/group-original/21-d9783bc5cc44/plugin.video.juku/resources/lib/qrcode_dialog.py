# -*- coding: utf-8 -*-
import threading
import time
import os
import tempfile
import base64
import urllib.request

try:
    import xbmc
    import xbmcgui
    import xbmcvfs
    # 避免单元测试 Mock 污染
    if type(xbmcgui.WindowDialog).__name__ in ('MagicMock', 'Mock'):
        class DialogBase:
            def __init__(self, *args, **kwargs):
                pass
            def addControl(self, control):
                pass
            def show(self):
                pass
            def close(self):
                pass
    else:
        DialogBase = xbmcgui.WindowDialog
except ImportError:
    xbmc = None
    xbmcgui = None
    xbmcvfs = None
    class DialogBase:
        def __init__(self, *args, **kwargs):
            pass
        def addControl(self, control):
            pass
        def show(self):
            pass
        def close(self):
            pass

def get_qr_temp_dir():
    if xbmcvfs:
        try:
            profile_dir = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.juku/cache")
            if profile_dir:
                if not os.path.exists(profile_dir):
                    os.makedirs(profile_dir, exist_ok=True)
                return profile_dir
        except Exception:
            pass
        try:
            temp_dir = xbmcvfs.translatePath("special://temp")
            if temp_dir:
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir, exist_ok=True)
                return temp_dir
        except Exception:
            pass
    fallback = os.path.join(tempfile.gettempdir(), "juku_cache")
    os.makedirs(fallback, exist_ok=True)
    return fallback

def _cleanup_old_qr_files():
    """清理历史遗留的临时二维码文件，防止坏缓存或堆积"""
    try:
        cache_dir = get_qr_temp_dir()
        now = time.time()
        for fname in os.listdir(cache_dir):
            if fname.startswith("qr_") and fname.endswith(".png"):
                p = os.path.join(cache_dir, fname)
                if now - os.path.getmtime(p) > 60:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
    except Exception:
        pass

def _ensure_rgb_image(image_path, target_size=(300, 300)):
    """
    检查若为 1-bit / 调色板模式（P / 1 / RGBA），转换为真彩色 RGB PNG，
    防止嵌入式平台 (如 CoreELEC / Linux ARM) Kodi GLES 纹理加载器渲染为空白。
    若尺寸小于 target_size，使用最近邻锐利放大，提升大屏清晰度与扫码识别率。
    """
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            mode_changed = False
            resized = False
            im_work = im
            if im_work.mode in ('1', 'P', 'RGBA', 'LA'):
                im_work = im_work.convert('RGB')
                mode_changed = True
            if target_size and (im_work.width < target_size[0] or im_work.height < target_size[1]):
                im_work = im_work.resize(target_size, Image.NEAREST)
                resized = True
            if mode_changed or resized:
                im_work.save(image_path, 'PNG')
    except Exception:
        pass

PROVIDER_NAMES = {
    "1": "阿里云盘", "ALIYUN": "阿里云盘", "aliyun": "阿里云盘", "阿里云盘": "阿里云盘", "阿里网盘": "阿里云盘",
    "2": "夸克网盘", "QUARK": "夸克网盘", "quark": "夸克网盘", "夸克网盘": "夸克网盘",
    "3": "UC网盘", "UC": "UC网盘", "uc": "UC网盘", "UC网盘": "UC网盘",
    "4": "百度网盘", "BAIDU": "百度网盘", "baidu": "百度网盘", "百度网盘": "百度网盘",
    "5": "迅雷网盘", "XUNLEI": "迅雷网盘", "xunlei": "迅雷网盘", "迅雷网盘": "迅雷网盘",
    "6": "123云盘", "CLOUD123": "123云盘", "cloud123": "123云盘", "123云盘": "123云盘", "123网盘": "123云盘",
    "7": "115网盘", "CLOUD115": "115网盘", "cloud115": "115网盘", "115网盘": "115网盘", "115云盘": "115网盘", "115": "115网盘",
    "8": "移动云盘", "CHINA_MOBILE": "移动云盘", "china_mobile": "移动云盘", "移动云盘": "移动云盘",
    "9": "天翼云盘", "CHINA_TELECOM": "天翼云盘", "china_telecom": "天翼云盘", "天翼云盘": "天翼云盘",
    "11": "光鸭云盘", "GUANGYA": "光鸭云盘", "guangya": "光鸭云盘", "光鸭云盘": "光鸭云盘",
}

class QrCodeLoginDialog(DialogBase):
    """
    Kodi 网盘扫码登录界面浮层对话框，支持主线程安全事件循环和异步状态轮询。
    """
    def __init__(self, provider, api_client, manual_mode=False, client_type=None, client_type_name=""):
        super(QrCodeLoginDialog, self).__init__()
        self.provider = provider
        self.api_client = api_client
        self.manual_mode = manual_mode
        self.client_type = client_type
        self.client_type_name = client_type_name
        self.running = True
        self.poll_thread = None
        self.qr_image_path = None
        self.qr_image_rendered = False
        self.dialog_closed = False
        provider_name = PROVIDER_NAMES.get(provider) or (provider if provider and not provider.startswith("CLOUD") else "网盘")
        if self.manual_mode:
            self.status_text = "正在生成{}网页手动输入地址...".format(provider_name)
        elif self.client_type_name:
            self.status_text = "正在生成{}[{}]登录二维码...".format(provider_name, self.client_type_name)
        else:
            self.status_text = "正在生成{}登录二维码...".format(provider_name)
        self.login_success = False

        if xbmcgui:
            # 二维码居中背景和标签控件
            self.bg = xbmcgui.ControlImage(440, 160, 400, 400, "")
            if self.manual_mode:
                self.status_label = xbmcgui.ControlLabel(340, 580, 600, 40, self.status_text, alignment=6)
            else:
                self.status_label = xbmcgui.ControlLabel(440, 580, 400, 40, self.status_text, alignment=6)
            self.addControl(self.bg)
            self.addControl(self.status_label)
            self.qr_image = None
            self.cancel_button = None
            self.cancel_label = None
        else:
            self.bg = None
            self.status_label = None
            self.qr_image = None
            self.cancel_button = None
            self.cancel_label = None

    def start(self):
        # a. Show the dialog using self.show() if xbmcgui is available.
        if xbmcgui:
            self.show()

        # b. Add and focus a "取消" button.
        if xbmcgui:
            self.cancel_button = xbmcgui.ControlButton(540, 540, 200, 40, "")
            self.cancel_label = xbmcgui.ControlLabel(540, 540, 200, 40, "取消", alignment=6)
            self.addControl(self.cancel_button)
            self.addControl(self.cancel_label)
            self.setFocus(self.cancel_button)

        # c. Spawn a background thread to fetch the QR code and poll status.
        self.poll_thread = threading.Thread(target=self.poll_status)
        self.poll_thread.daemon = True
        self.poll_thread.start()

        # d. Run a while self.running: loop on the main thread
        while self.running:
            if self.status_label and self.status_text:
                self.status_label.setLabel(self.status_text)

            if self.qr_image_path and not self.qr_image_rendered:
                if xbmcgui:
                    if self.qr_image:
                        try:
                            self.removeControl(self.qr_image)
                        except Exception:
                            pass
                    self.qr_image = xbmcgui.ControlImage(490, 210, 300, 300, self.qr_image_path)
                    self.addControl(self.qr_image)
                    if self.cancel_button:
                        # 确保取消按钮依然在前面可以被选中
                        self.setFocus(self.cancel_button)
                self.qr_image_rendered = True

            if xbmc:
                xbmc.sleep(100)
            else:
                time.sleep(0.1)

        # e. When the loop exits, call self.close_dialog().
        self.close_dialog()
        if self.login_success and xbmcgui:
            try:
                xbmcgui.Dialog().notification("登录状态", "登录成功", xbmcgui.NOTIFICATION_INFO, 3000)
            except Exception:
                pass
        return self.login_success

    def poll_status(self):
        try:
            if self.manual_mode:
                res = self.api_client.get_manual_login_info(self.provider)
                key = res.get("key")
                image_url = res.get("base64")
                manual_url = res.get("url")
            else:
                res = self.api_client.get_qrcode(self.provider, client_type=self.client_type)
                key = res.get("key")
                image_url = res.get("base64") or res.get("image_url")
        except Exception as e:
            self.status_text = "生成二维码错误: {}".format(str(e))
            self.running = False
            return

        if not image_url:
            self.status_text = "获取二维码失败"
            self.running = False
            return

        # Decode base64 QR code image or download URL to temporary file
        try:
            _cleanup_old_qr_files()
            temp_path = os.path.join(get_qr_temp_dir(), "qr_{}_{}.png".format(self.provider, int(time.time() * 1000)))
            if "base64" in image_url or image_url.startswith("data:image") or (not image_url.startswith("http")):
                # Base64 string
                base64_data = image_url
                if "," in base64_data:
                    base64_data = base64_data.split(",")[1]
                img_data = base64.b64decode(base64_data)
                with open(temp_path, "wb") as f:
                    f.write(img_data)
                _ensure_rgb_image(temp_path)
                self.qr_image_path = temp_path
            else:
                # URL string
                urllib.request.urlretrieve(image_url, temp_path)
                _ensure_rgb_image(temp_path)
                self.qr_image_path = temp_path
        except Exception as e:
            # fallback
            self.qr_image_path = image_url

        provider_name = PROVIDER_NAMES.get(self.provider) or "网盘"
        if self.manual_mode:
            self.status_text = "网页手工登录: {}".format(manual_url)
        elif self.client_type_name:
            self.status_text = "请使用手机{}App扫描[{}]二维码".format(provider_name, self.client_type_name)
        else:
            self.status_text = "请使用手机{}App扫码登录".format(provider_name)

        while self.running:
            try:
                res = self.api_client.check_qrcode_status(self.provider, key)
                status = res.get("status")
            except Exception as e:
                self.status_text = "检查状态错误: {}".format(str(e))
                time.sleep(2)
                continue

            if status == "confirmed":
                self.status_text = "登录成功"
                self.login_success = True
                self.running = False
                break
            elif status == "scanned":
                new_qrcode = res.get("qrcode")
                if new_qrcode:
                    try:
                        base64_data = new_qrcode
                        if "," in base64_data:
                            base64_data = base64_data.split(",")[1]
                        img_data = base64.b64decode(base64_data)
                        temp_path = os.path.join(get_qr_temp_dir(), "qr_{}_{}.png".format(self.provider, int(time.time() * 1000)))
                        with open(temp_path, "wb") as f:
                            f.write(img_data)
                        _ensure_rgb_image(temp_path)
                        self.qr_image_path = temp_path
                        self.qr_image_rendered = False  # 触发主线程重绘
                    except Exception:
                        pass
                self.status_text = res.get("msg") or "已扫码，请在手机端确认登录"
            elif status == "expired":
                self.status_text = "二维码已过期，请重新登录"
                self.running = False
                break
            elif status == "failed":
                self.status_text = "登录失败"
                self.running = False
                break
            time.sleep(2)

    def onControl(self, control):
        if xbmcgui and self.cancel_button and control.getId() == self.cancel_button.getId():
            self.running = False

    def onAction(self, action):
        if action and hasattr(action, 'getId'):
            # Kodi 返回/退出键 ID 分别为 92, 10
            if action.getId() in [92, 10]:
                self.running = False

    def close_dialog(self):
        if self.dialog_closed:
            return
        self.dialog_closed = True
        self.running = False
        if xbmcgui:
            try:
                # 尝试移除所有动态添加的控件以防界面残留
                for ctrl in [self.qr_image, self.cancel_button, self.cancel_label, self.status_label, self.bg]:
                    if ctrl:
                        try:
                            self.removeControl(ctrl)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass
        if self.qr_image_path and os.path.exists(self.qr_image_path):
            try:
                os.remove(self.qr_image_path)
            except Exception:
                pass

class PushQrDialog(DialogBase):
    """
    Kodi 网页推送 QR 显示浮层
    """
    def __init__(self, api_client):
        super(PushQrDialog, self).__init__()
        self.api_client = api_client
        self.running = True
        self.qr_image_path = None
        self.qr_image_rendered = False
        self.dialog_closed = False
        self.status_text = "正在生成网页推送地址..."
        self.auth_code_text = "设备配对码: 获取中..."

        if xbmcgui:
            # 二维码居中背景和标签控件
            self.bg = xbmcgui.ControlImage(440, 160, 400, 400, "")
            self.auth_code_label = xbmcgui.ControlLabel(340, 110, 600, 40, self.auth_code_text, alignment=6)
            self.status_label = xbmcgui.ControlLabel(340, 580, 600, 40, self.status_text, alignment=6)
            self.addControl(self.bg)
            self.addControl(self.auth_code_label)
            self.addControl(self.status_label)
            self.qr_image = None
            self.cancel_button = None
            self.cancel_label = None
        else:
            self.bg = None
            self.auth_code_label = None
            self.status_label = None
            self.qr_image = None
            self.cancel_button = None
            self.cancel_label = None

    def start(self):
        if xbmcgui:
            self.show()
            self.cancel_button = xbmcgui.ControlButton(540, 540, 200, 40, "")
            self.cancel_label = xbmcgui.ControlLabel(540, 540, 200, 40, "关闭", alignment=6)
            self.addControl(self.cancel_button)
            self.addControl(self.cancel_label)
            self.setFocus(self.cancel_button)

        self.poll_thread = threading.Thread(target=self.load_info)
        self.poll_thread.daemon = True
        self.poll_thread.start()

        while self.running:
            if self.status_label and self.status_text:
                self.status_label.setLabel(self.status_text)
            if self.auth_code_label and self.auth_code_text:
                self.auth_code_label.setLabel(self.auth_code_text)

            if self.qr_image_path and not self.qr_image_rendered:
                if xbmcgui:
                    if self.qr_image:
                        try:
                            self.removeControl(self.qr_image)
                        except Exception:
                            pass
                    self.qr_image = xbmcgui.ControlImage(490, 210, 300, 300, self.qr_image_path)
                    self.addControl(self.qr_image)
                    if self.cancel_button:
                        self.setFocus(self.cancel_button)
                self.qr_image_rendered = True

            if xbmc:
                xbmc.sleep(100)
            else:
                time.sleep(0.1)

        self.close_dialog()
        return True

    def load_info(self):
        try:
            res = self.api_client.get_push_url_info()
            image_url = res.get("base64")
            push_url = res.get("url")
            pair_code = res.get("pair_code")
        except Exception as e:
            self.status_text = "生成推送二维码错误: {}".format(str(e))
            self.auth_code_text = "设备配对码: 错误"
            return

        if not image_url:
            self.status_text = "获取推送地址失败"
            self.auth_code_text = "设备配对码: 失败"
            return

        try:
            _cleanup_old_qr_files()
            temp_path = os.path.join(get_qr_temp_dir(), "qr_push_{}.png".format(int(time.time() * 1000)))
            if "base64" in image_url or image_url.startswith("data:image") or (not image_url.startswith("http")):
                base64_data = image_url
                if "," in base64_data:
                    base64_data = base64_data.split(",")[1]
                img_data = base64.b64decode(base64_data)
                with open(temp_path, "wb") as f:
                    f.write(img_data)
                _ensure_rgb_image(temp_path)
                self.qr_image_path = temp_path
            else:
                urllib.request.urlretrieve(image_url, temp_path)
                _ensure_rgb_image(temp_path)
                self.qr_image_path = temp_path
        except Exception:
            self.qr_image_path = image_url

        self.status_text = "{}".format(push_url)

        # 优先使用简短配对码，若不存在再降级解析 device_id
        if pair_code:
            self.auth_code_text = "设备配对码: {}".format(pair_code)
        else:
            try:
                try:
                    from urllib.parse import urlparse, parse_qs
                except ImportError:
                    from urlparse import urlparse, parse_qs
                parsed_url = urlparse(push_url)
                params = parse_qs(parsed_url.query)
                dev_id = params.get("device_id", [""])[0]
                if dev_id:
                    self.auth_code_text = "设备配对码: {}".format(dev_id)
                else:
                    self.auth_code_text = "设备配对码: 未知"
            except Exception:
                self.auth_code_text = "设备配对码: 无法解析"

    def onControl(self, control):
        if xbmcgui and self.cancel_button and control.getId() == self.cancel_button.getId():
            self.running = False

    def onAction(self, action):
        if action and hasattr(action, 'getId'):
            if action.getId() in [92, 10]:
                self.running = False

    def close_dialog(self):
        if self.dialog_closed:
            return
        self.dialog_closed = True
        self.running = False
        if xbmcgui:
            try:
                for ctrl in [self.qr_image, self.cancel_button, self.cancel_label, self.status_label, self.auth_code_label, self.bg]:
                    if ctrl:
                        try:
                            self.removeControl(ctrl)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass
        if self.qr_image_path and os.path.exists(self.qr_image_path):
            try:
                os.remove(self.qr_image_path)
            except Exception:
                pass
