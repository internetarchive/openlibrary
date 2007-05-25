import sys
from threading import Thread, Lock, Condition

class AsyncChannel:

	def __init__ (self, buffer_size=1):
		self.buffer = []
		self.max_items = buffer_size
		self.lock = Lock ()
		self.not_empty = Condition (self.lock)
		self.not_full = Condition (self.lock)

	def get (self):
		self.lock.acquire ()
		while len (self.buffer) == 0:
			self.not_empty.wait ()
		val = self.buffer.pop (0)
		self.not_full.notifyAll ()
		self.lock.release ()
		return val

	def put (self, val):
		self.lock.acquire ()
		while len (self.buffer) == self.max_items:
			self.not_full.wait ()
		self.buffer.append (val)
		self.not_empty.notifyAll ()
		self.lock.release ()

class ForeignException:

	def __init__ (self, exc_type, exc_value, exc_traceback):
		self.exc_type = exc_type
		self.exc_value = exc_value
		self.exc_traceback = exc_traceback

	def re_raise (self):
		raise self.exc_type, self.exc_value, self.exc_traceback

def ForeignException_extract ():
	(exc_type, exc_value, exc_traceback) = sys.exc_info()
	return ForeignException (exc_type, exc_value, exc_traceback)

def threaded_generator (producer, buffer_size=1):

	t = None
	chan = AsyncChannel (buffer_size)

	def produce (val):
		chan.put (val)

	def main ():
		try:
			producer (produce)
			chan.put (StopIteration ())
		except:
			chan.put (ForeignException_extract ())

	def generator ():
		while True:
			v = chan.get ()
			if isinstance (v, StopIteration):
				break
			if isinstance (v, ForeignException):
				v.re_raise ()
			else:
				yield v

	t = Thread (target=main)
	t.setDaemon (True)
	t.start ()
	return generator ()
