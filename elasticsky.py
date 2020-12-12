#!/usr/bin/env python

import pandas as pd

##
## ADES reading/writing
##

def read_psv_ades(fn):
    """Read PSV ADES file
    
    Args:
        fn (str): Filename
        
    Returns:
        tuple: loaded dataframe, header
    """
    header = []
    with open(fn) as fp:
        # consume and store the header
        while True:
            line = fp.readline()
            if line[0] in ['#', '!']:
                header.append(line.rstrip())
                continue
            # the line is the header
            names = [ s.strip() for s in line.split('|') ]
            break
        df = pd.read_csv(fp, sep='|', header=0, names=names)
    return df, header

def write_psv_ades(fn, df, header):
    """Write PSV ADES file
    
    Args:
        fn (str): Output filename
        df (pd.DataFrame): Dataframe of observations
        header (list): ADES file header (list of lines)
        
    """
    with open(fn, "w") as fp:
        fp.write('\n'.join(header))
        fp.write('\n')
        df.to_csv(fp, sep='|', index=False)


##
## Multiprocess-safe FindOrb Wrappers
##

def fit_orbits(obsvs, hdr, trkSubs=None):
    """Fit a batch of tracklets with FindOrb in a multi-processing safe manner.

    These are all still processed within a single thread (process).

    Args:
        df (pd.DataFrame): The observations to fit
        hdr (str): ADES file header for the observations in `df`
        tracks (list): A list of trkSubs to fit; if None, process all from `df`
        
    Returns:
        dict: A dictionary of (trkSub: result), where result is a list of
              items of the form::
            {
                'name': track name,
                'state_vec': state vector
                'epoch': state vector epoch
                'covar': covariance matrix
                'findorb': { # run details, useful for debugging
                    'args': how findorb was invoked
                    'returncode': UNIX return code (zero for success)
                    'stdout': the contents of Find_Orb standard output
                    'stderr': the contents of Find_Orb standard error
                }
            }
    """
    import tempfile, subprocess, json, os

    if trkSubs is None:
        trkSubs = obsvs['trkSub'].unique()

    results = []
    # create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:

        # prep the new "home" directory
        from shutil import copytree, ignore_patterns
        copytree(
            os.path.expanduser("~/.find_orb"), f"{tmpdir}/.find_orb",
            ignore=ignore_patterns('debug.txt', 'elements.json', 'elem_short.json', 'linux_p1550p2650.430t')
        )
        os.symlink(os.path.expanduser("~/.find_orb/linux_p1550p2650.430t"), f"{tmpdir}/.find_orb/linux_p1550p2650.430t")

        # Fit tracklet by tracklet
        for trkSub in trkSubs:
            print(f"[{gethip()[1]}:{tmpdir}] {trkSub}")

            # select only the current tracklet
            df = obsvs[obsvs["trkSub"] == trkSub]
        
            # dump to ades
            datafile = f"{tmpdir}/data.psv"
            resultdir = f"{tmpdir}/result"
            write_psv_ades(datafile, df, hdr)

            # call findorb
            cmd = f"fo {datafile} -O {resultdir} -D environ.dat"
            env = os.environ.copy()
            env["HOME"] = tmpdir
            ret = subprocess.run(cmd, shell=True, env=env, check=False, capture_output=True)

            # fetch/construct the result
            if ret.returncode == 0:
                # read the result
                try:
                    with open(f"{resultdir}/covar.json") as fp:
                        result = json.load(fp)
                except:
                    result = {}
            else:
                result = {}

            result["name"] = trkSub
            result["findorb"] = {
                'args': ret.args,
                'returncode': ret.returncode,
                'stdout': ret.stdout.decode('utf-8'),
                'stderr': ret.stderr.decode('utf-8')
            }

            results.append(result)

    return results

##
## Utilities
##

# A utility to divide up the tracklets into smaller chunks
def chunk(k, chunk_size):
     return[ k[i:i + chunk_size] for i in range(0, len(k), chunk_size) ]

