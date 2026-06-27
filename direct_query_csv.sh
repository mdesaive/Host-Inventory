#!/bin/bash

python ./app/main.py --source vmware --output csv --host https://localhost:8989 --username dummy --password secret

for dckip in 10.0.40.11 10.0.40.12 10.0.40.13 10.0.40.14 10.0.40.15 10.0.40.16
do
  python ./app/main.py --source docker  --output csv --host http://"${dckip}":2375
done
