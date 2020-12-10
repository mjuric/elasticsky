## Proof of Concept for running Ray

### Cheatsheet

```
# Grab an example ADES file
curl https://epyc.astro.washington.edu/~moeyensj/rubin_submissions/ver5/2022-10-18T09:06:40.464Z_discoveries_01_LSST_TEST.psv -o input.psv

# Launch
ray up aws-ray.yaml
ray submit aws-ray.yaml elasticsky.py --port-forward=5000

# Submit job
curl -F 'ades=@input.psv' -F 'ntracklets=10000' http://localhost:5000/fit

# Watch status
watch "curl -s http://127.0.0.1:5000/fit/status/$ID"

# Grab results
curl -s "http://127.0.0.1:5000/fit/result/$ID" | jq -r '.[] | {trkSub: .name, epoch, state: .state_vect}'
curl -s "http://127.0.0.1:5000/fit/result/$ID" | jq -r '.[] | [ .name, .epoch, .state_vect[0], .state_vect[1], .state_vect[2], .state_vect[3], .state_vect[4], .state_vect[5] ] | @tsv'
```
