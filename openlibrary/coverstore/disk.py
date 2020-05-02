import random
import os
import string

chars = string.ascii_letters + string.digits
def random_string(n):
    return "".join([random.choice(chars) for i in range(n)])

class Disk:
    """Disk interface to store files.

    >>> import os, string
    >>> _ = os.system("rm -rf test_disk")
    >>> disk = Disk("test_disk")
    >>> f1 = disk.write("hello, world!")
    >>> f2 = disk.write(string.ascii_letters)
    >>> f3 = disk.write(string.ascii_letters)
    >>> disk.read(f1)
    'hello, world!'
    >>> disk.read(f2)
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    >>> disk.read(f3)
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    """
    def __init__(self, root):
        self.root = root
        if not os.path.exists(root):
            os.makedirs(root)

    def write(self, data, params={}):
        prefix = params.get('olid', '')
        filename = self.make_filename(prefix)
        path = os.path.join(self.root, filename)
        f = open(path, 'w')
        f.write(data)
        f.close()
        return filename

    def read(self, filename):
        path = os.path.join(self.root, filename)
        if os.path.exists(path):
            return open(path).read()

    def make_filename(self, prefix=""):
        def exists(filename):
            return os.path.exists(os.path.join(self.root, filename))
        filename = prefix + "_" + random_string(4)
        while exists(filename):
            filename = prefix + "_"  + random_string(4)
        return filename


class LayeredDisk:
    """Disk interface over multiple disks.
    Write always happens to the first disk and
    read happens on the first disk where the file is available.
    """
    def __init__(self, disks):
        self.disks = disks

    def read(self, filename):
        for disk in self.disks:
            data = disk.read(filename)
            if data:
                return data

    def write(self, data, headers={}):
        return self.disks[0].write(data, headers)

if __name__ == "__main__":
    import doctest
    doctest.testmod()

