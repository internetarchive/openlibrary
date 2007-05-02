
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
