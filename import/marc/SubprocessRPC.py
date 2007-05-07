from subprocess import Popen, PIPE
import netstring
import sys

class SubprocessRPC:
	def __init__ (self, args, trace=False):
		self.args = args
		self.conn = Popen (args, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
		self.tracing = trace;

	def __call__ (self, arg):
		if (self.tracing):
			sys.stderr.write ("CALL: '%s'\n" % arg)
		netstring.dump (arg, self.conn.stdin)
		r = netstring.load (self.conn.stdout)
		if (self.tracing):
			sys.stderr.write ("RETURN: '%s'\n" % r)
		return r

	#def __del__ (self):
	#	self.conn.stdin.close ()
	#	r = self.conn.wait ()
	#	if r != 0:
	#		raise Exception ("SubprocessRPC process failed with exit code %d" % r)
