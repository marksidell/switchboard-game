# Shared settings for the AWS session scripts (tts_task.md 4.4).
# Sourced, not run.

: "${AWS_PROFILE:=sbgame-tts}"
: "${AWS_DEFAULT_REGION:=us-east-1}"
export AWS_PROFILE AWS_DEFAULT_REGION

PROJECT_TAG=sbgame-tts
KEY_NAME=sbgame-tts
KEY_FILE=${KEY_FILE:-$HOME/.ssh/sbgame-tts.pem}
SG_NAME=sbgame-tts-default

# VPC_ID, the VPC the instances launch into (session.sh requires it): from the
# environment, or from local.env beside this file (not committed; see
# local.env.example). The launch tries each of its subnets and asks for a public
# address explicitly rather than depending on a subnet attribute.
_here=$(dirname "${BASH_SOURCE[0]}")
if [ -f "$_here/local.env" ]; then . "$_here/local.env"; fi

# The DLAMI's own root volume is 40GB and most of it is already spent on CUDA,
# the frameworks and the container images; qwen-tts and 4.3GB of model weights
# on top of that fill it. gp3 is about $0.08/GB-month, so the extra 60GB costs
# well under a cent for a session.
ROOT_GB=${ROOT_GB:-100}

# Every state except terminated: a stopped instance still holds its volume, and
# a shutting-down one is worth seeing.
LIVE_STATES=pending,running,shutting-down,stopping,stopped

die() { printf '%s\n' "$*" >&2; exit 1; }

command -v aws >/dev/null || die "aws CLI not found; see tts/aws/IAM-SETUP.md section 4"

# ids_of_ours [states] — instance ids tagged project=sbgame-tts, one per line.
ids_of_ours() {
    aws ec2 describe-instances \
        --filters "Name=tag:project,Values=$PROJECT_TAG" \
                  "Name=instance-state-name,Values=${1:-$LIVE_STATES}" \
        --query 'Reservations[].Instances[].InstanceId' --output text \
    | tr '\t' '\n' | sed '/^$/d'
}

# elapsed_since <iso8601> — "1h23m", as a human reads a bill.
elapsed_since() {
    local then now d
    then=$(date -d "$1" +%s 2>/dev/null) || { printf 'unknown'; return; }
    now=$(date +%s); d=$(( now - then ))
    printf '%dh%02dm' $(( d / 3600 )) $(( (d % 3600) / 60 ))
}
