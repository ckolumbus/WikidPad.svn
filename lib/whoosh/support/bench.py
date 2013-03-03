#===============================================================================
# Copyright 2010 Matt Chaput
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#===============================================================================

from __future__ import division
import os.path, random, sys
from optparse import OptionParser
from shutil import rmtree
from zlib import compress, decompress

from whoosh import index, qparser, query
from whoosh.util import now

try:
    import xappy
except ImportError:
    pass
try:
    import xapian
except ImportError:
    pass
try:
    import pysolr
except ImportError:
    pass

try:
    from persistent import Persistent
    class ZDoc(Persistent):
        def __init__(self, d):
            self.__dict__.update(d)
except ImportError:
    pass


class Module(object):
    def __init__(self, bench, options, args):
        self.bench = bench
        self.options = options
        self.args = args
    
    def __repr__(self):
        return self.__class__.__name__
    
    def indexer(self):
        pass
    
    def index_document(self, d):
        raise NotImplementedError
    
    def finish(self):
        pass
    
    def searcher(self):
        pass
    
    def query(self):
        raise NotImplementedError
    
    def find(self, q):
        raise NotImplementedError
    
    def findterms(self, terms):
        raise NotImplementedError
    
    def results(self, r):
        return r


class Spec(object):
    headline_field = "title"
    main_field = "body"
    whoosh_compress_main = False
    
    def __init__(self, options, args):
        self.options = options
        self.args = args
        
    def documents(self):
        raise NotImplementedError
    
    def setup(self):
        pass
    
    def print_results(self, ls):
        showbody = self.options.showbody
        limit = self.options.limit
        for i, hit in enumerate(ls):
            if i >= limit:
                break
            
            print "%d. %s" % (i+1, hit.get(self.headline_field))
            if showbody:
                print hit.get(self.main_field)
            
class WhooshModule(Module):
    def indexer(self):
        schema = self.bench.spec.whoosh_schema()
        path = os.path.join(self.options.dir, "%s_whoosh" % self.options.indexname)
        if not os.path.exists(path):
            os.mkdir(path)
        ix = index.create_in(path, schema)
        self.writer = ix.writer(procs=int(self.options.procs),
                                limitmb=int(self.options.limitmb))

    def index_document(self, d):
        if hasattr(self.bench, "process_document_whoosh"):
            self.bench.process_document_whoosh(d)
        if self.bench.spec.whoosh_compress_main:
            mf = self.bench.spec.main_field
            d["_stored_%s" % mf] = compress(d[mf], 9)
        self.writer.add_document(**d)

    def finish(self):
        self.writer.commit()
        
    def searcher(self):
        path = os.path.join(self.options.dir, "%s_whoosh" % self.options.indexname)
        ix = index.open_dir(path)
        self.srch = ix.searcher()
        self.parser = qparser.QueryParser(self.bench.spec.main_field, schema=ix.schema)
        
    def query(self):
        qstring = " ".join(self.args).decode("utf8")
        return self.parser.parse(qstring)
    
    def find(self, q):
        return self.srch.search(q, limit=int(self.options.limit))
    
    def results(self, r):
        mf = self.bench.spec.main_field
        for hit in r:
            fs = hit.fields()
            if self.bench.spec.whoosh_compress_main:
                fs[mf] = decompress(fs[mf])
            yield fs
    
    def findterms(self, terms):
        limit = int(self.options.limit)
        s = self.srch
        q = query.Term(self.main_field, None)
        for term in terms:
            q.text = term
            yield s.search(q, limit=limit)
    

class XappyModule(Module):
    def indexer(self):
        path = os.path.join(self.options.dir, "%s_xappy" % self.options.indexname)
        conn = self.bench.spec.xappy_connection(path)
        return conn
    
    def index_document(self, conn, d):
        if hasattr(self.bench, "process_document_xappy"):
            self.bench.process_document_xappy(d)
        doc = xappy.UnprocessedDocument()
        for key, values in d:
            if not isinstance(values, list):
                values = [values]
            for value in values:
                doc.fields.append(xappy.Field(key, value))
        conn.add(doc)

    def finish(self, conn):
        conn.flush()
        
    def searcher(self):
        path = os.path.join(self.options.dir, "%s_xappy" % self.options.indexname)
        return xappy.SearchConnection(path)
        
    def query(self, conn):
        return conn.query_parse(" ".join(self.args))
    
    def find(self, conn, q):
        return conn.search(q, 0, int(self.options.limit))
    
    def findterms(self, conn, terms):
        limit = int(self.options.limit)
        for term in terms:
            q = conn.query_field(self.main_field, term)
            yield conn.search(q, 0, limit)
    
    def results(self, r):
        hf = self.bench.spec.headline_field
        mf = self.bench.spec.main_field
        for hit in r:
            yield {hf: hit.data[hf], mf: hit.data[mf]}
        

