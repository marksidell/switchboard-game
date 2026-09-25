# AWS credentials for the TTS pipeline

Setup notes for `tts_task.md` §4.1 and §4.2. Everything here is done **once**, in the
console, as Mark's normal admin identity — the `sbgame-tts` policy deliberately cannot
touch IAM, so it cannot bootstrap itself.

Region throughout: **us-west-2**. Profile name throughout: **`sbgame-tts`**.

## 1. Create the policy

IAM → Policies → Create policy → JSON. Name it `sbgame-tts`.

This is the draft policy from `tts_task.md` §4.2 with the rough edge that document flags
already fixed: `CreateSecurityGroup` is split in two, because the request also names the
VPC, a VPC carries no request tag, and so the original single statement would be denied
on every call.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "OneRegionOnly", "Effect": "Deny", "Action": "ec2:*", "Resource": "*",
      "Condition": { "StringNotEquals": { "aws:RequestedRegion": "us-west-2" } } },

    { "Sid": "Read", "Effect": "Allow",
      "Action": ["ec2:Describe*", "ssm:GetParameter", "ssm:GetParameters", "servicequotas:GetServiceQuota"],
      "Resource": "*" },

    { "Sid": "LaunchTaggedGpuOnly", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:us-west-2:*:instance/*",
      "Condition": { "StringEquals": { "ec2:InstanceType": ["g6.xlarge", "g5.xlarge"],
                                       "aws:RequestTag/project": "sbgame-tts" } } },

    { "Sid": "LaunchSupportingResources", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": ["arn:aws:ec2:us-west-2:*:volume/*", "arn:aws:ec2:us-west-2:*:network-interface/*",
                   "arn:aws:ec2:us-west-2:*:subnet/*", "arn:aws:ec2:us-west-2:*:security-group/*",
                   "arn:aws:ec2:us-west-2:*:key-pair/*", "arn:aws:ec2:us-west-2::image/*"] },

    { "Sid": "TagOnlyOnCreate", "Effect": "Allow", "Action": "ec2:CreateTags", "Resource": "*",
      "Condition": { "StringEquals": { "ec2:CreateAction": ["RunInstances", "CreateSecurityGroup", "CreateKeyPair"] } } },

    { "Sid": "CreateSgInVpc", "Effect": "Allow", "Action": "ec2:CreateSecurityGroup",
      "Resource": "arn:aws:ec2:us-west-2:*:vpc/*" },

    { "Sid": "CreateOwnSupport", "Effect": "Allow",
      "Action": ["ec2:CreateSecurityGroup", "ec2:CreateKeyPair"],
      "Resource": ["arn:aws:ec2:us-west-2:*:security-group/*", "arn:aws:ec2:us-west-2:*:key-pair/*"],
      "Condition": { "StringEquals": { "aws:RequestTag/project": "sbgame-tts" } } },

    { "Sid": "ManageOnlyOwn", "Effect": "Allow",
      "Action": ["ec2:TerminateInstances", "ec2:AuthorizeSecurityGroupIngress",
                 "ec2:RevokeSecurityGroupIngress", "ec2:DeleteSecurityGroup", "ec2:DeleteKeyPair"],
      "Resource": "*",
      "Condition": { "StringEquals": { "aws:ResourceTag/project": "sbgame-tts" } } }
  ]
}
```

### What changed from the §4.2 draft, for review

- **`CreateSgInVpc` added.** Unconditional `CreateSecurityGroup` against the VPC; the
  request-tag condition stays on the group itself. Without this, security group creation
  is denied outright.
- **`CreateOwnSupport` narrowed** from `"Resource": "*"` to the two resource types it
  actually creates, so the request-tag condition means something.
- Everything else is verbatim from §4.2.

### Two things to know about how it hangs together

- `ManageOnlyOwn` keys on `aws:ResourceTag/project`, which works only because
  `TagOnlyOnCreate` allows the tag to be applied at creation time. If a resource ever
  lands untagged, this identity can no longer delete it and it has to be cleaned up as
  admin.
- The `OneRegionOnly` deny covers `ec2:*` only. `ssm` and `servicequotas` here are
  read-only. Widening the deny to `"*"` would break global endpoints such as STS, whose
  `aws:RequestedRegion` is not us-west-2.

## 2. Create the user

IAM → Users → Create user → `sbgame-tts`.

- Do **not** tick "Provide user access to the AWS Management Console". This identity is
  for the CLI only.
- Permissions → Attach policies directly → `sbgame-tts`.
- Create user.

## 3. Create the access key

The new user → Security credentials → Access keys → Create access key →
**Command Line Interface (CLI)** → acknowledge the warning → Create.

Copy the access key id and the secret access key. The secret is shown once and cannot be
retrieved afterwards.

Do not paste either into a chat session. They go straight into step 5.

## 4. Install the AWS CLI

There is no `awscli` apt package on this machine, so it is the official v2 installer:

```sh
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install
aws --version
```

## 5. Configure the profile

```sh
aws configure --profile sbgame-tts
```

Answers:

| Prompt | Value |
| --- | --- |
| AWS Access Key ID | from step 3 |
| AWS Secret Access Key | from step 3 |
| Default region name | `us-west-2` |
| Default output format | `json` |

Then tighten the file:

```sh
chmod 600 ~/.aws/credentials
```

Every AWS call in this pipeline passes `--profile sbgame-tts` explicitly.

## 6. Verify before spending anything

Identity — must report `user/sbgame-tts`:

```sh
aws sts get-caller-identity --profile sbgame-tts
```

GPU quota — must be at least **4** vCPUs (one xlarge):

```sh
aws service-quotas get-service-quota --service-code ec2 \
    --quota-code L-DB2E81BA --region us-west-2 --profile sbgame-tts
```

Confirm in the console (Service Quotas → EC2 → search "On-Demand G") that `L-DB2E81BA`
is still **Running On-Demand G and VT instances** rather than trusting that code. If the
value is 0, request an increase immediately: it can take a day, and nothing past this
point can proceed without it.

Region fence — this must **fail** with an explicit-deny error, not succeed:

```sh
aws ec2 describe-instances --region us-east-1 --profile sbgame-tts
```

## 7. Budget alert (optional, §4.1 item 3)

Billing → Budgets → a monthly cost budget with an email threshold at, say, $10. A
g6.xlarge is roughly $1/hour, so this catches a session that was never torn down.

## 8. Then, before the first real launch

Claude Code dry-runs every mutating action and reports which ones the policy rejects, so
the policy gets adjusted once rather than in the middle of a session:

- `ec2:RunInstances` for both `g6.xlarge` and `g5.xlarge`
- `ec2:CreateSecurityGroup`, `ec2:AuthorizeSecurityGroupIngress`
- `ec2:CreateKeyPair`
- `ec2:TerminateInstances`, `ec2:DeleteSecurityGroup`

No instance is launched until that output has been reviewed.

## Housekeeping

- `~/.aws/credentials` is never committed and never leaves this machine.
- Rotate the access key if it is ever exposed: IAM → the user → Security credentials →
  deactivate, create a new one, `aws configure --profile sbgame-tts` again, then delete
  the old key.
- The key pair for SSH is a separate thing, created by the pipeline itself:
  `sbgame-tts`, private key at `~/.ssh/sbgame-tts.pem`, mode 0600 (`tts_task.md` §4.3).
