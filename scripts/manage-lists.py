#! /usr/bin/env python
"""Script to manage lists.

Usage: ./scripts/manage-lists.py command settings.yml args
"""
import _init_path
import sys, os, shutil, tempfile, time, re
import multiprocessing, itertools
import optparse
import simplejson
import couchdb
import web

class Command:
    def __init__(self):
        self.parser = optparse.OptionParser(add_help_option=False)
        self.parser.add_option("--help", action="store_true", help="display this help message")

        self.init()

    def add_option(self, *a, **kw):
        self.parser.add_option(*a, **kw)

    def add_subcommand(self, name, cmd):
        cmd.name = name
        self.subcommands.append(cmd)
        
    def main(self):
        self(sys.argv[1:])

    def __call__(self, args):
        args = list(args)
        options, args = self.parser.parse_args(args)
        kwargs = options.__dict__
        
        help = kwargs.pop('help', False)
        if help:
            self.help()
        else:
            self.run(*args, **kwargs)

    def init(self):
        pass
        
class MakeEdtions(Command):
    def run(self):
        for line in sys.stdin:
            json = line.strip().split("\t")[-1]
            work = simplejson.loads(json)
            
            seeds = [seed for seed, info in GenerateSeeds().map(work)]
            for e in work['editions']:
                e["seeds"] = seeds
            print "%s\t%s" % (e['key'].encode('utf-8'), simplejson.dumps(e))

class SortWorker:
    def __init__(self, indir, outdir):
        self.indir = indir
        self.outdir = outdir
    
    def __call__(self, filename):
        os.system("sort -S 1G -k1 %s/%s -o %s/%s" % (self.indir, filename, self.outdir, filename))

class GroupWorksWorker:
    """Worker to group edtions of a work."""
    def __init__(self, indir, outdir):
        self.indir = indir
        self.outdir = outdir

    def __call__(self, filename):
        infile = os.path.join(self.indir, filename)
        outfile = os.path.join(self.outdir, filename)
        out = open(outfile, 'w', 50*1024*1024)
        
        for work in self.parse(self.read(open(infile))):
            out.write(work['key'] + "\t" + simplejson.dumps(work) + "\n")
        out.close()

    def read(self, f):
        for line in f:
            key, json = line.strip().split("\t", 1)
            yield key, json

    def parse(self, rows):
        for key, chunk in itertools.groupby(rows, lambda row: row[0]):
            docs = [simplejson.loads(json) for key, json in chunk]

            work = None
            editions = []

            for doc in docs:
                if doc['type']['key'] == '/type/work':
                    work = doc
                else:
                    editions.append(doc)

            if not work:
                work = {
                    "key": editions[0]['works'][0]['key'],
                    "type": {"key": "/type/work"},
                    "dummy_": True
                }

            work['editions'] = editions
            yield work
            
class ProcessChangesets(Command):
    """Command to process changesets.
    
    Changesets are processed and effected seeds are generated for each changeset. This involves accessing infobase for 
    """
    def run(self, configfile):
        pass

class ProcessDump(Command):
    """Processes works and edition dumps and generates documents that can be loaded into couchdb.
    
    The generated files:
        * works.txt
        * editions.txt
    """
    def init(self):
        self.parser.add_option("--no-cleanup", action="store_true", default=False)
        self.parser.add_option("--bucket-size", type="int", default=100000)

    def run(self, works_dump, editons_dump, bucket_size=100000, **options):
        seq = self.read_dumps(works_dump, editons_dump)
        
        tmpdir = tempfile.mkdtemp(prefix="ol-process-dump-")
        
        docs_dir = os.path.join(tmpdir, "docs")
        sorted_dir = os.path.join(tmpdir, "sorted-docs")
        works_dir = os.path.join(tmpdir, "works")
        
        os.mkdir(docs_dir)
        os.mkdir(sorted_dir)
        os.mkdir(works_dir)
        
        self.log("spitting inputs into %s" % docs_dir)
        self.split(seq, docs_dir, bucket_size)
        
        self.log("sorting into %s" % sorted_dir)
        self.sort_files(docs_dir, sorted_dir)

        self.log("grouping works into %s" % works_dir)
        self.group_works(sorted_dir, works_dir)
        
        self.log("merging the sorted works")
        os.system("cat  %s/* > works.txt" % works_dir)

        if not options.get("no_cleanup"):
            self.log("cleaning up...")
            shutil.rmtree(tmpdir)
        self.log("done")
        
    def log(self, msg):
        print >> sys.stderr, time.asctime(), msg
        
    def sort_files(self, dir, outdir):
        for f in os.listdir(dir):
            infile = os.path.join(dir, f)
            outfile = os.path.join(outdir, f)
            self.log("sort %s" % f)
            os.system("sort -S1G -k1 %s -o %s" % (infile, outfile))
        
    def split(self, seq, dir, bucket_size):
        M = 1024*1024
        files = {}
        
        def get_file(index):
            if index not in files:
                files[index] = open(os.path.join(dir, "%04d.txt" % index), "w", 2*M)
            return files[index]
        
        for key, json in seq:
            try:
                index = int(web.numify(key)) / bucket_size
            except Exception:
                print >> sys.stderr, "bad key %s" % key
                continue
                
            get_file(index).write("%s\t%s\n" % (key, json))
        
        for f in files.values():
            f.close()
            
    def read_dumps(self, works_dump, editons_dump):
        return itertools.chain(
            self.read_works_dump(works_dump),
            self.read_editions_dump(editons_dump))

    def read_works_dump(self, works_dump):
        for tokens in self.read_tokens(works_dump):
            key = tokens[1]
            json = tokens[-1]
            yield key, json
            
    def read_editions_dump(self, editons_dump):
        for tokens in self.read_tokens(editons_dump):
            json = tokens[-1]
            doc = simplejson.loads(json)
            if 'works' in doc:
                yield doc['works'][0]['key'], json
                
    def read_tokens(self, filename):
        self.log("reading %s" % filename)
        M=1024*1024
        for i, line in enumerate(xopen(filename, 'r', 100*M)):
            if i % 1000000 == 0:
                self.log(i)
            yield line.strip().split("\t")
                
    def group_works(self, indir, outdir):
        worker = GroupWorksWorker(indir, outdir)
        
        pool = multiprocessing.Pool(4)
        pool.map(worker, os.listdir(indir))
    
