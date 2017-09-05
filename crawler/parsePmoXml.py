from argparse import ArgumentParser
from glob import glob
from collections import OrderedDict
from xmltodict import parse
from ast import literal_eval
from datetime import datetime
try:
    from pymongo import MongoClient
except ImportError:
    HASMONGO = False

class file_meta(object):
    """ file size is always in MB, GTI intervals are in ms"""
    BasicAttribute = {}
    Time = {}
    Calibrations = {}
    md5 = None
    dtype = "2A"

    def __init__(self,d,dtype="2A"):
        self.dtype = dtype
        self.__unpack__(d)


    def __unpack__(self,vd):
        """ unpacks and fills the relevant keys"""
        self.BasicAttribute = self.parseBasicAtts(vd.get("BasicAttribute",{}))
        self.Time           = self.parseTime(vd.get("Time",{}))
        if self.dtype == "2A":
            self.Calibrations   = self.parseAOB(vd.get("AOB",{}))

    def parseDict(self,val):
        if isinstance(val,dict):
            for key, value in val.iteritems():
                if isinstance(value,OrderedDict):
                    if "#text" in value:
                        val[key] = float(value.get("#text",0.))
        return val

    def parseBasicAtts(self,val):
        """ parse BasicAttribute """
        p = self.parseDict(val)
        for key, value in p.iteritems():
            if key == 'Parent':
                p[key] = value.get("FileName","None")
        return p

    def parseTime(self,val):
        """ parse Time """
        return self.parseDict(val)

    def parseAOB(self,val):
        """ parse AOB, contains calibration data """
        p = literal_eval(self.parseDict(val))
        md5 = "None"
        if "md5" in p: md5 = p.pop("md5")
        p['md5'] = md5
        calib = p.get("Calibration",{})
        if 'STK' in calib:
            stk = calib.get("STK",{})
            for key, value in stk.iteritems():
                if "TimeStamp" in key:
                    stk[key] = int(value)
            calib['STK'] = stk
        return calib


    def export2DB(self):
        """ will build a dict ready for ingest """
        p = self.BasicAttribute
        p.update(self.Time)
        p['Calibrations']=self.Calibrations
        for key, value in p.iteritems():
            if "Time" in key:
                try:
                    dt = datetime.strptime(value,'%Y%m%d%H%M%S')
                    p[key] = dt
                except ValueError:
                    p[key] = float(value)
                except Exception: pass
        return p

def readOne(fname,dtype="2A"):
    f = open(fname, 'r')
    replace_chars = [" ", "\t", "\n"]
    doc = parse(f.read()).get("MetaDataFile", {})

    for key, value in doc.iteritems():
        for ch in replace_chars:
            while ch in value:
                value = value.replace(ch, "")
        if "}\"" in value:
            value = value.replace("}\"", "},\"")
        elif "{" in value:
            value = literal_eval(value)
        if isinstance(value, OrderedDict):
            value = dict(value)
        doc[key] = value
    f.close()
    meta = file_meta(doc,dtype=dtype)
    return meta.export2DB()

def insertDocuments(mongopath,docs, debug=False,file_type="2A"):
    assert HASMONGO, "pymongo not found, DB mode disabled"
    if debug: print 'establishing db connection'
    cl = MongoClient(mongopath)
    if debug: print cl
    db = client.FlightData
    coll = literal_eval("db.%s"%file_type)
    objs_to_insert = []
    if debug: print '# objects to insert',len(docs)
    if debug: print 'checking if docs already exist in db'
    for doc in docs:
        md5 = doc['md5']
        fn = doc["FileName"]
        query = coll.find({'md5':md5,'FileName':fn}).count()
        if not query:
            objs_to_insert.append(doc)
    if len(objs_to_insert):
        result = coll.insert_many(objs_to_insert)
        if debug: print 'inserted #docs:',len(result)
    cl.close()

def main(args=None):
    usage = "Usage: %(prog)s [options]"
    description = "ingest one or multiple xml files into MongoDB"
    parser = ArgumentParser(usage=usage, description=description)
    parser.add_argument("--dtype",dest="dtype",type=str,default="2A",choices=["2A","1F"],help="data type")
    parser.add_argument("--input","-i",dest='input',type=str,default=None,help="input file (or multiple, use asterisk)")
    parser.add_argument("--conn","-c",dest="connection_string",type=str,default=None,help="MongoDB connection string")
    parser.add_argument("--debug","-d",dest="debug",action='store_true',default=False, help="run with debugging enabled")
    opts = parser.parse_args(args)
    mp = opts.connection_string
    files_to_process = []
    inf = [opts.input]
    if "*" in inf[0]:
        inf = glob(inf)
    for f in inf:
        if not f.endswith(".xml"):
            fi = open(f,"r").readlines()
            files_to_process+=[fin.replace("\n","") for fin in fi]
        else:
            files_to_process.append(f)
    docs = []
    for fi in files_to_process:
        docs.append(readOne(fi,dtype=opts.dtype))
    if opts.debug:
        print docs
    insertDocuments(mp,docs,debug=opts.debug,file_type=opts.dtype)

if __name__ == '__main__':
    main()
