# PRANA Terraform — which environment to use, and when

**Read this before running `terraform apply` anywhere.** The root `CLAUDE.md`
describes the target architecture — Kafka/Redis/YugabyteDB dual-region,
MirrorMaker2, Global Datastore — as "DECIDED, NOT optional." That describes
the architecture PRANA is built to scale to (per `project_scale_strategy.md`:
1 lakh orgs, 1 crore employees). It does **not** mean every environment must
run at that scale from day one. Provisioning `environments/prod` before there
is a single live, paying organization has previously cost ~$12-15k/month
(~₹10-13L) for infrastructure serving zero traffic — MSK brokers, dual-region
YugabyteDB nodes, and GPU compute all bill by the hour regardless of load.

## The three environments

| | `dev` | `staging` | `prod` |
|---|---|---|---|
| **Use when** | Local development, feature work, testing (this is what you should be using right now if there is no live customer yet) | Real integration testing needed: partner HRMS integration, load testing, a demo environment that must stay up between sessions | A real, paying, live organization exists and needs production infra |
| **Kafka** | docker-compose, local | 1 broker/AZ, `kafka.m5.large`, single region, no MirrorMaker | 3+2 brokers/AZ, `kafka.m5.2xlarge`/`.xlarge`, **2 regions**, MirrorMaker2 |
| **Redis** | docker-compose, local | 1 cluster, single region | 2+2 clusters, **Global Datastore** across 2 regions |
| **YugabyteDB** | docker-compose, local | 3 nodes, `c5.2xlarge`, 200GB, 1 region | 6 nodes, `c5.4xlarge`, 1000GB, **2 regions** |
| **GPU compute** | none | 1× `g4dn.xlarge` | 2× `g4dn.2xlarge` |
| **Rough monthly cost** | ~$0 (S3+KMS+ECR only) | Low hundreds to low thousands USD | **~$12-15k+ USD**, before any real usage |

## The rule

**Default to `dev`.** Only move to `staging` when you have a concrete reason
that needs real AWS-hosted Kafka/Redis/YugabyteDB rather than
docker-compose — an actual scheduled load test, an actual partner HRMS
integration session, a demo that must survive your laptop being off. Tear
`staging` back down (`terraform destroy`) when that reason is over; it is not
meant to run continuously as a default.

**Never provision `prod`** until there is an actual signed/committed
organization onboarding — dual-region, MirrorMaker2, and Global Datastore
exist to serve real customers who need geographic redundancy or low
cross-region latency. None of that has any effect with zero live orgs; it is
pure idle cost.

## If `prod` is currently running with no live organizations

Tear it down:

```bash
cd terraform/environments/prod
terraform workspace select prod
terraform destroy -var-file="prod.tfvars"
```

Review the plan output before confirming — this is a real, hard-to-reverse
action against real infrastructure. If any real data exists in the prod
YugabyteDB cluster (it shouldn't, with zero live orgs, but verify), export it
first.

Then do local development against `dev` (docker-compose — see the root
`docker-compose.yml` and `prana-db/CLAUDE.md`) until there's a concrete
reason to stand `staging` back up.
