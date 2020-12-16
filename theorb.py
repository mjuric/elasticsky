#!/usr/bin/env python

import requests
import ujson as json
from requests.auth import HTTPBasicAuth
from tqdm import tqdm

url = "http://127.0.0.1:5000"
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

    def result(self, begin=None, end=None):
        with requests.get(f"{self._url}/result", auth=auth, stream=True) as r:
            r.raise_for_status()

            # unserialize
            for line in r.iter_lines():
                yield json.loads(line)

    def __len__(self):
        if self._len is None:
            status = self.status()
            self._len = status['trk_done'] + status['trk_pending']

        return self._len

    def __iter__(self):
        it = self.result()

        # hack a len() method
#        def len(it_self):
#            return self.len()
#        it.__len__ = len

        return it

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
    with theorb.fit("medium.psv") as f:
        print(f"len={len(f)}")
        for result in tqdm(f.result(), total=len(f)):
            #print(result["name"], result["state_vect"])
            pass
