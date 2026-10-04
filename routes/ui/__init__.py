from http.server import BaseHTTPRequestHandler

from routes.http import HandlerMixin
from routes.ui.account import AccountMixin
from routes.ui.read import ReadMixin
from routes.ui.write import WriteMixin


def make_app_handler(runtime):
    class AppHandler(AccountMixin, ReadMixin, WriteMixin, HandlerMixin, BaseHTTPRequestHandler):
        pass

    AppHandler.runtime = runtime
    return AppHandler
