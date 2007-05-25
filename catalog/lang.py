import sys
from StringIO import StringIO
import time, re

def cftime():
	t,m = divmod(time.time(), 1.0)
	return re.sub(r':\d\d ', r'\1.%02d ',
		      (time.ctime(t), int(100*m)))
	
def warn (msg):
	sys.stderr.write ("%s\n" % msg)

def die (msg):
	raise Exception (msg)

def lines_positions (input):
	done = False
	while not done:
		line = StringIO ()
		pos = input.tell ()
		while True:
			ch = input.read (1)
			if len (ch) == 0:
				done = True
				break
			elif ch == '\n':
				break
			else:
				line.write (ch)
		yield (line.getvalue (), pos)

class Box:
	def __init__ (self):
		self.empty = True
	def set (self, val):
		self.value = val
		self.empty = False
	def get (self):
		if self.empty:
			raise Exception ("get: box is empty")
		else:
			return self.value

def memoized (f):
        box = Box ()
        def get ():     
		if box.empty:
			box.set (f ())
                return box.get ()
        return get
