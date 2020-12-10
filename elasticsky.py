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

def fit_orbit(df, hdr):
    """Fit orbit with FindOrb to a single track in a multi-processing safe manner
    
    Args:
        df (pd.DataFrame): The observations to fit
        hdr (str): ADES file header for the observations in `df`
        
    Returns:
        dict: A dictionary with the result of the run, of the form::
        
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
    # make sure there's only a single tracklet
    assert len(df) >= 1
    assert len(df["trkSub"].unique()) == 1
    trkSub = df["trkSub"].iloc[0]

    # create a temporary directory
    import tempfile, subprocess, json, os
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"tmpdir: {tmpdir}")

        # prep the new "home" directory
        from shutil import copytree, ignore_patterns
        copytree(
            os.path.expanduser("~/.find_orb"), f"{tmpdir}/.find_orb",
            ignore=ignore_patterns('debug.txt', 'elements.json', 'elem_short.json', 'linux_p1550p2650.430t')
        )
        os.symlink(os.path.expanduser("~/.find_orb/linux_p1550p2650.430t"), f"{tmpdir}/.find_orb/linux_p1550p2650.430t")

        # dump to ades
        datafile = f"{tmpdir}/data.psv"
        resultdir = f"{tmpdir}/result"
        write_psv_ades(datafile, df, hdr)

        # call findorb
        cmd = f"fo {datafile} -O {resultdir} -D /Users/mjuric/projects/elasticsky/environ.dat"
        env = os.environ.copy()
        env["HOME"] = tmpdir
        ret = subprocess.run(cmd, shell=True, env=env, check=False, capture_output=True)

        # fetch/construct the result
        if ret.returncode == 0:
            # read the result
            with open(f"{resultdir}/covar.json") as fp:
                result = json.load(fp)
        else:
            result = {}

        result["name"] = trkSub
        result["findorb"] = {
            'args': ret.args,
            'returncode': ret.returncode,
            'stdout': ret.stdout.decode('utf-8'),
            'stderr': ret.stderr.decode('utf-8')
        }

        return result


def fit_orbit_batch(df, hdr, tracks=None):
    """Fit a batch of tracklets with FindOrb in a multi-processing safe manner

    These are all still processed within a single thread (process).

    Args:
        df (pd.DataFrame): The observations to fit
        hdr (str): ADES file header for the observations in `df`
        tracks (list): A list of trkSubs to fit; if None, process all from `df`
        
    Returns:
        dict: A dictionary of (trkSub: result), where result is the output of `fit_orbit`
    """
    if tracks is None:
        tracks = df['trkSub'].unique()

    results = []
    for trkSub in tracks:
        trk = df[df["trkSub"] == trkSub]
        results.append(fit_orbit(trk, hdr))
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

##
## Ray support
##

import ray

@ray.remote
def dist_fit_orbit_batch(df, hdr, tracks):
    return fit_orbit_batch(df, hdr, tracks)

##
## Main
##

def processAdesFile(fn, chunk_size=10, ntracklets=None):
    # load the file
    df, hdr = read_psv_ades(fn)
    del df["rmsMag"] # workaround for FindOrb bug

    # subdivide it into smaller chunks, with N tracklets each. These
    # chunks will be submitted to individual FindOrb threads to work on.
    tracks = chunk(df['trkSub'].unique(), chunk_size)

    # launch the parallel processing, and wait for the result
    df_id = ray.put(df)
    futures = [
        dist_fit_orbit_batch.remote(df_id, hdr, track_batch)
        for track_batch in tracks[:ntracklets]
    ]
    chunked_results = ray.get(futures)
    del df_id

    # merge the result chunks
    results = [result for chunk in chunked_results for result in chunk]

    return results

if __name__ == "__main__":
    ray.init()

    # grab this file from https://epyc.astro.washington.edu/~moeyensj/rubin_submissions/ver5/
    orbits = processAdesFile("2022-10-18T09:06:40.464Z_discoveries_01_LSST_TEST.psv", ntracklets=10)

    # basic info
    print(f"Number of results: {len(orbits)}")

    # check for failures
    failures = [ result for result in orbits if result['findorb']['returncode'] != 0]
    print(f"Number of failures: {len(failures)}")
    failures

    # construct dataframe of states and write it out
    states = [ result['state_vect'] for result in orbits ]
    epochs = [ result["epoch"] - 2400000.5 for result in orbits]
    keys = [ result['name'] for result in orbits ]
    states = pd.DataFrame(states, index=keys, columns=["x", "y", "z", "vx", "vy", "vz"])
    states["epoch"] = epochs
    states.reset_index(inplace=True)
    states = states.rename(columns = {'index':'trkSub'})
    states.sort_index()
    to_fwf("result.txt", states)
    print(f"Resuling states are in result.txt")
