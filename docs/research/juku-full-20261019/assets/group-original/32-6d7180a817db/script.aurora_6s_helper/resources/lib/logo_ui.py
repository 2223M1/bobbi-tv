"""User-invoked boot-logo preview and confirmed write; no Kodi service hook."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xbmc
import xbmcgui
import xbmcvfs

ROOT=Path(__file__).resolve().parents[1]/'logo'
BACKEND=ROOT/'backend.py'
NOTICE='请勿断电、拔盘、退出 Kodi 或进行其他操作。'
MAX_IMAGE=32*1024**2


def call(*args):
    # Writes must never be killed by a frontend timeout.
    result=subprocess.run(['/usr/bin/python3',str(BACKEND),*args],capture_output=True,
        encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    if result.returncode:raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Logo 操作失败')
    return json.loads(result.stdout)


class Preview(xbmcgui.WindowDialog):
    def __init__(self, path, writable):
        super().__init__()
        self.accepted=False;self.writable=writable
        sx,sy=self.getWidth()/1280,self.getHeight()/720
        def rect(x,y,w,h):return tuple(int(v*s) for v,s in zip((x,y,w,h),(sx,sy,sx,sy)))
        self.addControl(xbmcgui.ControlImage(*rect(0,0,1280,720),str(ROOT/'black.png')))
        self.addControl(xbmcgui.ControlImage(*rect(160,40,960,540),path,aspectRatio=2))
        text='预览第一屏（Android / CE 共用）' if writable else '当前第一屏'
        self.addControl(xbmcgui.ControlLabel(*rect(60,585,1160,35),text,font='font13'))
        self.addControl(xbmcgui.ControlLabel(*rect(60,620,1160,35),'关闭预览后仍需确认才会写入；返回键可取消。' if writable else '返回键关闭。',font='font13'))
        self.back=xbmcgui.ControlButton(*rect(700,660,220,48),'取消' if writable else '关闭',
            focusTexture=str(ROOT/'focus.png'),noFocusTexture=str(ROOT/'button.png'))
        self.addControl(self.back)
        if writable:
            self.next=xbmcgui.ControlButton(*rect(940,660,220,48),'使用此图片',
                focusTexture=str(ROOT/'focus.png'),noFocusTexture=str(ROOT/'button.png'))
            self.addControl(self.next)
            self.back.controlRight(self.next);self.back.controlLeft(self.next)
            self.next.controlLeft(self.back);self.next.controlRight(self.back)
        self.setFocus(self.back)

    def onControl(self, control):
        # Kodi callbacks can wrap the same GUI control in a new Python object.
        # Match the stable control ID, not Python object identity/equality.
        control_id=control.getId()
        if control_id==self.back.getId():self.close()
        elif self.writable and control_id==self.next.getId():self.accepted=True;self.close()

    def onAction(self, action):
        if action.getId() in (9,10,92,216):self.close()


def discard(result):
    # Only throw away an unexecuted private task, never its completed backup.
    folder=Path(result['folder']);base=Path('/storage/.config/aurora-logo')
    if folder.parent==base and folder.resolve()==folder:
        state=json.loads((folder/'status.json').read_text(encoding='utf-8'))
        if state['phase']=='prepared':shutil.rmtree(folder)


def main():
    dialog=xbmcgui.Dialog()
    index=dialog.select('启动第一屏', ['查看当前第一屏','选择图片更换第一屏','恢复内置原厂第一屏'])
    if index<0:return
    mode=('current','custom','stock')[index]
    result=None
    with tempfile.TemporaryDirectory(prefix='aurora-logo-input-') as tmp:
        args=['prepare',mode]
        if mode=='custom':
            selected=dialog.browse(1,'选择 PNG / JPG / BMP 图片','files','.png|.jpg|.jpeg|.bmp',False,False)
            if not selected:return
            source=xbmcvfs.File(selected)
            try:
                if source.size()>MAX_IMAGE:raise ValueError('图片文件不能超过 32 MiB')
                dest=Path(tmp)/'input-image';total=0
                with dest.open('wb') as f:
                    while True:
                        data=source.readBytes(1024**2)
                        if not data:break
                        total+=len(data)
                        if total>MAX_IMAGE:raise ValueError('图片文件不能超过 32 MiB')
                        f.write(data)
            finally:source.close()
            args+=['--image',str(dest)]
        progress=xbmcgui.DialogProgressBG();progress.create('启动第一屏','读取分区、校验素材并生成预览…')
        try:result=call(*args)
        finally:progress.close()
        try:
            preview=Preview(result['preview'],mode!='current');preview.doModal()
            if not preview.accepted:return
            warning=('将替换 Android 和 CE 共用的启动第一屏，原分区已保存备份。不会清空应用或用户数据。\n'
                '写入中断可能导致第一屏损坏，插件作者不对此操作造成的损失负责。\n'+NOTICE)
            if mode=='stock':warning='使用已核验的 6S 原厂“腾讯极光 / 互联八方”素材，适用于本助手支持的 4 Pro/6S。\n'+warning
            if not dialog.yesno('确认写入第一屏',warning,nolabel='取消',yeslabel='确认写入'):return
            progress=xbmcgui.DialogProgressBG();progress.create('写入第一屏',NOTICE)
            try:
                outcome=call('apply',result['folder'],'--sha256',result['new_sha256'],'--confirm')
            finally:progress.close()
            dialog.ok('第一屏已更新',outcome['message']+'\n备份：'+outcome['backup']+'\n请通过关机菜单手动重启查看。')
        finally:
            if result:discard(result)
