"""`ikyu` 站點 adapter 匯出。"""

from app.sites.ikyu.adapter import IkyuAdapter
from app.sites.ikyu.client import LiveIkyuHtmlClient

__all__ = ["IkyuAdapter", "LiveIkyuHtmlClient"]