class XapianModule(Module):
    def indexer(self):
        path = os.path.join(self.options.dir, "%s_xapian" % self.options.indexname)
        self.database = xapian.WritableDatabase(path, xapian.DB_CREATE_OR_OPEN)
        self.ixer = xapian.TermGenerator()
        
    def index_document(self, d):
        if hasattr(self.bench, "process_document_xapian"):
            self.bench.process_document_xapian(d)
        doc = xapian.Document()
        doc.add_value(0, d.get(self.bench.spec.headline_field, "-"))
        doc.set_data(d[self.main_field])
        self.ixer.set_document(doc)
        self.ixer.index_text(d[self.main_field])
        self.database.add_document(doc)
        
    def finish(self):
        self.database.flush()
        
    def searcher(self):
        path = os.path.join(self.options.dir, "%s_xappy" % self.options.indexname)
        self.db = xapian.Database(path)
        self.enq = xapian.Enquire(self.db)
        self.qp = xapian.QueryParser()
        self.qp.set_database(self.db)
        
    def query(self):
        return self.qp.parse_query(" ".join(self.args))
    
    def find(self, q):
        self.enq.set_query(q)
        return self.enq.get_mset(0, int(self.options.limit))
    
    def findterms(self, terms):
        limit = int(self.options.limit)
        for term in terms:
            q = self.qp.parse_query(term)
            self.enq.set_query(q)
            yield self.enq.get_mset(0, limit)
    
    def results(self, matches):
        hf = self.bench.spec.headline_field
        mf = self.bench.spec.main_field
        for m in matches:
            yield {hf: m.document.get_value(0), mf: m.document.get_data()}


class SolrModule(Module):
    def indexer(self):
        self.solr_doclist = []
        self.conn = pysolr.Solr(self.options.url)
        self.conn.delete("*:*")
        self.conn.commit()
    
    def index_document(self, d):
        self.solr_doclist.append(d)
        if len(self.solr_doclist) >= int(self.options.batch):
            self.conn.add(self.solr_doclist, commit=False)
            self.solr_doclist = []
        
    def finish(self):
        if self.solr_doclist:
            self.conn.add(self.solr_doclist)
        del self.solr_doclist
        self.conn.optimize(block=True)
        
    def searcher(self):
        self.solr = pysolr.Solr(self.options.url)
    
    def query(self):
        return " ".join(self.args)
    
    def find(self, q):
        return self.solr.search(q, limit=int(self.options.limit))
    
    def findterms(self, terms):
        limit = int(self.options.limit)
        for term in terms:
            yield self.solr.search("body:" + term, limit=limit)
    

class ZcatalogModule(Module):
    def indexer(self):
        from ZODB.FileStorage import FileStorage
        from ZODB.DB import DB
        from zcatalog import catalog
        from zcatalog import indexes
        import transaction
        
        dir = os.path.join(self.options.dir, "%s_zcatalog" % self.options.indexname)
        if os.path.exists(dir):
            rmtree(dir)
        os.mkdir(dir)
        
        storage = FileStorage(os.path.join(dir, "index"))
        db = DB(storage)
        conn = db.open()
        
        self.cat = catalog.Catalog()
        self.bench.spec.zcatalog_setup(self.cat)
        conn.root()["cat"] = self.cat
        transaction.commit()
        
        self.zcatalog_count = 0
    
    def index_document(self, d):
        if hasattr(self.bench, "process_document_zcatalog"):
            self.bench.process_document_zcatalog(d)
        doc = ZDoc(d)
        self.cat.index_doc(doc)
        self.zcatalog_count += 1
        if self.zcatalog_count >= 100:
            import transaction
            transaction.commit()
            self.zcatalog_count = 0
        
    def finish(self):
        import transaction
        transaction.commit()
        del self.zcatalog_count
        
    def searcher(self):
        from ZODB.FileStorage import FileStorage
        from ZODB.DB import DB
        from zcatalog import catalog
        from zcatalog import indexes
        import transaction
        
        path = os.path.join(self.options.dir, "%s_zcatalog" % self.options.indexname, "index")
        storage = FileStorage(path)
        db = DB(storage)
        conn = db.open()
        
        self.cat = conn.root()["cat"]
    
    def query(self):
        return " ".join(self.args)
    
    def find(self, q):
        return self.cat.searchResults(body=q)
    
    def findterms(self, terms):
        for term in terms:
            yield self.cat.searchResults(body=term)
    
    def results(self, r):
        hf = self.bench.spec.headline_field
        mf = self.bench.spec.main_field
        for hit in r:
            # Have to access the attributes for them to be retrieved
            yield {hf: getattr(hit, hf), mf: getattr(hit, mf)}


