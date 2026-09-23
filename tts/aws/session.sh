# Shared session machinery for design and generate (tts_task.md 4.4, 6).
# Sourced after common.sh.
#
# This exists because the two session scripts differ only in their payload:
# both launch one tagged GPU instance, wait for it, prove they can terminate
# it, upload, run one thing, copy back and tear down. Everything up to "run one
# thing" is identical and is here.

SSH_OPTS="-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HOME/.ssh/known_hosts_sbgame -o ConnectTimeout=10"
SSH="ssh -i $KEY_FILE $SSH_OPTS"

# pick_image — our baked image if there is one, else the current DLAMI.
# Sets AMI and FROM_BAKED.
pick_image() {
    # REBAKE=1 forces the stock DLAMI even when a baked image exists, so that
    # setup.sh runs again. Needed because a baked image skips setup entirely:
    # without this, a change to setup.sh could never take effect.
    if [ "${REBAKE:-0}" = 1 ]; then
        AMI=""
    else
        AMI=$(aws ec2 describe-images --owners self \
            --filters "Name=tag:project,Values=$PROJECT_TAG" "Name=state,Values=available" \
            --query 'reverse(sort_by(Images,&CreationDate))[0].ImageId' --output text 2>/dev/null)
    fi
    if [ "$AMI" = "None" ] || [ -z "$AMI" ]; then
        AMI=$(aws ec2 describe-images --owners amazon \
            --filters 'Name=name,Values=Deep Learning OSS Nvidia Driver AMI GPU PyTorch*Ubuntu 22.04*' \
                      'Name=state,Values=available' \
            --query 'reverse(sort_by(Images,&CreationDate))[0].ImageId' --output text)
        FROM_BAKED=0
    else
        FROM_BAKED=1
    fi
    aws ec2 describe-images --image-ids "$AMI" \
        --query 'Images[0].[ImageId,Name,RootDeviceName,BlockDeviceMappings[0].Ebs.VolumeSize]' --output text
    ROOT_DEV=$(aws ec2 describe-images --image-ids "$AMI" \
               --query 'Images[0].RootDeviceName' --output text)
    [ "$FROM_BAKED" = 1 ] && echo "  (our baked image — setup is already in it)"
    [ "${REBAKE:-0}" = 1 ] && echo "  (--rebake: ignoring any baked image so setup.sh runs again)"
    return 0
}

# open_ssh_today — the operator's address changes; 4.3 says update it each session.
open_ssh_today() {
    SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
            --query 'SecurityGroups[0].GroupId' --output text)
    local ip
    ip=$(curl -s --max-time 10 https://checkip.amazonaws.com)
    [ -n "$ip" ] || die "could not determine this machine's public address"
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 \
        --cidr "$ip/32" >/dev/null 2>&1 && echo "  added $ip/32" || echo "  $ip/32 already present"
}

# launch_tagged <name> — one GPU instance, every zone tried, g6 then g5.
# Sets INSTANCE_ID, INSTANCE_TYPE.
launch_tagged() {
    local name=$1 userdata subnets types t s az errfile
    # 4.4 layer 1, the one that is left when everything else has failed.
    userdata=$(printf '#!/bin/bash\nshutdown -h +120\n' | base64 -w0)
    subnets=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
              --query 'Subnets[].SubnetId' --output text)
    [ -n "$subnets" ] || die "no subnets in $VPC_ID"
    types=$INSTANCE_TYPE
    [ "$INSTANCE_TYPE" = g6.xlarge ] && types="g6.xlarge g5.xlarge"
    errfile=$(mktemp)
    INSTANCE_ID=""
    for t in $types; do
        for s in $subnets; do
            az=$(aws ec2 describe-subnets --subnet-ids "$s" \
                 --query 'Subnets[0].AvailabilityZone' --output text)
            printf '  trying %-12s in %s … ' "$t" "$az"
            if INSTANCE_ID=$(aws ec2 run-instances \
                    --image-id "$AMI" --instance-type "$t" \
                    --subnet-id "$s" --security-group-ids "$SG_ID" --key-name "$KEY_NAME" \
                    --associate-public-ip-address \
                    --block-device-mappings \
                        "DeviceName=$ROOT_DEV,Ebs={VolumeSize=$ROOT_GB,VolumeType=gp3,DeleteOnTermination=true}" \
                    --instance-initiated-shutdown-behavior terminate \
                    --user-data "$userdata" \
                    --tag-specifications \
                        "ResourceType=instance,Tags=[{Key=project,Value=$PROJECT_TAG},{Key=Name,Value=$name}]" \
                        "ResourceType=volume,Tags=[{Key=project,Value=$PROJECT_TAG}]" \
                        "ResourceType=network-interface,Tags=[{Key=project,Value=$PROJECT_TAG}]" \
                    --query 'Instances[0].InstanceId' --output text 2>"$errfile"); then
                printf 'got it\n'
                INSTANCE_TYPE=$t
                rm -f "$errfile"
                # EC2 is eventually consistent: DescribeInstances can return
                # InvalidInstanceID.NotFound for an id RunInstances just
                # handed back. Seen on one launch and not the next, which is
                # the worst kind of bug to meet in session 2.
                aws ec2 wait instance-exists --instance-ids "$INSTANCE_ID"
                aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
                    --query 'Reservations[].Instances[].[InstanceId,InstanceType,LaunchTime]' --output text
                return 0
            fi
            INSTANCE_ID=""
            if grep -q InsufficientInstanceCapacity "$errfile"; then
                printf 'no capacity\n'; continue
            fi
            printf 'failed\n'; cat "$errfile" >&2
            die "launch failed for a reason that is not capacity; not retrying"
        done
    done
    rm -f "$errfile"
    die "no capacity for $types in any zone of $VPC_ID. Try again later."
}

# assert_can_terminate — 4.4's teardown permission, provable only once an
# instance exists. NOT a pipeline: the CLI exits 255 on DryRunOperation, and
# under `set -o pipefail` `aws ... | grep -q` can never report success.
assert_can_terminate() {
    local probe
    probe=$(aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --dry-run 2>&1 || true)
    case $probe in
        *DryRunOperation*) echo "  TerminateInstances on this instance: permitted" ;;
        *) printf '%s\n' "$probe" >&2
           die "TerminateInstances is DENIED for $INSTANCE_ID. Terminate it by hand NOW." ;;
    esac
}

# wait_for_ssh — sets PUBLIC_IP.
wait_for_ssh() {
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
    PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
                --query 'Reservations[].Instances[].PublicIpAddress' --output text)
    echo "  $PUBLIC_IP"
    local i
    for i in $(seq 1 60); do
        $SSH ubuntu@"$PUBLIC_IP" true 2>/dev/null && { echo "  sshd up after $((i*5))s"; return 0; }
        sleep 5
    done
    die "ssh never came up on $PUBLIC_IP"
}

# upload_tree <repo> — the tts package, minus everything regenerable.
upload_tree() {
    rsync -az -e "$SSH" --exclude '.venv' --exclude 'raw' --exclude '__pycache__' \
          --exclude 'voices/candidates' --exclude 'voices/preview' \
          "$1/tts" ubuntu@"$PUBLIC_IP":~/
}

run_setup() {
    $SSH ubuntu@"$PUBLIC_IP" 'bash ~/tts/remote/setup.sh'
}
