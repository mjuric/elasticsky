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

##    from timeit import default_timer as timer
##    start = timer()

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

            with timing() as orbfit_timer:
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
                'runtime': orbfit_timer.t,
                'stdout': ret.stdout.decode('utf-8'),
                'stderr': ret.stderr.decode('utf-8')
            }

            results.append(result)

##    dt = timer() - start
##    results.append({ 'total': dt })

    return results

##
## Utilities
##

# A context manager for measuring the time it takes to run
# a block of statements.
class timing:
    t = None
    def __enter__(self):
        from timeit import default_timer as timer
        self.start = timer()
        return self

    def __exit__(self, *args):
        from timeit import default_timer as timer
        self.end = timer()
        self.t = self.end - self.start

# A utility to divide up the tracklets into smaller chunks
def chunk(k, chunk_size):
     return[ k[i:i + chunk_size] for i in range(0, len(k), chunk_size) ]

def to_fwf(fn, df):
    from tabulate import tabulate
    content = tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".12f")
    with open(fn, "w") as fp:
        fp.write(content)
        fp.write("\n")

# Function to display hostname and IP address
_iphost = None
def gethip():
    # cache the name resolution
    global _iphost
    if _iphost is None:
        import socket
        try:
            host_name = socket.gethostname()

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))  # connect() for UDP doesn't send packets
            host_ip = s.getsockname()[0]
            s.close()

            _iphost = (host_name, host_ip)
        except:
            _iphost = (None, None)

    return _iphost

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
    if "rmsMag" in df:
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
    if "rmsMag" in df:
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
## Web API app. Should be refactored to its own module.
##

class FitRunner:
    def __init__(self, fn):
        df, hdr = read_psv_ades(fn)
        if "rmsMag" in df:
            del df["rmsMag"] # workaround for FindOrb bug

        self.df, self.hdr = df, hdr
        self.total = len(self.df)
        self.result = []
        
        self.tend = None

    def stats(self):
        # return the time this batch took to execute, and
        # the ETA if it's still running

        if self.tend is None:
            now = datetime.now()
            if len(self.tasks) == 0:
                self.tend = now
        else:
            now = self.tend

        dt = now - self.tstart

        if self.result:
            return dt, timedelta(seconds = (self.total / len(self.result) - 1) * dt.seconds);
        else:
            return dt, None

    def start(self, chunk_size=10, ntracklets=None):
        self.tstart = datetime.now()
    
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

    async def collect(self, num_returns=None, timeout=0):
        if num_returns == None:
            num_returns = len(self.tasks)

        if len(self.tasks) == 0:
            return 0

        # collect the results that have finished
#        done, tasks = ray.wait(self.tasks, num_returns=num_returns, timeout=timeout)
#        chunked_results = ray.get(done)
        import asyncio
        done, tasks = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout)
        chunked_results = [ task.result() for task in done ]

        results = [result for chunk in chunked_results for result in chunk]
        
        self.result += results
        self.tasks = tasks

        print("len(result)=", len(self.result))
        return len(results)

###############################################
#
# FastAPI server
#

#
# Quick API sketch:
#      GET /fit              -> [ id1, id2, ... ]
#     POST /fit/[FILE]       -> { id: str }, 202 (Accepted)
#      GET /fit/<id>         -> { status }
#      GET /fit/<id>/result  -> { results }
#

from typing import Optional

from fastapi import FastAPI, Path, Query, Request, Response, File, UploadFile, Form, HTTPException, Depends, status
from starlette.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Any
from datetime import datetime, timedelta

tags_metadata = [
    {
        "name": "fitter",
        "description": "Orbit fitting operations",
    }
]

app = FastAPI(
#    root_path="/api/v1",
    title = "Orbit Fitter Service",
    description = "Scalable service for Solar System orbit fitting",
    version="0.0.1",
    openapi_tags=tags_metadata
)

@app.on_event("startup")
async def startup_event():
    ray.init(address='auto')

#########################################3

import os

from fastapi.security import HTTPBasicCredentials

