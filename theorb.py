#!/usr/bin/env python

import requests
import ujson as json
from requests.auth import HTTPBasicAuth
from tqdm import tqdm

url = "http://127.0.0.1:5000/api/v1"
auth=None

class fit:
    def __init__(self, ades):
        self._len = None
        self._fit(ades)

    def _fit(self, ades):
        # start a fit
        files = {'ades': ('input.psv', open(ades, 'r').read())}
        r = requests.post(f"{url}/fit", files, auth=auth)
        r.raise_for_status()

        res = r.json()
        self._id, self._url = res["id"], res["url"]

    def status(self):
        r = requests.get(self._url, auth=auth)
        r.raise_for_status()

        return r.json()

    def __len__(self):
        if self._len is None:
            status = self.status()
            self._len = status['trk_done'] + status['trk_pending']

        return self._len

    class ResultIterable():
        def __init__(self, job, begin=None, end=None):
            qp = {}
            if begin is not None: qp['begin'] = begin
            if end   is not None: qp['end']   = end

            self.r = requests.get(f"{job._url}/result", auth=auth, stream=True, params=qp)
            self.r.raise_for_status()

            self.it = self.r.iter_lines()

            # calculate result length
            if end is None:
                end = len(job)
            if begin is None: begin = 0
            self._len = end - begin

        def __del__(self):
            self.r.close()

        def __len__(self):
            return self._len

        def __iter__(self):
            return self

        def __next__(self):
            return json.loads(next(self.it))

    def __iter__(self):
        return self.ResultIterable(self)

    def result(self, begin=None, end=None):
        return self.ResultIterable(self, begin, end)

    # context manager protocol
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        r = requests.delete(f"{self._url}", auth=auth)
        r.raise_for_status()

        return False

def login(username, password):
    global auth
    auth = HTTPBasicAuth(username, password)

    r = requests.get(f"{url}/fit", auth=auth)
    r.raise_for_status()

if __name__ == "__main__":
    import __main__ as theorb

    theorb.login('dirac', 'tribbles')

    # start the fit and stream back the results
    with theorb.fit("mini.psv") as f:
        for result in tqdm(f):
            #print(result["name"], result["state_vect"])
            pass
