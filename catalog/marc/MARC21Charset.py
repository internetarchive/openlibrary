from SubprocessRPC import SubprocessRPC
import os

def marc8_to_unicode_converter ():
        dir = os.path.dirname(__file__)
        perl = os.getenv ("PHAROS_PERL", "perl")
        marc8_to_utf8_bytes = SubprocessRPC ([perl, os.path.join(dir, "marc8_to_utf8.pl")])
        def marc8_to_unicode (s_marc8):
            utf8_bytes = marc8_to_utf8_bytes (s_marc8)
            if utf8_bytes[0] == '+':
                return unicode (utf8_bytes[1:], "utf_8")
            else:
                raise MARC21Exn(utf8_bytes[1:])
        return marc8_to_unicode

if __name__ == "__main__":
        from sys import stderr
        conv = marc8_to_unicode_converter ()
        s = "foo"
        if (conv (s) == s):
                stderr.write ("ok\n")
        else:
                stderr.write ("bad conversion\n")