def to_fwf(fn, df):
    from tabulate import tabulate
    content = tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".12f")
    with open(fn, "w") as fp:
        fp.write(content)
        fp.write("\n")

# Function to display hostname and
# IP address
def gethip():
    import socket
    try:
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)
        return (host_name, host_ip)
    except:
        return (None, None)

##
## Ray support
##

import ray

@ray.remote
def dist_fit_orbits(df, hdr, tracks):
    return fit_orbits(df, hdr, tracks)

##
## Functions for command-line testing; should be refactored to its own module
##

def processAdesFile(fn, chunk_size=10, ntracklets=None):
    # load the file
    df, hdr = read_psv_ades(fn)
    del df["rmsMag"] # workaround for FindOrb bug

    # subdivide it into smaller chunks, with N tracklets each. These
    # chunks will be submitted to individual FindOrb threads to work on.
    tracks = chunk(df['trkSub'].unique()[:ntracklets], chunk_size)

    # launch the parallel processing, and wait for the result
    df_id = ray.put(df)
    futures = [
        dist_fit_orbits.remote(df_id, hdr, track_batch)
        for track_batch in tracks
    ]
    chunked_results = ray.get(futures)
    del df_id

    # merge the result chunks
    results = [result for chunk in chunked_results for result in chunk]

    return results

def processAdesFile_single(fn, ntracklets=None):
    # load the file
    df, hdr = read_psv_ades(fn)
    del df["rmsMag"] # workaround for FindOrb bug

    tracks = df["trkSub"].unique()[:ntracklets]
    results = fit_orbits(df, hdr, tracks)

    return results

def cmdline_test():
    if False:
        orbits = processAdesFile_single("input.psv", ntracklets=5)
    else:
        ray.init(address='auto')

        # grab this file from https://epyc.astro.washington.edu/~moeyensj/rubin_submissions/ver5/
        orbits = processAdesFile("input.psv", ntracklets=10000)

    # basic info
    print(f"Number of results: {len(orbits)}")

    # check for failures
    failures = [ result for result in orbits if result['findorb']['returncode'] != 0]
    print(f"Number of failures: {len(failures)}")
    if len(failures):
        import json
        with open("failures.log", "w") as fp:
            json.dump(failures, fp)

    # construct dataframe of states and write it out
    states = [ result['state_vect']        for result in orbits if result['findorb']['returncode'] == 0 ]
    epochs = [ result["epoch"] - 2400000.5 for result in orbits if result['findorb']['returncode'] == 0 ]
    keys   = [ result['name']              for result in orbits if result['findorb']['returncode'] == 0 ]
    states = pd.DataFrame(states, index=keys, columns=["x", "y", "z", "vx", "vy", "vz"])
    states.reset_index(inplace=True)
    states = states.rename(columns = {'index':'trkSub'})
    states["epoch"] = epochs
    states.sort_index()
    to_fwf("result.txt", states)
    print(f"Fitted state vectors are in result.txt")

    print(f"Shutting down...")


##
## Flask app. Should be refactored to its own module.
##
import datetime

