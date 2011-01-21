import web
import os
import re
import shutil
from collections import defaultdict

template = """\
$def with (mod, submodules)
$ name = mod.split(".")[-1]

$name
$("=" * len(name))

$if submodules:
    Submodules
    ----------

    .. toctree::
       :maxdepth: 1

       $for m in submodules: $m

    Documentation
    -------------
    
    .. automodule:: $mod
$else:
    .. automodule:: $mod
"""

t = web.template.Template(template)

def docpath(path):
    return "docs/api/" + path.replace(".py", ".rst").replace("__init__", "index")
    
def modname(path):
    return path.replace(".py", "").replace("/__init__", "").replace("/", ".")
    
def write(path, text):
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    
    print "writing", path
    f = open(path, "w")
    f.write(text)
    f.close()
    
def generate_doc_file(path):
    if path.endswith("__init__.py"):
        submodules = os.listdir(os.path.dirname(path))
    else:
        submodules = []
        
    mod = modname(path)
    
    text = str(t(mod, submodules))
    write(docpath(path), text)
    
def find_python_sources(dir):
    ignores = [
        "openlibrary/catalog.*",
        "openlibrary/solr.*",
        "openlibrary/plugins/recaptcha.*",
        "openlibrary/plugins/akismet.*",
        "openlibrary/plugins/bookrev.*",
        "openlibrary/plugins/copyright.*",
        "openlibrary/plugins/heartbeat.*",
        ".*tests",
        "infogami/plugins.*",
        "infogami.utils.markdown",
    ]
    re_ignore = re.compile("|".join(ignores))

    for dirpath, dirnames, filenames in os.walk(dir):
        if re_ignore.match(dirpath):
            print "ignoring", dirpath
            continue
            
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)
    
def generate_docs(dir):
    shutil.rmtree(docpath(dir), ignore_errors=True)
    
    paths = list(find_python_sources(dir))
    
    submodule_dict = defaultdict(list)
    
    for path in paths:
        dir = os.path.dirname(path)
        
        if path.endswith("__init__.py"):
            dir = os.path.dirname(dir)
            
        submodule_dict[dir].append(path)
    
    for path in paths:
        dirname = os.path.dirname(path)
        if path.endswith("__init__.py"):
            submodules = [web.lstrips(docpath(s), docpath(dirname) + "/") for s in submodule_dict[dirname]]
        else:
            submodules = []
        submodules.sort()
        
        mod = modname(path)
        text = str(t(mod, submodules))
        write(docpath(path), text)
                
def generate_index():
    filenames = sorted(os.listdir("docs/api"))
    
    f = open("docs/api/index.rst", "w")
    
    f.write("API Documentation\n")
    f.write("=================\n")
    f.write("\n")
    f.write(".. toctree::\n")
    f.write("   :maxdepth: 1\n")
    f.write("\n")
    f.write("\n".join("   " + filename for filename in filenames))

def main():    
    generate_docs("openlibrary")
    generate_docs("infogami")
    #generate_index()

if __name__ == "__main__":
    main()
