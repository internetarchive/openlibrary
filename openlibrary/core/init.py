"""Library for starting and monitoring Open Library services.

Many services need to be started to run an Open Library instance. It becomes
quite complicated to manage them manually. This library provides init, a
process manager like unix init, for starting and managing OL services.

This is used only for running the dev instance. In production, these services
are typically run on multiple nodes and monitored using upstart.
"""
import os
import shlex
import subprocess
import sys
import time

import formats

class Init:
    """Init process for starting and managing OL services.
    """
    def __init__(self, config):
        self.services = {}
        for name, value in config.items():
            self.services[name] = Service(self, name, value)
            
        self.files = []
        
    def start(self):
        services = self.services.values()
        
        for s in services:
            s.start()
        
        try:
            while True:
                time.sleep(0.5)
                for s in services:
                    if s.poll() is not None:
                        print "ERROR: %s stopped:" % s.name
                        print "Stopping all services and exiting."
                        self.stop()
                        return
        except KeyboardInterrupt:
            print "Detected keyboard interrupy. Stopping all services and exiting."
            self.stop()
                    
    def stop(self):
        services = self.services.values()
        
        for s in services:
            s.stop()
    
class Service:
    def __init__(self, init, name, config):
        self.init = init
        self.name = name
        self.config = config
        self.process = None
        
    def start(self):
        """Starts the service.
        """
        config = self.config
        
        print "start:", config['command']
        
        args = shlex.split(config['command'])
        cwd = config.get("root", os.getcwd())
        
        stdout = self._open_file(config.get('stdout'), 'a')
        stderr = self._open_file(config.get('stderr'), 'a')
        print self.name, stdout, stderr

        self.process = subprocess.Popen(args, cwd=cwd, stdout=stdout, stderr=stderr)
        return self
        
    def _open_file(self, filename, mode='r'):
        filename = filename or self.name + ".log"
        
        if filename == "-":
            return sys.stdout
        else:
            return open(filename, mode)
        
    def stop(self, timeout=3):
        """Stops the service.
        """
        print "stopping", self.name
        if self.process and self.is_alive():
            self._terminate()
            exit_status = self.wait(timeout)
            
            if exit_status is None:
                self._kill()
                time.sleep(0.1) # wait for process to get killed
                
            return self.poll()
    
    def _terminate(self):
        if self.process:
            print self.process.pid, "terminate"
            self.process.terminate()
        
    def _kill(self):
        if self.process:
            print self.process.pid, "kill"
            self.process.kill()
    
    def wait(self, timeout=None):
        """Wait for the service to complete and returns the exit status.
        """
        if self.process:
            if timeout:
                limit = time.time() + timeout
                exit_status = None
                while exit_status is None and time.time() < limit:
                    time.sleep(0.1)
                    exit_status = self.poll()
                
                return exit_status
            else:
                return self.process.wait()
        
    def poll(self):
        """Returns the exit status if the service is terminated.
        """
        return self.process and self.process.poll()
        
    def is_alive(self):
        """Returns True if the service is running."""
        if self.process is None:
            return False
        return self.poll() is None
        

def main(config_file):
    config = formats.load_yaml(open(config_file).read())
    init = Init(config)
    init.start()