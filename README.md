## Proof of Concept for running Ray

### Cheatsheet

```
# Simple basic auth u/p while the service is up for testing purposes
AUTH=...

#
# Service dashboard: http://api.b612.ai/
# API Documentation: http://api.b612.ai/api/v1/docs
#

# Grab some orbits to fit
curl https://epyc.astro.washington.edu/~moeyensj/rubin_submissions/ver5/2022-10-18T09:06:40.464Z_discoveries_01_LSST_TEST.psv -o input.psv

# Submit them to the orbit fit service
curl -u "$AUTH" -F 'ades=@input.psv' http://api.b612.ai/api/v1/fit

# Now watch as the fit happens. It will start slowly, then autoscale doubling the number of cores every ~minute
# until it completes the run or maxes out at 240 cores.
# IMPORTANT #1: Copy the ID below from the response body of the curl call above
# IMPORTANT #2: The service is "clever" and it caches results for files it already computed. If you get an instantaneous
#               completion, it means someone before you has submitted the file. Edit it, drop an observation at random, then
#               resubmit (it should generate a different ID).
ID=0bf01cc5dab9d9b8e6f008eb37e05d66
watch "curl -u "$AUTH" -Ls http://api.b612.ai/api/v1/fit/$ID | jq"

# Stream back the results (and reformat them into a table)
curl -s -u "$AUTH" "http://api.b612.ai/api/v1/fit/$ID/result" \
        | jq -r '[ .name, .epoch, .state_vect[0], .state_vect[1], .state_vect[2], .state_vect[3], .state_vect[4], .state_vect[5] ] | @tsv'
```

### Cheatsheet (old)

```
# Documentation URL
# Visit http://127.0.0.1:5000/api/v1/docs in browser

# Grab an example ADES file
curl https://epyc.astro.washington.edu/~moeyensj/rubin_submissions/ver5/2022-10-18T09:06:40.464Z_discoveries_01_LSST_TEST.psv -o input.psv

# Launch
ray up aws-ray.yaml
ray submit aws-ray.yaml elasticsky.py --port-forward=5000

# Submit job
curl -F 'ades=@mini.psv' http://localhost:5000/api/v1/fit
curl -F 'ades=@input.psv' -F 'ntracklets=10000' http://localhost:5000/api/v1/fit

# Watch status
watch "curl -s http://127.0.0.1:5000/api/v1/fit/status/$ID | jq"

# Grab results
curl -s "http://127.0.0.1:5000/api/v1/fit/$ID/result" | jq -r '{trkSub: .name, epoch, state: .state_vect}'
curl -s "http://127.0.0.1:5000/api/v1/fit/$ID/result" | jq -r '.[] | {trkSub: .name, epoch, state: .state_vect}'
curl -s "http://127.0.0.1:5000/api/v1/fit/$ID/result" | jq -r '.[] | [ .name, .epoch, .state_vect[0], .state_vect[1], .state_vect[2], .state_vect[3], .state_vect[4], .state_vect[5] ] | @tsv'
```

### Development

Running outside docker
```
ray start --head
./elasticsky.py
```

Building/running in Docker
```
docker build . -t elasticsky:latest
docker run --rm -it -v $PWD:/data -p 5000:5000 elasticsky:latest

# in the container, run
ray start --head
./elasticsky.py
```