if "ELASTICSKY_HTPASSWD" in os.environ:
    # Authentication (quick and dirty)
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    security = HTTPBasic()

    async def authenticate(
        credentials: HTTPBasicCredentials = Depends(security)
    ):
        from passlib.apache import HtpasswdFile
        ht = HtpasswdFile(os.environ["ELASTICSKY_HTPASSWD"])

        if not ht.check_password(credentials.username, credentials.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username
else:
    print("Running w/o direct API authentication; make sure your proxy authenticates");
    async def authenticate():
        return "anonymous"

# List of jobs
batches = {}

#######################################################

class Job(BaseModel):
    id: str = Field(..., max_length=40, title='Job identifier', description='An idenfitier uniquely identifying this job')
    url: HttpUrl = Field(..., title='Job resource URL', description='Resource URL to check for job status and fetch results')

@app.get(
    "/fit",
    summary="List all pending or completed jobs.",
    tags=[ "fitter" ],
    response_model=List[Job],
    response_description="List of pending or completed jobs."
)
async def fit_get(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(authenticate)
):
    result = []
    for id in batches.keys():
        url = request.url_for("fit_id_get", id=id)

        result.append(Job(id=id, url=url))
    return result

@app.post(
    "/fit",
    summary="Submit an orbit fitting job",
    tags=[ "fitter" ],
    response_model=Job,
    response_description="Description of the created job",
    status_code=200
)
async def fit_post(
    request: Request,
    response: Response,
    credentials: HTTPBasicCredentials = Depends(authenticate),
    ades: bytes = File(..., description="PSV-serialized ADES file"),
    ntracklets: int = Form(None, description="Number of tracklets to process", ge=1)
):
    #
    # Initiate a new fit. If the file and request correspond to something we've already run,
    # do not initiate a new run.
    #
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmpdir:
        fn = f"{tmpdir}/input.psv"
        with open(fn, 'wb') as fp:
            fp.write(ades)
            
        # generate the ID, as hash of the file
        import hashlib
        content = open(fn).read() + f"\nntracklets={ntracklets}"
        id = hashlib.md5(content.encode("utf-8")).hexdigest()

        # start a new fit, if it's not already in batches
        if id not in batches:
            runner = FitRunner(fn)
            runner.start(ntracklets=ntracklets)

            batches[id] = runner

            response.status_code = 201

    # compute the resource URL
    url = request.url_for("fit_id_get", id=id)

    return { 'id': id, 'url': url }

########################

class JobStatus(BaseModel):
    id: str
    done: bool
    ncores: int
    trk_done: int
    trk_pending: int
    started: datetime
    finished: Optional[datetime]
    eta: Optional[timedelta]
    runtime: Optional[timedelta]

@app.get(
    "/fit/{id:str}",
    summary="Get job status.",
    tags=[ "fitter" ],
    response_model=JobStatus,
    response_description="Job status details."
)
async def fit_id_get(
    request: Request,
    id: str,
    credentials: HTTPBasicCredentials = Depends(authenticate)
):
    try:
        runner = batches[id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

    await runner.collect()

    trk_done = len(runner.result)
    trk_pending = runner.total - trk_done
    runtime, eta = runner.stats()

    return JobStatus(
        id = id,
        done = trk_pending == 0,
        ncores = ray.cluster_resources()['CPU'],
        trk_done = trk_done,
        trk_pending = trk_pending,
        started = runner.tstart,
        finished = runner.tend,
        runtime = runtime,
        eta = eta
    )

from fastapi.responses import StreamingResponse

@app.get(
    "/fit/{id:str}/result",
    summary="Get job status.",
    tags=[ "fitter" ],
    response_model=List[Any],
    response_description="Results of a job (fitted orbits)."
)
async def fit_id_get(
    request: Request,
    id: str,
    begin: Optional[int] = None,
    end:   Optional[int] = None,
    credentials: HTTPBasicCredentials = Depends(authenticate)
):
    try:
        runner = batches[id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

    # return what the user asked for:
    # begin: starting point -- we may need to wait on collect if
    #        we haven't reached it yet
    if begin is None:
        begin = 0
    while begin < len(runner.result) and len(runner.tasks):
        await runner.collect(num_returns=1, timeout=None)

    # end:
    #   a) if a number, return result[begin:end]
    #   b) if None, return until the batch is finished
    if end is None:
        await runner.collect(timeout=None)
    else:
        while len(runner.result) < end and len(runner.tasks):
            await runner.collect(num_returns=1, timeout=None)

#    print(begin, end, len(runner.result))
    return runner.result[begin:end]

########################################################

@app.get(
    "/timeline-json",
    summary="Get Ray timeline in Chrome trace .json format",
    tags=["diagnostics"],
    response_description="The timeline in Chrome's trace JSON format",
)
async def timeline_get(
    credentials: HTTPBasicCredentials = Depends(authenticate)
):
    traceJson = ray.timeline()
    return traceJson

@app.get(
    '/timeline',
    summary="Display a trace of Ray timeline",
    tags=["diagnostics"],
)
@app.get('/timeline/', include_in_schema=False)
async def timeline_redirect(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(authenticate)
):
    return RedirectResponse(url=request.url_for('timeline_redirect') + "index.html", status_code=302)

from fastapi.staticfiles import StaticFiles
app.mount("/timeline", StaticFiles(directory="tv"), name="timeline")

import os
import uvicorn

if __name__ == "__main__":
    # bind to 0.0.0.0 if running in docker (127.0.0.1 isn't port-mapped on
    # the Mac)
    in_docker = os.path.exists('/.dockerenv')
    host = "0.0.0.0" if in_docker else "127.0.0.1"

    uvicorn.run(app, host=host, port=5000, log_level="info", forwarded_allow_ips='*')
