from SubprocessRPC import SubprocessRPC
import os

def marc8_to_unicode_converter ():
        repo = os.getenv ("PHAROS_REPO")
        perl = os.getenv ("PHAROS_PERL")
        marc8_to_utf8_bytes = SubprocessRPC ([perl, "%s/catalog/marc/%s" % (repo, "marc8_to_utf8.pl")])
        def marc8_to_unicode (s_marc8):
                utf8_bytes = marc8_to_utf8_bytes (s_marc8)
                return unicode (utf8_bytes, "utf_8")
        return marc8_to_unicode

if __name__ == "__main__":
        from sys import stderr
        conv = marc8_to_unicode_converter ()
        s = "foo"
        if (conv (s) == s):
                stderr.write ("ok\n")
        else:
                stderr.write ("bad conversion\n")
