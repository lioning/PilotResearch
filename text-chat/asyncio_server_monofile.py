import asyncio
import logging

logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s-[%(levelname)s]-[%(funcName)s:%(lineno)d]:%(message)s',
                datefmt='%Y/%m/%d,%H:%M:%S')


# 定义结束异常类
class EndSession(Exception):
    pass

'''
异步通信基类
'''
class AbstractAsyncioBase():
    def __init__(self, reader, writer, loop):
        logging.debug('%s:=======start========' %('AbstractAsyncioBase'))
        self._reader = reader
        self._writer = writer
        self._loop   = loop
        asyncio.run_coroutine_threadsafe(self.on_read(), loop)

    async def on_read(self):
        logging.debug('%s:=======start========' %('on_read'))
        while True:
            logging.debug("reading......")
            line = await self._reader.read(1000)
            if not line:
                print ("[on_read]connection exit.\n")
                break

            print('[on_read]Recieve:%s' %(line.decode('utf-8').rstrip()))

        logging.debug('%s:*******end*******' %('on_read'))

class AsyncioChat(AbstractAsyncioBase):
    ac_in_buffer_size = 65536
    # we don't want to enable the use of encoding by default, because that is a
    # sign of an application bug that we don't want to pass silently

    use_encoding = 0
    encoding = 'latin-1'

    def __init__(self, reader, writer, loop):
        AbstractAsyncioBase.__init__(self, reader, writer, loop)
        # for string terminator matching
        self.ac_in_buffer = b''

    async def on_read(self):
        logging.debug('%s:=======start========' %('AsyncioChat.on_read'))
        while True:
            logging.debug("reading......")
            line = await self._reader.read(self.ac_in_buffer_size)
            if not line:
                print ("[on_read]connection exit.\n")
                break

            print('[AsyncioChat.on_read]Recieve:%s%s' %(line.decode('utf-8').rstrip(),'\n'))
            self.handle_read(line)

        logging.debug('%s:*******end*******' %('AsyncioChat.on_read'))

    def set_terminator(self, term):
        """Set the input delimiter.

        Can be a fixed string of any length, an integer, or None.
        """
        if isinstance(term, str) and self.use_encoding:
            term = bytes(term, self.encoding)
        elif isinstance(term, int) and term < 0:
            raise ValueError('the number of received bytes must be positive')
        self.terminator = term

    def get_terminator(self):
        return self.terminator

    def handle_close(self):
        self._writer.close()

    def handle_read(self, data):
        logging.debug('%s:=======start========' %('AsyncioChat.handle_read'))
        if isinstance(data, str) and self.use_encoding:
            data = bytes(str, self.encoding)
        self.ac_in_buffer = self.ac_in_buffer + data

        # Continue to search for self.terminator in self.ac_in_buffer,
        # while calling self.collect_incoming_data.  The while loop
        # is necessary because we might read several data+terminator
        # combos with a single recv(4096).

        while self.ac_in_buffer:
            lb = len(self.ac_in_buffer)
            terminator = self.get_terminator()
            if not terminator:
                # no terminator, collect it all
                self.collect_incoming_data(self.ac_in_buffer)
                self.ac_in_buffer = b''
            elif isinstance(terminator, int):
                # numeric terminator
                n = terminator
                if lb < n:
                    self.collect_incoming_data(self.ac_in_buffer)
                    self.ac_in_buffer = b''
                    self.terminator = self.terminator - lb
                else:
                    self.collect_incoming_data(self.ac_in_buffer[:n])
                    self.ac_in_buffer = self.ac_in_buffer[n:]
                    self.terminator = 0
                    self.found_terminator()
            else:
                # 3 cases:
                # 1) end of buffer matches terminator exactly:
                #    collect data, transition
                # 2) end of buffer matches some prefix:
                #    collect data to the prefix
                # 3) end of buffer does not match any prefix:
                #    collect data
                terminator_len = len(terminator)
                index = self.ac_in_buffer.find(terminator)
                if index != -1:
                    # we found the terminator
                    if index > 0:
                        # don't bother reporting the empty string
                        # (source of subtle bugs)
                        self.collect_incoming_data(self.ac_in_buffer[:index])
                    self.ac_in_buffer = self.ac_in_buffer[index+terminator_len:]
                    # This does the Right Thing if the terminator
                    # is changed here.
                    self.found_terminator()
                else:
                    # check for a prefix of the terminator
                    index = find_prefix_at_end(self.ac_in_buffer, terminator)
                    if index:
                        if index != lb:
                            # we found a prefix, collect up to the prefix
                            self.collect_incoming_data(self.ac_in_buffer[:-index])
                            self.ac_in_buffer = self.ac_in_buffer[-index:]
                        break
                    else:
                        # no prefix, collect it all
                        self.collect_incoming_data(self.ac_in_buffer)
                        self.ac_in_buffer = b''
        logging.debug('%s:*******end*******' %('AsyncioChat.handle_read'))


    def collect_incoming_data(self, data):
        raise NotImplementedError("must be implemented in subclass")

    def found_terminator(self):
        raise NotImplementedError("must be implemented in subclass")

    def push(self, data):
        logging.debug('%s:=======start========' %('push'))
        logging.debug('data:%s' %(data))
        self._writer.write(data)
        logging.debug('%s:*******end*******' %('push'))

# this could maybe be made faster with a computed regex?
# [answer: no; circa Python-2.0, Jan 2001]
# new python:   28961/s
# old python:   18307/s
# re:        12820/s
# regex:     14035/s

