# Shared settings for the AWS session scripts (tts_task.md 4.4).
# Sourced, not run.

: "${AWS_PROFILE:=sbgame-tts}"
: "${AWS_DEFAULT_REGION:=us-east-1}"
export AWS_PROFILE AWS_DEFAULT_REGION

PROJECT_TAG=sbgame-tts
KEY_NAME=sbgame-tts
KEY_FILE=${KEY_FILE:-$HOME/.ssh/sbgame-tts.pem}
SG_NAME=sbgame-tts-default

# Mark created a default VPC in us-east-1 on 2026-09-22 so this work stays out
# of his own `sidell` VPC. Its subnets set MapPublicIpOnLaunch, but the launch
# asks for the address explicitly anyway rather than depending on a subnet
# attribute that is not ours and can be changed.
VPC_ID=${VPC_ID:-vpc-0b3420dc81332d21d}
SUBNET_ID=${SUBNET_ID:-subnet-0b5bd7185fea0efb5}   # us-east-1a; both GPU types offered
ASSOCIATE_PUBLIC_IP=1

# The DLAMI's own root volume is 40GB and most of it is already spent on CUDA,
# the frameworks and the container images. Installing qwen-tts and caching 4.3GB
# of model weights on top of that fills it: pip died with
# "[Errno 28] No space left on device". gp3 is about $0.08/GB-month, so the
# extra 60GB costs well under a cent for a session and removes the question.
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