class GenerateSeeds(Command):
    """Processes works.txt and generates seeds.txt.
    
    This command runs a map function over all the docs from works.txt and runs
    a reduce function to generate summary for each seed.
    
    This process involves three steps.
        1. Generate map.txt
        2. Sort map.txt on seed
        3. reduce the map.txt
    """
    def init(self):
        self.re_subject = re.compile("[, _]+")
        
    def run(self, works_txt=None, **options):
        works_file = works_txt and open(works_txt) or sys.stdin
        works = self.read_works(works_file)
        
        f = open("map.txt", "w")
        for work in works:
            for seed, info in self.map(work):
                f.write("%s\t%s\n" % (seed.encode("utf-8"), simplejson.dumps(info)))
                
        self.sort("map.txt", "map_sorted.txt")
        
    def sort(self, filename, outfile):
        os.system("sort -k1 -S1G %s > %s" % (filename, outfile))
    
    def read_works(self, works_file):
        for line in works_file:
            key, json = line.strip().split("\t", 1)
            yield simplejson.loads(json)
            
    def map(self, work):
        """Map function for generating seed info.
        Returns a generator with (seed, seed_info) for each seed of the given work.
        
        Seed_info is of the following format:
        
            {
                "works": [{"key": "/works/..."}],
                "editions": [..],
                "subjects": [..],
                "last_modified": "..."
            }
        """
        authors = self.get_authors(work)
        subjects = self.get_subjects(work)
        editions = list(self.get_editions(work))
        ebooks = [e for e in editions if "ocaid" in e]

        docs = [work] + work.get("editions", [])

        try:
            last_modified = max(doc['last_modified']['value'] for doc in docs if 'last_modified' in doc)
        except ValueError:
            last_modified = ""
            
        xwork = {
            "works": 1,
            "subjects": subjects,
            "editions": len(editions),
            "ebooks": len(ebooks),
            "last_modified": last_modified
        }
        
        yield work['key'], xwork        
        for a in authors:
            yield a['key'], xwork
            
        for e in editions:
            yield e['key'], dict(xwork, editions=1)
        
        for s in subjects:
            yield s['key'], dict(xwork, subjects=[s])
            
    def reduce(self, values):
       pass 

    def get_editions(self, work):
        editions = work.get('editions', [])
        for e in editions:
            doc = {'key': e['key']}
            if 'ocaid' in e:
                doc['ia'] = e['ocaid']
            yield doc

    def get_authors(self, work):
        return [a['author'] for a in work.get('authors', []) if 'author' in a]

    def _get_subject(self, subject, prefix):
        if isinstance(subject, basestring):
            key = prefix + self.re_subject.sub("_", subject.lower()).strip("_")
            return {"key": key, "name": subject}

    def get_subjects(self, work):
        subjects = [self._get_subject(s, "subject:") for s in work.get("subjects", [])]
        places = [self._get_subject(s, "place:") for s in work.get("subject_places", [])]
        people = [self._get_subject(s, "person:") for s in work.get("subject_people", [])]
        times = [self._get_subject(s, "time:") for s in work.get("subject_times", [])]
        return [s for s in subjects + places + people + times if s is not None]
        
class CouchDBImport(Command):
    def run(self, url):
        db = couchdb.Database(url)
        for docs in web.group(self.read(), 1000):
            db.update(docs)
        
    def read(self):
        for line in sys.stdin:
            key, json = line.strip().split("\t")
            doc = simplejson.loads(json)
            doc['_id'] = key
            yield doc
            
def xopen(filename, mode="r", buffering=None):
    if filename.endswith(".gz"):
        import gzip
        return gzip.open(filename, mode, buffering)
    else:
        return open(filename, mode, buffering)

def main(cmd=None, *args):
    commands = {
        "process-dump": ProcessDump(),
        "generate-seeds": GenerateSeeds(),
        "make-editions": MakeEdtions(),
        "couchdb-import": CouchDBImport(),        
    }
    if cmd in commands:
        commands[cmd](args)
    elif cmd is None or cmd == "--help" or cmd == "help":
        print __doc__
        
        print "Available commands:"
        print
        for name in sorted(commands):
            if not name.startswith("_"):
                print "  " + name
        print
    else:
        print >> sys.stderr, "Unknown command %r. see '%s --help'." % (cmd, sys.argv[0])
        
if __name__ == "__main__":
    main(*sys.argv[1:])
    