def find_prefix_at_end(haystack, needle):
    l = len(needle) - 1
    while l and not haystack.endswith(needle[:l]):
        l -= 1
    return l

class ChatServer():
    """
    聊天服务器
    """
    def __init__(self, host, port, loop):

        self.co_srv = None
        self._host  = host
        self._port  = port
        self._loop  = loop
        self.users  = {}
        self.main_room = ChatRoom(self)

    async def run_server(self):
        self.co_srv= await asyncio.start_server(self.handle_accept, self._host, self._port, loop=loop)
        print('Server started at http://%s:%s...'%(self._host, self._port))

    def handle_accept(self, reader, writer):
        logging.debug('%s:=======start========' %('handle_accept'))
        ChatSession(self, reader, writer, self._loop)
        logging.debug('%s:*******end********' %('handle_accept'))

class ChatSession(AsyncioChat):
    """
    负责和客户端通信
    """

    def __init__(self, server, reader, writer, loop):
        AsyncioChat.__init__(self, reader, writer, loop)
        self.server = server
        self.set_terminator(b'\n')
        self.data = []
        self.name = None
        self.enter(LoginRoom(server))

    def enter(self, room):
        #一个session属于一个 room， 互相注册，能互相引用对方
        # 从当前房间移除自身，然后添加到指定房间。
        self.leave_current_room();
        self.enter_room(room);

    def leave_current_room(self):
        try:
            cur_room = self.room
        except AttributeError:
            pass
        else:
            cur_room.remove(self)

    def enter_room(self, room):
        self.room = room
        room.add(self)

    def collect_incoming_data(self, data):
        # 接收客户端的数据
        self.data.append(data.decode("utf-8"))

    def found_terminator(self):
        # 当客户端的一条数据结束时的处理
        logging.debug("data=%s" % (self.data))
        line = ''.join(self.data)
        self.data = []
        try:
            self.room.handle(self, line.encode("utf-8"))
        # 退出聊天室的处理
        except EndSession:
            self.handle_close()

    def handle_close(self):
        # 当 session 关闭时，将进入 LogoutRoom
        logging.debug("handle_close")

        AsyncioChat.handle_close(self)
        #asynchat.async_chat.handle_close(self)
        self.enter(LogoutRoom(self.server))

        logging.debug("handle_close end")

class CommandHandler:
    """
    命令处理类
    """

    def unknown(self, session, cmd):
        # 响应未知命令
        # 通过 aynchat.async_chat.push 方法发送消息
        session.push(('Unknown command {} \n'.format(cmd)).encode("utf-8"))

    def handle(self, session, line):
        line = line.decode()
        # 命令处理
        if not line.strip():
            return
        parts = line.split(' ', 1)
        cmd = parts[0]
        try:
            line = parts[1].strip()
        except IndexError:
            line = ''
        # 通过协议代码执行相应的方法
        method = getattr(self, 'do_' + cmd, None)
        try:
            method(session, line)
        except TypeError:
            self.unknown(session, cmd)

class Room(CommandHandler):
    """
    包含多个用户的环境，负责基本的命令处理和广播
    """

    def __init__(self, server):
        self.server = server
        self.sessions = []

    def add(self, session):
        # 一个用户进入房间
        self.sessions.append(session)

    def remove(self, session):
        # 一个用户离开房间
        self.sessions.remove(session)

    def broadcast(self, line):
        # 向所有的用户发送指定消息
        # 使用 asynchat.asyn_chat.push 方法发送数据
        for session in self.sessions:
            session.push(line)

    def do_logout(self, session, line):
        logging.debug("logout......")
        # 退出房间
        raise EndSession


class LoginRoom(Room):
    """
    处理登录用户
    """

    def add(self, session):
        # 用户连接成功的回应
        Room.add(self, session)
        # 使用 asynchat.asyn_chat.push 方法发送数据
        session.push(b'Connect Success')

    def do_login(self, session, line):
        # 用户登录逻辑
        name = line.strip()
        # 获取用户名称
        if not name:
            session.push(b'UserName Empty')
        # 检查是否有同名用户
        elif name in self.server.users:
            session.push(b'UserName Exist')
        # 用户名检查成功后，进入主聊天室
        else:
            session.name = name
            session.enter(self.server.main_room)


class LogoutRoom(Room):
    """
    处理退出用户
    """

    def add(self, session):
        # 从服务器中移除
        try:
            del self.server.users[session.name]
        except KeyError:
            pass


class ChatRoom(Room):
    """
    聊天用的房间
    """

    def add(self, session):
        # 广播新用户进入
        session.push(b'Login Success')
        self.broadcast((session.name + ' has entered the room.\n').encode("utf-8"))
        self.server.users[session.name] = session
        Room.add(self, session)

    def remove(self, session):
        # 广播用户离开
        Room.remove(self, session)
        self.broadcast((session.name + ' has left the room.\n').encode("utf-8"))

    def do_say(self, session, line):
        # 客户端发送消息
        self.broadcast((session.name + ': ' + line + '\n').encode("utf-8"))

    def do_look(self, session, line):
        # 查看在线用户
        session.push(b'Online Users:\n')
        for other in self.sessions:
            session.push((other.name + '\n').encode("utf-8"))

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()

        s = ChatServer('127.0.0.1','8000',loop)
        loop.run_until_complete(s.run_server())
        loop.run_forever()
    except KeyboardInterrupt:
        print("chat server exit")