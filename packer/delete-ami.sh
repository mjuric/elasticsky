#!/usr/bin/env bash
#
# Based on https://gist.githubusercontent.com/elasticdog/11152144/raw/6027ba02f63b55626737caaed0a7960f5043be8a/delete-ami
#

#
# delete-ami
#
# A script to deregister an Amazon Machine Image (AMI) and
# delete its corresponding root device snapshot.
#

##### Functions

# print a message to stderr
warn() {
	local fmt="$1"
	shift
	printf "delete-ami: $fmt\n" "$@" >&2
}

# print a message to stderr and exit with either
# the given status or that of the most recent command
die() {
	local st="$?"
	if [[ "$1" != *[^0-9]* ]]; then
		st="$1"
		shift
	fi
	warn "$@"
	exit "$st"
}

# print this script's usage message to stderr
usage() {
	cat <<-EOF >&2
	Usage: delete-ami -r REGION -a AMI-ID [-h]
	Deregister the given AMI and delete its root device snapshot
	EOF
}

##### Main

# reset all variables that might be set
region=''
ami_id=''

# parse command line options
while [[ "$1" != '' ]]
do
  case $1 in
    -r | --region)
      region=$2
      shift
      ;;
    --region=*)
      region=${1#*=}
      ;;
    -a | --ami-id)
      ami_id=$2
      shift
      ;;
    --ami-id=*)
      ami_id=${1#*=}
      ;;
    -h | --help | -\?)
      usage
      exit 0
      ;;
    --*)
      warn "unknown option -- ${1#--}"
      usage
      exit 1
      ;;
    *)
      warn "unknown option -- ${1#-}"
      usage
      exit 1
      ;;
  esac
  shift
done

# check for required command line options
if [[ ! $region ]]; then
  die 1 "option '--region=REGION' not given; see --help"
elif [[ ! $ami_id ]]; then
  die 1 "option '--ami-id=AMI_ID' not given; see --help"
fi

# check for dependencies
for cmd in {aws,jq}; do
	if ! command -v $cmd > /dev/null; then
		die 1 'required command "%s" was not found' "$cmd"
	fi
done

AMI_DESCRIPTION=$(aws --output json --region "$region" ec2 describe-images --image-ids "$ami_id" 2> /dev/null)
if [[ -z $AMI_DESCRIPTION ]]; then
	warn 'unable to find an AMI with the ID "%s"' "$ami_id"
	die 1 'run the following command to debug:\n  aws --output json --region %s ec2 describe-images --image-ids "%s"' "$region" "$ami_id"
fi

ROOT_DEVICE_NAME=$(printf "$AMI_DESCRIPTION" | jq --raw-output '.[][].RootDeviceName')
SNAPSHOT_ID=$(printf "$AMI_DESCRIPTION" | jq --raw-output ".[][].BlockDeviceMappings[] | select(.DeviceName == \"$ROOT_DEVICE_NAME\") | .Ebs.SnapshotId")

if [[ -z $SNAPSHOT_ID ]]; then
	warn 'unable to find a Snapshot ID for the "%s" root device on %s' "$ROOT_DEVICE_NAME" "$ami_id"
	die 1 'run the following command to debug:\n  aws --output json --region %s ec2 describe-images --image-ids "%s"' "$region" "$ami_id"
else
	if ! aws --output json --region "$region" ec2 deregister-image --image-id "$ami_id" > /dev/null; then
		die 'image deregistration failed; run the following command to debug:\n  aws --output json --region %s ec2 deregister-image --image-id "%s"' "$region" "$ami_id"
	fi
	if ! aws --output json --region "$region" ec2 delete-snapshot --snapshot-id "$SNAPSHOT_ID" > /dev/null; then
		die 'snapshot deletion failed; run the following command to debug:\n  aws --output json --region %s ec2 delete-snapshot --snapshot-id "%s"' "$region" "$SNAPSHOT_ID"
	fi
fi

exit 0
