"""

@author: zimmer
@date: 2017-01-19
@comment: a first implementation of a crawler of DAMPE data, depending on DAMPE framework.
@todo: implement livetime calculation.

"""
from sys import argv
from ROOT import gSystem, gROOT
from os.path import getsize, abspath
#from tqdm import tqdm
gROOT.SetBatch(True)
gROOT.ProcessLine("gErrorIgnoreLevel = 3002;")
from XRootD import client

infile = argv[1]
if not infile.startswith("root://"):
    infile = abspath(infile)
res = gSystem.Load("libDmpEvent")
if res != 0:
    raise ImportError("could not import libDmpEvent, mission failed.")
from ROOT import TChain, TString, DmpChain, DmpEvent


def main(infile, debug=False):
    DmpChain.SetVerbose(-1)
    DmpEvent.SetVerbosity(-1)
    if debug:
        DmpChain.SetVerbose(1)
        DmpEvent.SetVerbosity(1)
    types = ("mc:simu","mc:reco","2A")

    branches = {
        "mc:simu":['EventHeader', 'DmpSimuStkHitsCollection', 'DmpSimuPsdHits', 'DmpSimuNudHits0Collection',
                   'DmpSimuNudHits1Collection', 'DmpSimuNudHits2Collection', 'DmpSimuNudHits3Collection',
                   'DmpBgoSptStruct', 'DmpSimuBgoHits', 'DmpEvtSimuHeader', 'DmpEvtSimuPrimaries',
                   'DmpTruthTrajectoriesCollection', 'DmpSimuSeondaryVtxCollection', 'DmpEvtOrbit'],
        "mc:reco":['StkKalmanTracks', 'DmpEvtBgoHits', 'DmpSimuBgoHits', 'DmpEvtBgoRec', 'EventHeader',
                   'DmpEvtNudRaw', 'DmpEvtSimuPrimaries', 'StkClusterCollection', 'DmpStkLadderAdcCollection',
                   'DmpStkEventMetadata', 'DmpPsdHits', 'DmpSimuPsdHits', 'DmpEvtPsdRec', 'DmpGlobTracks',
                   'DmpEvtOrbit', 'DmpEvtSimuHeader', 'DmpTruthTrajectoriesCollection'],
        "2A":['EventHeader', 'DmpEvtPsdRaw', 'DmpPsdHits', 'DmpEvtBgoRaw', 'DmpEvtBgoHits', 'StkClusterCollection',
              'DmpStkLadderAdcCollection', 'DmpStkEventMetadata', 'StkKalmanTracks', 'DmpEvtNudRaw', 'EvtAttitudeContainer',
              'DmpEvtBgoRec', 'DmpEvtPsdRec', 'DmpGlobTracks']
    }

    # fixme: this wraps the null pointer testing.

    #def md5sum(fname):
    #    from subprocess import Popen, PIPE
    #    cmd = "md5sum {fname}".

    def checkBranches(tree, branches):
        if debug: print 'checking branches.'
        for b in branches:
            res = tree.FindBranch(b)
            if res is None:
                raise Exception("missing branch %s",b)
        return True

    def testPdgId(fname):
        if debug: print 'testing for PDG id'
        from os.path import basename
        bn = basename(fname).split(".")[0].split("-")[0]
        if (not bn.startswith("all")) or (("bkg" or "background" or "back") in bn.lower()):
            return True
        else:
            try:
                from ROOT import DmpEvtSimuPrimaries
                tree = mcprimaries = None
                tree = TChain("CollectionTree")
                tree.Add(fname)
                tree.SetBranchStatus("DmpEvtSimuPrimaries",1)
                branch = tree.GetBranch("DmpEvtSimuPrimaries")
                mcprimaries = DmpEvtSimuPrimaries()
                tree.SetBranchAddress("DmpEvtSimuPrimaries", mcprimaries)
                branch.GetEntry(0)
                tree.GetEntry(0)
                entry = tree.GetEntry(0)
                pdg_id = int(mcprimaries.pvpart_pdg)
                if pdg_id > 10000:
                    pdg_id = int(pdg_id/10000.) - 100000
                pdgs = dict(Proton=2212, Electron=11, Muon=13, Gamma=22,He = 2, Li = 3, Be = 4, B = 5, C = 6, N = 7, O = 8)
                particle = bn.replace("all","")
                #print particle
                assert particle in pdgs.keys(), "particle type not supported"
                if pdgs[particle] != pdg_id:
                    raise Exception("wrong PDG ID! particle_found=%i particle_expected=%i",pdgs[particle],pdg_id)
            except Exception as err:
                del tree, mcprimaries
                raise Exception(str(err))
            return True

    def isNull(ptr):
        if debug: print 'test if pointer is null.'
        try:
            heap = ptr.IsOnHeap()
        except ReferenceError:
            return True
        else:
            return False

    def getTime(evt):
        if debug: print 'extract timestamp'
        if isNull(evt.pEvtHeader()):
            return -1.
        sec = evt.pEvtHeader().GetSecond()
        ms  = evt.pEvtHeader().GetMillisecond()
        time = float("{second}.{ms}".format(second=sec,ms=ms))
        return time

    def checkHKD(fname):
        if debug: print 'check HKD trees'
        trees = dict( SatStatus = ['DmpHKDSatStatus'],
                         HighVoltage=['DmpHKDHighVoltage'],
                         TempSatellite=['DmpHKDTempSatellite'],
                         TempPayloadNegative=['DmpHKDTempNegative'],
                         TempPayloadPositive=['DmpHKDTempPositive'],
                         CurrentPayloadNegative=['DmpHKDCurrentNegative'],
                         CurrentPayloadPositive=['DmpHKDCurrentPositive'],
                         StatusPayloadNegative=['DmpHKDStatusNegative'],
                         StatusPayloadPositive=['DmpHKDStatusPositive'],
                         StatusPowerSupplyPositive=['DmpHKDStatusPowerSupplyPositive'],
                         StatusPowerSupplyNegative=['DmpHKDStatusPowerSupplyNegative'],
                         PayloadDataProcesser=['DmpHKDPayloadDataProcessor'],
                         PayloadManager=['DmpHKDPayloadManager'])
        try:
            for tree, branches in trees.iteritems():
                ch = TChain("HousekeepingData/{tree}".format(tree=tree))
                ch.Add(fname)
                if ch.GetEntries() == 0: raise Exception("HKD tree %s empty",tree)
                checkBranches(ch, branches)
        except Exception as err:
            raise Exception(err.message)
        return True

    def extractVersion(fname):
        if debug: print 'extract version'
        ch = TChain("RunMetadataTree")
        ch.Add(fname)
        ch.SetBranchStatus("*",1)
        svn_rev = TString()
        tag = TString()
        ch.SetBranchAddress("SvnRev",svn_rev)
        ch.SetBranchAddress("tag",tag)
        ch.GetEntry(0)
        return tag, svn_rev

    def isFlight(fname):
        if debug: print 'check if data is flight data'
        ch = DmpChain("CollectionTree")
        ch.Add(infile)
        nevts = int(ch.GetEntries())
        if not nevts: raise Exception("zero events")
        evt = ch.GetDmpEvent(0)
        tstart = getTime(evt)
        #for i in tqdm(xrange(nevts)):
        #    evt = ch.GetDmpEvent(i)
        #    if i == 0:
        evt = ch.GetDmpEvent(nevts-1)
        tstop = getTime(evt)
        flight_data = True if ch.GetDataType() == DmpChain.kFlight else False
        del ch
        del evt
        return flight_data, dict(tstart=tstart, tstop=tstop)

    def getSize(lfn):
        if debug: 'print extracting file size'
        if lfn.startswith("root://"):
            server = "root://{server}".format(server=lfn.split("/")[2])
            xc = client.FileSystem(server)
            is_ok, res = xc.stat(lfn.replace(server,""))
            if not is_ok.ok: raise Exception(is_ok.message)
            return res.size
        else:
            return getsize(lfn)


    tstart = -1.
    tstop = -1.
    fsize = 0.
    good = True
    comment = "NONE"
    f_type = "Other"
    svn_rev = "None"
    tag = "None"
    try:
        fsize = getSize(infile)
        tag, svn_rev = extractVersion(infile)
        tch = TChain("CollectionTree")
        tch.Add(infile)
        nevts = int(tch.GetEntries())
        if nevts == 0: raise IOError("zero events.")
        flight_data, stat = isFlight(infile)
        if flight_data:
            good = checkHKD(infile)
            tstart = stat.get("tstart",-1.)
            tstop  = stat.get("tstop",-1.)
            f_type = "2A"
        else:
            #print 'mc data'
            simu_branches = [tch.FindBranch(b) for b in branches['mc:simu']]
            reco_branches = [tch.FindBranch(b) for b in branches['mc:reco']]

            if None in simu_branches:
                f_type = "mc:reco"
                if None in reco_branches: raise Exception("missing branches in mc:reco")
            else:
                f_type = "mc:simu"
            if(testPdgId(infile)): good = True
        if good:
            assert f_type in types, "found non-supported dataset type!"
            good = checkBranches(tch, branches[f_type])

    except Exception as err:
        comment = str(err.message)
        good = False

    f_out = dict(lfn=infile, nevts=nevts, tstart=tstart, tstop=tstop, good=good,
                 comment=comment, size=fsize, type=f_type, version=tag, SvnRev=svn_rev)
    return f_out

if __name__ == '__main__':

    from optparse import OptionParser
    parser = OptionParser()
    usage = "Usage: %prog [options]"
    description = "extract metadata from root files."
    parser.set_usage(usage)
    parser.set_description(description)
    parser.add_option("--debug",dest="debug",action="store_true",default=False, help="run in debug mode")
    (opts, arguments) = parser.parse_args()
    out = main(argv[1], opts.debug)
    print out