class Bench(object):
    libs = {"whoosh": WhooshModule, "xappy": XappyModule,
            "xapian": XapianModule, "solr": SolrModule,
            "zcatalog": ZcatalogModule}
    
    def index(self, lib):
        print "Indexing with %s..." % lib
        
        options = self.options
        chunk = int(options.chunk)
        skip = int(options.skip)
        upto = int(options.upto)
        count = 0
        skipc = skip
        
        starttime = chunkstarttime = now()
        lib.indexer()
        for d in self.spec.documents():
            skipc -= 1
            if not skipc:
                lib.index_document(d)
                count += 1
                skipc = skip
                if chunk and not count % chunk:
                    t = now()
                    sofar = t - starttime
                    print "Done %d docs, %0.3f secs for %d, %0.3f total, %0.3f docs/s" % (count, t - chunkstarttime, chunk, sofar, count/sofar)
                    chunkstarttime = t
                if count > upto:
                    break
        
        spooltime = now()
        print "Spool time:", spooltime - starttime
        lib.finish()
        committime = now()
        print "Commit time:", committime - spooltime
        print "Total time to index", count, "documents:",  committime - starttime
    
    def search(self, lib):
        lib.searcher()
        
        t = now()
        q = lib.query()
        print "Query:", q
        r = lib.find(q)
        print "Search time:", now() - t
        
        t = now()
        self.spec.print_results(lib.results(r))
        print "Print time:", now() - t
    
    def search_file(self, lib):
        f = open(self.options.termfile, "rb")
        terms = [line.strip() for line in f]
        f.close()
        
        print "Searching %d terms with %s" % (len(terms), lib)
        lib.searcher()
        starttime = now()
        for r in lib.findterms(terms):
            pass
        searchtime = now() - starttime
        print "Search time:", searchtime, "searches/s:", float(len(terms))/searchtime
    
    def _parser(self, name):
        p = OptionParser()
        p.add_option("-x", "--lib", dest="lib",
                     help="Name of the library to use to index/search.",
                     default="whoosh")
        p.add_option("-d", "--dir", dest="dir", metavar="DIRNAME",
                     help="Directory in which to store index.", default=".")
        p.add_option("-s", "--setup", dest="setup", action="store_true",
                     help="Set up any support files or caches.", default=False)
        p.add_option("-i", "--index", dest="index", action="store_true",
                     help="Index the documents.", default=False)
        p.add_option("-n", "--name", dest="indexname", metavar="PREFIX",
                     help="Index name prefix.", default="%s_index" % name)
        p.add_option("-U", "--url", dest="url", metavar="URL",
                     help="Solr URL", default="http://localhost:8983/solr")
        p.add_option("-m", "--mb", dest="limitmb",
                     help="Max. memory usage, in MB", default="128")
        p.add_option("-c", "--chunk", dest="chunk",
                     help="Number of documents to index between progress messages.",
                     default=1000)
        p.add_option("-B", "--batch", dest="batch",
                     help="Batch size for batch adding documents.",
                     default=100)
        p.add_option("-k", "--skip", dest="skip", metavar="N",
                     help="Index every Nth document.", default=1)
        p.add_option("-u", "--upto", dest="upto", metavar="N",
                     help="Index up to this document number.", default=600000)
        p.add_option("-p", "--procs", dest="procs", metavar="NUMBER",
                     help="Number of processors to use.", default=1)
        p.add_option("-l", "--limit", dest="limit", metavar="N",
                     help="Maximum number of search results to retrieve.",
                     default=10)
        p.add_option("-b", "--body", dest="showbody", action="store_true",
                     help="Show the body text in search results.",
                     default=False)
        p.add_option("-g", "--gen", dest="generate", metavar="N",
                     help="Generate a list at most N terms present in all libraries.",
                     default=None)
        p.add_option("-f", "--file", dest="termfile", metavar="FILENAME",
                     help="Search using the list of terms in this file.",
                     default=None)
        
        return p
    
    def run(self, specclass):
        parser = self._parser(specclass.name)
        options, args = parser.parse_args()
        self.options = options
        self.args = args
        
        if options.lib not in self.libs:
            raise Exception("Unknown library: %r" % options.lib)
        lib = self.libs[options.lib](self, options, args)
        
        self.spec = specclass(options, args)
        
        if options.setup:
            self.spec.setup()
        
        action = self.search
        if options.index:
            action = self.index
        if options.termfile:
            action = self.search_file
        if options.generate:
            action = self.generate_search_file
        
        action(lib)
        











