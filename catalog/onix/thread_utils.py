# 2007 dbg for the Internet Archive

import sys
from threading import Thread, Lock, Condition

class AsyncChannel:
	# yes, i believe this is just Queue ... i was new to python and couldn't find it

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
	# the producer function will be invoked with a single argument, a "produce" function.
	# the producer may pass an object to this "produce" function any number of times before
	# returning.  the values thus passed will, in turn, be produced by the generator which
	# is the return value of threaded_generator().
	#
	# this provides a sort of coroutine facility, because python's generators can't do that:
	# they can only yield values from the bottom of the call stack.  sometimes you need to
	# keep control context between producing values.

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
