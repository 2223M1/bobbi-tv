"""Kodi settings.xml is the single persistent source of lighting preferences."""
import re
import xbmcaddon

ADDON_ID = 'script.aurora_6s_helper'


def parse_color(color):
    """Accept legacy RGB and Kodi colorbutton's AARRGGBB; LEDs have no alpha."""
    color = color.lstrip('#')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})', color):
        raise ValueError('颜色必须为六位 RGB，例如 0080FF')
    color = color[-6:]
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def migrate_colors():
    addon = xbmcaddon.Addon(ADDON_ID)
    for key in ('normal.color', 'playback.color'):
        value = addon.getSetting(key)
        if re.fullmatch(r'#?[0-9a-fA-F]{6}', value):
            addon.setSetting(key, 'FF' + value.lstrip('#').upper())


def load_profile(playing):
    addon = xbmcaddon.Addon(ADDON_ID)  # reload after another interpreter saves settings
    prefix = 'playback' if playing else 'normal'
    color = addon.getSetting(prefix + '.color') or '0000FF'
    rgb = parse_color(color)
    brightness = int(addon.getSetting(prefix + '.brightness') or '50')
    speed = int(addon.getSetting(prefix + '.speed') or '1536')
    mode = addon.getSetting(prefix + '.mode') or 'steady'
    if not 0 <= brightness <= 100 or speed not in (768, 1536, 3072):
        raise ValueError('亮度或呼吸速度超出范围')
    if mode not in ('steady', 'breathing', 'off'):
        raise ValueError('未知灯光效果')
    return dict(enabled=addon.getSetting('led.enabled') == 'true', name=prefix,
                rgb=rgb, brightness=brightness, mode=mode, speed=speed,
                smooth=addon.getSetting('led.smooth') != 'false')
