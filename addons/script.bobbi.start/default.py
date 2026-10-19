"""Kodi owns dependency installation; no writes into another addon's directory."""
import xbmc
xbmc.executebuiltin('RunScript(script.bobbi.setup)')
