"""Homatics PCM transport; ATVV decoding is shared with UR02."""
from .cmcc_audio import CmccClient


class B25Client(CmccClient):
    def __init__(self, profile, token):
        super().__init__(profile, token, socket_name='b25.sock')
