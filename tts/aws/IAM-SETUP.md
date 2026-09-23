# AWS credentials for the TTS pipeline

Setup notes for `tts_task.md` §4.1 and §4.2. Everything here is done **once**, in the
console, as Mark's normal admin identity — the `sbgame-tts` policy deliberately cannot
touch IAM, so it cannot bootstrap itself.

Region throughout: **us-east-1**. Note that `tts_task.md` §4 says us-west-2; see
"Region" at the end of this document for why it is not. Profile name throughout: **`sbgame-tts`**.

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
      "Condition": { "StringNotEquals": { "aws:RequestedRegion": "us-east-1" } } },

    { "Sid": "Read", "Effect": "Allow",
      "Action": ["ec2:Describe*", "ssm:GetParameter", "ssm:GetParameters", "servicequotas:GetServiceQuota"],
      "Resource": "*" },

    { "Sid": "LaunchTaggedGpuOnly", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:us-east-1:*:instance/*",
      "Condition": { "StringEquals": { "ec2:InstanceType": ["g6.xlarge", "g5.xlarge"],
                                       "aws:RequestTag/project": "sbgame-tts" } } },

    { "Sid": "LaunchSupportingResources", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": ["arn:aws:ec2:us-east-1:*:volume/*", "arn:aws:ec2:us-east-1:*:network-interface/*",
                   "arn:aws:ec2:us-east-1:*:subnet/*", "arn:aws:ec2:us-east-1:*:security-group/*",
                   "arn:aws:ec2:us-east-1:*:key-pair/*", "arn:aws:ec2:us-east-1::image/*"] },

    { "Sid": "TagOnlyOnCreate", "Effect": "Allow", "Action": "ec2:CreateTags", "Resource": "*",
      "Condition": { "StringEquals": { "ec2:CreateAction": ["RunInstances", "CreateSecurityGroup", "CreateKeyPair"] } } },

    { "Sid": "CreateSgInVpc", "Effect": "Allow", "Action": "ec2:CreateSecurityGroup",
      "Resource": "arn:aws:ec2:us-east-1:*:vpc/*" },

    { "Sid": "CreateOwnSupport", "Effect": "Allow",
      "Action": ["ec2:CreateSecurityGroup", "ec2:CreateKeyPair"],
      "Resource": ["arn:aws:ec2:us-east-1:*:security-group/*", "arn:aws:ec2:us-east-1:*:key-pair/*"],
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
  `aws:RequestedRegion` is not us-east-1.

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
| Default region name | `us-east-1` |
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
    --quota-code L-DB2E81BA --region us-east-1 --profile sbgame-tts
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
---

## Region — why us-east-1 and not us-west-2

`tts_task.md` §4 specifies us-west-2. On 2026-09-22 the GPU quota there was found to be
0 and the AWS default for that quota is also 0, so it would have needed an increase
request and those are granted per region, on AWS's schedule — a day is normal.

The same quota is already **768** in us-east-1 and eu-west-1. Mark chose to move the work
to us-east-1 rather than wait. Everything else about the task is unchanged.

Consequences, all of them small:

- Every ARN in the policy, and the `aws:RequestedRegion` deny, names us-east-1.
- The key pair and the security group are region-scoped. The pair created in us-west-2 on
  2026-09-22 was deleted the same day, before the policy switched, since the new policy
  denies us-west-2 and would have stranded them. `~/.ssh/sbgame-tts.pem` is replaced when
  the us-east-1 pair is created.
- SSH from Seattle goes from roughly 20ms to 70ms. Irrelevant for an hour-long batch and
  a few hundred megabytes of scp.
- `tts_task.md` §4 is now wrong on this point. That document is maintained in chat, not
  here, so the correction belongs on that side.

## Verification run — 2026-09-22, us-west-2, before the move

Account `010358066382`, `arn:aws:iam::010358066382:user/sbgame-tts`, aws-cli 2.37.0.
Kept because it is what validated the policy's shape; the resource-specific rows have to
be repeated in us-east-1.

| Check | Result |
| --- | --- |
| `sts get-caller-identity` | `user/sbgame-tts` |
| `describe-instances` outside the allowed region | explicit deny, as designed |
| `create-key-pair` tagged `project=sbgame-tts` | `DryRunOperation` — would succeed |
| `create-security-group` tagged, into the default VPC | `DryRunOperation` — would succeed |
| `run-instances` g6.xlarge, tagged | `DryRunOperation` — would succeed |
| `run-instances` g5.xlarge, tagged | `DryRunOperation` — would succeed |
| `run-instances` g6.xlarge, **untagged** | denied |
| `run-instances` m5.large, tagged | denied |
| `revoke-security-group-ingress` on a tagged group | `DryRunOperation` — would succeed |
| `delete-security-group` on a tagged group | `DryRunOperation` — would succeed |
| `delete-key-pair` on a tagged pair | `DryRunOperation` — would succeed |

The `CreateSgInVpc` split in §1 is confirmed by the fourth row: the `tts_task.md` §4.2
draft as written would have failed there.

`TerminateInstances` is conditioned on `aws:ResourceTag/project` and cannot be dry-run
without a live instance — a syntactically invalid id is rejected before the authorisation
check. This is the one teardown permission that would first be exercised with a GPU
instance already billing, so `tts/aws/design` and `tts/aws/generate` dry-run it against
the new instance id immediately after launch and abort if it is denied.

## Verification run — 2026-09-22, us-east-1, after the policy was moved

Mark applied the us-east-1 policy the same day. Re-verified there, against real tagged
resources:

| Check | Result |
| --- | --- |
| `describe-instances --region us-west-2` | denied — the fence now points the other way |
| `describe-instances --region us-east-1` | allowed |
| `create-key-pair` tagged | created, `70:45:a7:da:80:bc:95:81:e0:2d:4b:b0:2d:f3:b8:aa:66:a4:5a:b9` |
| `create-security-group` tagged, into `vpc-03f154984d688285c` | created, `sg-08ea4c002f92de33f` |
| `authorize-security-group-ingress` 22/tcp from Mark's address | rule `sgr-0d4c8d12badfd54cf` |
| `run-instances` g6.xlarge, full session shape | `DryRunOperation` — would succeed |
| `run-instances` untagged | denied |
| `run-instances` m5.large, tagged | denied |
| `revoke-security-group-ingress` on the group | `DryRunOperation` |
| `delete-security-group` on the group | `DryRunOperation` |
| `delete-key-pair` on the pair | `DryRunOperation` |
| quota L-DB2E81BA | **768** — no increase needed |

The launch dry-run was the real thing, not a reduced one: the DLAMI, g6.xlarge, the
subnet, the security group, the key pair, `--associate-public-ip-address`,
`--instance-initiated-shutdown-behavior terminate` and tag specifications for the
instance, the volume and the network interface.

The private key at `~/.ssh/sbgame-tts.pem` is the us-east-1 pair; the us-west-2 one it
replaced was deleted and is useless.

## The network, and one thing for Mark to confirm

us-east-1 has **no default VPC** on this account, and the policy grants no permission to
create one or to create a VPC, subnet, route table or gateway. The only VPC in the region
is Mark's own:

| | |
| --- | --- |
| VPC | `vpc-03f154984d688285c`, named `sidell`, 10.0.0.0/24 |
| Subnets | `sidell-public-1` us-east-1a, `sidell-public-2` us-east-1b — both routed to `igw-0a8d34f9708fed344` |
| | `sidell-private-1/2` — routed through `i-0a08b97812c36f7c3`, a t4g.micro NAT instance |
| Other groups | `pttlb`, `24carrot`, `dynips`, `default` |
| Chosen | `subnet-08262cf96e4f9ad28` (public-1, us-east-1a); g6.xlarge and g5.xlarge are both offered there |

So the GPU instance would sit in the same /24 as whatever else Mark runs there. It gets
its own security group, inbound 22 from one address, and it is terminated at the end of
the session. It does not touch the existing groups, the NAT instance or the route tables.

`tts/aws/teardown` filters on `tag:project=sbgame-tts`, and that filter currently returns
nothing at all in the region — the NAT instance is not tagged that way and cannot be
caught by it. That filter is the only thing standing between teardown and the rest of
Mark's infrastructure, which is worth knowing given it now shares a VPC.

If that is not wanted, the alternative is a dedicated VPC, which needs `ec2:CreateVpc`,
`CreateSubnet`, `CreateRouteTable`, `CreateInternetGateway` and their delete counterparts
added to the policy, or a default VPC created once by Mark's admin identity
(`aws ec2 create-default-vpc`), which would be simpler and is free.
