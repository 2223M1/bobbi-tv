"""Show a short-lived LAN configuration URL as a QR code on the TV."""
import os
from pathlib import Path
import secrets
import struct
import threading
import time

import xbmc
import xbmcgui
import xbmcvfs
import zlib

from ..qrcodegen import QrCode
from ..strings import text

BACK = (9, 10, 92, 216, 247, 257)
PROPERTY = 'VoiceInput.'
# How many per-address properties the service publishes; the dialog reads and
# clears exactly this range.
ADDRESSES = 4


def qr_png(url, destination, width=420):
    """Write a grayscale PNG QR code for ``url``."""
    code = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    scale = max(1, min(10, width // (code.get_size() + 8)))
    inset = (width - code.get_size() * scale) // 2
    pixels = bytearray()
    for y in range(width):
        pixels.append(0)  # PNG filter type: none
        for x in range(width):
            inside = inset <= x < inset + code.get_size() * scale and \
                inset <= y < inset + code.get_size() * scale
            dark = inside and code.get_module((x - inset) // scale, (y - inset) // scale)
            pixels.append(0 if dark else 255)

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    png = (b'\x89PNG\r\n\x1a\n' +
           chunk(b'IHDR', struct.pack('>2I5B', width, width, 8, 0, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(bytes(pixels), 9)) +
           chunk(b'IEND', b''))
    with Path(destination).open('wb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(png)


class ConfigureWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.stopped = kwargs.pop('stopped')
        self.ready = threading.Event()
        super().__init__(*args, **kwargs)

    def onInit(self):
        xbmc.log('[voice-input] configure dialog onInit', xbmc.LOGINFO)
        self.setFocusId(400)
        self.ready.set()

    def onAction(self, action):
        if action.getId() in BACK:
            self.stopped.set()
            self.close()

    def onClick(self, identifier):
        if identifier == 400:
            self.stopped.set()
            self.close()


def show(addon, profile):
    """Ask the service for an entry, then display it as a QR code."""
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    _clear(home)
    home.setProperty(PROPERTY + 'ConfigureRequested', secrets.token_hex(8))
    url = ''
    count = 0
    for unused in range(60):
        if monitor.waitForAbort(.05):
            return
        url = home.getProperty(PROPERTY + 'ConfigureURL')
        if url:
            try:
                count = int(home.getProperty(PROPERTY + 'ConfigureURLCount'))
            except ValueError:
                count = 1
            break
    if not url:
        # The service owns the HTTP listener; without it there is nothing to serve.
        xbmcgui.Dialog().ok(text(31090), text(31091))
        return
    pin = home.getProperty(PROPERTY + 'ConfigurePIN')
    # Read every address individually: a space-separated list written back does
    # not notify the GUI, so the dialog would never see the alternates.
    addresses = [home.getProperty(PROPERTY + 'ConfigureURL%d' % index)
                 for index in range(1, min(count, ADDRESSES) + 1)]
    alternates = [item for item in addresses if item and item != url]
    image = Path(profile) / ('configure-' + secrets.token_hex(8) + '.png')
    stopped = threading.Event()
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    window = ConfigureWindow('ConfigureVoiceInput.xml', root, 'Default', '1080i',
                             stopped=stopped)
    try:
        qr_png(url, image)
        window.show()
        while not stopped.is_set() and not monitor.abortRequested():
            if window.ready.is_set():
                # Content that changes belongs in the update loop: text assigned
                # before the dialog has drawn is lost once it paints itself.
                window.getControl(301).setImage(str(image))
                window.getControl(302).setText(text(31092))
                window.getControl(303).setLabel(url.split('#')[0])
                window.getControl(304).setLabel(text(31093) if not alternates else
                    text(31094, '  '.join(item.split('#')[0] for item in alternates)))
                # The PIN is the only secret the TV shows and the page does not,
                # so it is the fallback for a computer that types the address.
                window.getControl(305).setLabel(text(31095, pin) if pin else '')
            if monitor.waitForAbort(.1):
                break
    finally:
        window.close()
        image.unlink(missing_ok=True)
        _clear(home)


def _clear(home):
    # ConfigurePIN and ConfigureURL<N>/ConfigureURLCount are separate property
    # names, not prefixes of ConfigureURL: closing the dialog has to leave no
    # address and no code behind on the home window for the rest of the session.
    home.clearProperty(PROPERTY + 'ConfigureURL')
    home.clearProperty(PROPERTY + 'ConfigureURLCount')
    home.clearProperty(PROPERTY + 'ConfigurePIN')
    for index in range(1, ADDRESSES + 1):
        home.clearProperty(PROPERTY + 'ConfigureURL%d' % index)
