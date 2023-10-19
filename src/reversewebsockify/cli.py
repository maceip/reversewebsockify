"""CLI interface for reversewebsockify."""

import logging
import json
import os.path
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
import tornado.concurrent
import tornado.gen
from tornado.queues import Queue
from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)
q = Queue()


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/ws", SocketHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static'),
        )
        super(Application, self).__init__(handlers, **settings)


class MainHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self):
        self.data_future = q.get()
        SocketHandler.broadcast(self.request.full_url())
        data = yield self.data_future
        self.write(data)
        self.set_status(200)
        self.finish()
    @tornado.gen.coroutine
    def post(self):
        self.data_future = q.get()
        SocketHandler.broadcast(json.loads(self.request.body))
        data = yield self.data_future
        self.write(data)
        self.set_status(200)
        self.finish()
    def on_connection_close(self):
        self.msg_future.set_result(None)
        

class SocketHandler(tornado.websocket.WebSocketHandler):
    waiters = set()

    def check_origin(self, origin):
        return True

    def open(self):
        SocketHandler.waiters.add(self)
        logging.info(
            'New WebSocket Connection: %d total',
            len(SocketHandler.waiters)
        )

    def select_subprotocol(self, subprotocol):
        if len(subprotocol):
            return subprotocol[0]
        return super().select_subprotocol(subprotocol)

    async def on_message(self, message):
        logging.info('new message: %s', message)
        await q.put(message)


    def on_close(self):
        SocketHandler.waiters.remove(self)
        logging.info(
            'Disconnected WebSocket (%d total)',
            len(SocketHandler.waiters)
        )

    @classmethod
    def broadcast(cls, data):
        for waiter in cls.waiters:
            try:
                waiter.write_message(data, binary=True)
            except tornado.websocket.WebSocketClosedError:
                logging.error("Error sending message", exc_info=True)


def relay():
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)
    tornado.ioloop.IOLoop.current().start()




def cli() -> None:
    relay()