class FitRunner:
    def __init__(self, fn):
        df, hdr = read_psv_ades(fn)
        del df["rmsMag"] # workaround for FindOrb bug

        self.df, self.hdr = df, hdr
        self.total = len(self.df)
        self.result = []
        
        self.tend = None

    def stats(self):
        # return the time this batch took to execute, and
        # the ETA if it's still running

        if self.tend is None:
            now = datetime.datetime.now()
            if len(self.tasks) == 0:
                self.tend = now
        else:
            now = self.tend

        dt = now - self.tstart

        if self.result:
            return dt.seconds, (self.total / len(self.result) - 1) * dt.seconds;
        else:
            return dt.seconds, "unknown"

    def start(self, chunk_size=10, ntracklets=None):
        self.tstart = datetime.datetime.now()
    
        if ntracklets is None:
            ntracklets = len(self.df['trkSub'].unique())

        # subdivide the data into smaller chunks, with N tracklets each. These
        # will be submitted to individual FindOrb threads to work on.
        tracks = chunk(self.df['trkSub'].unique()[:ntracklets], chunk_size)

        # launch the parallel processing
        df_id = ray.put(self.df)
        self.tasks = [
            dist_fit_orbits.remote(df_id, self.hdr, track_batch) for track_batch in tracks
        ]
        self.result = []
        self.total = min(len(self.df), ntracklets)

    def collect(self, num_returns=None, timeout=0):
        if num_returns == None:
            num_returns = len(self.tasks)

        # collect the results that have finished
        done, tasks = ray.wait(self.tasks, num_returns=num_returns, timeout=timeout)
        
        chunked_results = ray.get(done)
        results = [result for chunk in chunked_results for result in chunk]
        
        self.result += results
        self.tasks = tasks

        return len(results)

from flask import Flask, request, redirect
from flask_restful import Resource, Api, reqparse, abort
import werkzeug
import os

app = Flask(__name__, static_folder=f'{os.getcwd()}/tv', static_url_path='/timeline')
api = Api(app)

# FIXME: this method of storing state won't work in production (in a
# multiprocessing setting).  I'm not clear what happens with ray in such
# case, as well.  It's probably best to shift all of this to ray.serve
# https://docs.ray.io/en/master/serve/ to get things to work nicely.

batches = {}

import ray
ray.init(address='auto')
#ray.init()

class FitRun(Resource):
    #
    # The resource representing a the orbit fitter service.
    #
    def get(self):
        #
        # Return a list of fits we know of, either in progress or done.
        #
        return list(batches.keys())

    def post(self):
        #
        # Initiate a new fit. If the file and request correspond to something we've already run,
        # do not initiate a new run.
        #
        parser = reqparse.RequestParser()
        parser.add_argument('ades', type=werkzeug.datastructures.FileStorage, location='files', help='PSV-serialized ADES file')
        parser.add_argument('ntracklets', type=int, help="Number of tracklets to process")
        args = parser.parse_args()

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            fn = f"{tmpdir}/input.psv"
            args['ades'].save(fn)
            ntracklets=args["ntracklets"]

            # generate the ID, as hash of the file
            import hashlib
            content = open(fn).read() + f"\nntracklets={ntracklets}"
            id = hashlib.md5(content.encode("utf-8")).hexdigest()

            # start a new fit, if it's not already in batches
            if id not in batches:
                runner = FitRunner(fn)
                runner.start(ntracklets=ntracklets)

                batches[id] = runner

                return { 'id': id }, 201
            else:
                return { 'id': id }, 200

        # We're not supposed to get here
        assert(False)

class FitStatus(Resource):
    #
    # The resource representing the status of a fit
    #
    def get(self, id):
        runner = batches[id]
        runner.collect()

        done = len(runner.result)
        running = runner.total - done
        runtime, eta = runner.stats()

        return {
            'ncores': ray.cluster_resources()['CPU'],
            'trk_done': done,
            'trk_running': running,
            'started': str(runner.tstart),
            'runtime_seconds': runtime,
            'eta_seconds': eta
        }

class FitResult(Resource):
    #
    # The resource representing the result of a fit. It
    # could be a partial result.
    #
    def get(self, id):
        runner = batches[id]
        runner.collect()
        return runner.result


class TimelineResource(Resource):
    def get(self):
        traceJson = ray.timeline()
        return traceJson

api.add_resource(FitRun, '/fit')
api.add_resource(FitResult, '/fit/result/<id>')
api.add_resource(FitStatus, '/fit/status/<id>')
api.add_resource(TimelineResource, '/timeline-json')

@app.route('/timeline')
@app.route('/timeline/')
def hello():
    return redirect("/timeline/index.html", code=302)

if __name__ == "__main__":
    import os
    print(f"CWD={os.getcwd()}")
   # cmdline_test()
    app.run(debug=True)
