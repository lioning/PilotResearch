import asyncio
import logging

logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s-[%(levelname)s]-[%(funcName)s:%(lineno)d]:   %(message)s',
                datefmt='%Y/%m/%d,%H:%M:%S')


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
