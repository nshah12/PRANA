# =============================================================================
#  PRANA — AWS Full Stack Installer
#  Run once to go from zero to a live production deployment on AWS.
#
#  Usage:  .\Start-Installation.ps1
#          .\Start-Installation.ps1 -Step 4        # resume from a step
#          .\Start-Installation.ps1 -DryRun        # plan only, no apply
# =============================================================================

param(
    [int]    $Step    = 1,
    [switch] $DryRun  = $false
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot
$STATE_FILE = "$ROOT\.install-state.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-Header($text) {
    Write-Host ""
    Write-Host "=" * 70 -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "=" * 70 -ForegroundColor Cyan
}

function Write-Step($n, $text) {
    Write-Host ""
    Write-Host "[ STEP $n ] $text" -ForegroundColor Yellow
    Write-Host "-" * 50 -ForegroundColor DarkGray
}

function Write-OK($text)   { Write-Host "  OK  $text" -ForegroundColor Green }
function Write-Info($text) { Write-Host "  ..  $text" -ForegroundColor Gray }
function Write-Warn($text) { Write-Host "  !!  $text" -ForegroundColor Magenta }
function Write-Fail($text) { Write-Host " FAIL $text" -ForegroundColor Red }

function Pause-ForUser($prompt) {
    Write-Host ""
    Write-Host "  >>> $prompt" -ForegroundColor White
    Write-Host "      Press ENTER when ready, or Ctrl+C to abort." -ForegroundColor DarkGray
    Read-Host | Out-Null
}

function Save-State($key, $value) {
    $state = if (Test-Path $STATE_FILE) { Get-Content $STATE_FILE | ConvertFrom-Json } else { [PSCustomObject]@{} }
    $state | Add-Member -NotePropertyName $key -NotePropertyValue $value -Force
    $state | ConvertTo-Json | Set-Content $STATE_FILE
}

function Get-State($key) {
    if (-not (Test-Path $STATE_FILE)) { return $null }
    $state = Get-Content $STATE_FILE | ConvertFrom-Json
    return $state.$key
}

function Require-Command($cmd, $installHint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Fail "$cmd not found.  Install: $installHint"
        exit 1
    }
    Write-OK "$cmd found"
}

# ── Banner ────────────────────────────────────────────────────────────────────

Write-Header "PRANA Platform — AWS Installer"
Write-Host ""
Write-Host "  This script provisions the full PRANA stack on AWS:" -ForegroundColor White
Write-Host "  VPC + Subnets, KMS, S3, MSK Kafka, ElastiCache Redis," -ForegroundColor White
Write-Host "  YugabyteDB, Kong Gateway, ECR, ECS (API/AI/ASK)," -ForegroundColor White
Write-Host "  Temporal, Route53 + ACM, GitHub Actions OIDC." -ForegroundColor White
Write-Host ""
if ($DryRun) { Write-Warn "DRY RUN MODE — terraform plan only, no apply." }
if ($Step -gt 1) { Write-Warn "Resuming from Step $Step" }


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Prerequisites
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 1) {
    Write-Step 1 "Checking prerequisites"

    Require-Command "aws"       "https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    Require-Command "terraform" "https://developer.hashicorp.com/terraform/downloads"
    Require-Command "docker"    "https://docs.docker.com/get-docker/"
    Require-Command "gh"        "winget install --id GitHub.cli  OR  https://cli.github.com/"
    Require-Command "git"       "https://git-scm.com/download/win"

    # Verify AWS credentials work
    try {
        $identity = aws sts get-caller-identity --output json | ConvertFrom-Json
        Write-OK "AWS identity: $($identity.Account) / $($identity.Arn)"
        Save-State "aws_account_id" $identity.Account
    } catch {
        Write-Fail "AWS credentials not configured. Run: aws configure"
        exit 1
    }

    # Verify gh auth
    try {
        gh auth status 2>&1 | Out-Null
        Write-OK "GitHub CLI authenticated"
    } catch {
        Write-Warn "GitHub CLI not authenticated. Run: gh auth login"
        Pause-ForUser "Complete 'gh auth login' then press ENTER."
    }

    Write-OK "All prerequisites satisfied."
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Collect configuration inputs
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 2) {
    Write-Step 2 "Collect deployment configuration"

    $AWS_ACCOUNT_ID = Get-State "aws_account_id"
    $AWS_REGION     = "ap-south-1"

    Write-Host ""
    Write-Host "  Answer the prompts below. Values are saved to .install-state.json" -ForegroundColor DarkGray
    Write-Host "  and reused if you resume. Never commit .install-state.json." -ForegroundColor DarkGray
    Write-Host ""

    $DOMAIN = if (Get-State "domain_name") { Get-State "domain_name" } else {
        Read-Host "  Domain name (e.g. prana.in)"
    }
    Save-State "domain_name" $DOMAIN

    $GITHUB_REPO = if (Get-State "github_repo") { Get-State "github_repo" } else {
        Read-Host "  GitHub repo (e.g. nshah12/PRANA)"
    }
    Save-State "github_repo" $GITHUB_REPO

    $YB_PASSWORD = if (Get-State "yugabytedb_password") { Get-State "yugabytedb_password" } else {
        $pass = -join ((65..90) + (97..122) + (48..57) + (33,35,36,37,38,42) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
        $pass
    }
    Save-State "yugabytedb_password" $YB_PASSWORD

    Write-OK "Config saved.  Domain: $DOMAIN | Repo: $GITHUB_REPO | DB password: [generated]"
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Bootstrap Terraform state + GitHub OIDC
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 3) {
    Write-Step 3 "Bootstrap: Terraform state bucket + DynamoDB + GitHub OIDC"

    $AWS_ACCOUNT_ID = Get-State "aws_account_id"
    $GITHUB_REPO    = Get-State "github_repo"

    Push-Location "$ROOT\terraform\bootstrap"
    try {
        Write-Info "terraform init (bootstrap — local state)..."
        terraform init -upgrade | Out-Null
        Write-OK "Init complete"

        $plan_args = @(
            "-var=aws_account_id=$AWS_ACCOUNT_ID",
            "-var=github_repo=$GITHUB_REPO"
        )

        if ($DryRun) {
            terraform plan @plan_args
        } else {
            Write-Info "terraform apply (bootstrap)..."
            terraform apply -auto-approve @plan_args

            $deploy_role_arn = terraform output -raw deploy_role_arn
            $state_bucket    = terraform output -raw state_bucket
            Save-State "deploy_role_arn" $deploy_role_arn
            Save-State "state_bucket"    $state_bucket
            Write-OK "Deploy role ARN: $deploy_role_arn"
            Write-OK "State bucket:    $state_bucket"
        }
    } finally {
        Pop-Location
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — ACM Certificate (manual — AWS requires DNS validation)
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 4) {
    Write-Step 4 "ACM Certificate (manual step)"

    $DOMAIN = Get-State "domain_name"
    $ACM_ARN = Get-State "acm_certificate_arn"

    if (-not $ACM_ARN) {
        Write-Host ""
        Write-Host "  You need an ACM certificate for: api.$DOMAIN" -ForegroundColor White
        Write-Host "  AWS Console steps:" -ForegroundColor White
        Write-Host "    1. Open https://console.aws.amazon.com/acm/home?region=ap-south-1" -ForegroundColor DarkGray
        Write-Host "    2. Request a public certificate" -ForegroundColor DarkGray
        Write-Host "    3. Domain: api.$DOMAIN  (add *.$DOMAIN as a SAN too)" -ForegroundColor DarkGray
        Write-Host "    4. DNS validation — add the CNAME record to your DNS" -ForegroundColor DarkGray
        Write-Host "    5. Wait for status to show 'Issued'" -ForegroundColor DarkGray
        Write-Host "    6. Copy the Certificate ARN" -ForegroundColor DarkGray
        Write-Host ""
        Pause-ForUser "Complete ACM certificate creation, then press ENTER."

        $ACM_ARN = Read-Host "  Paste the Certificate ARN"
        Save-State "acm_certificate_arn" $ACM_ARN
    }

    Write-OK "ACM ARN: $ACM_ARN"
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — Route53 Hosted Zone
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 5) {
    Write-Step 5 "Route53 Hosted Zone"

    $DOMAIN = Get-State "domain_name"
    $ZONE_ID = Get-State "route53_zone_id"

    if (-not $ZONE_ID) {
        # Try to find it automatically
        $zones = aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN." --output json | ConvertFrom-Json
        $zone  = $zones.HostedZones | Where-Object { $_.Name -eq "$DOMAIN." } | Select-Object -First 1

        if ($zone) {
            $ZONE_ID = ($zone.Id -replace "/hostedzone/", "")
            Write-OK "Found hosted zone: $ZONE_ID"
        } else {
            Write-Warn "No hosted zone found for $DOMAIN in Route53."
            Write-Host "  Create one at https://console.aws.amazon.com/route53/v2/hostedzones" -ForegroundColor DarkGray
            Write-Host "  Then update your domain registrar's NS records to point to Route53." -ForegroundColor DarkGray
            Pause-ForUser "Create the hosted zone, then press ENTER."
            $ZONE_ID = Read-Host "  Paste the Hosted Zone ID (e.g. Z1ABC2DEF3GH4I)"
        }

        Save-State "route53_zone_id" $ZONE_ID
    }

    Write-OK "Route53 zone: $ZONE_ID"
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 6 — Generate prod.tfvars
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 6) {
    Write-Step 6 "Generate terraform/environments/prod/prod.tfvars"

    $AWS_ACCOUNT_ID = Get-State "aws_account_id"
    $DEPLOY_ROLE    = Get-State "deploy_role_arn"
    $DOMAIN         = Get-State "domain_name"
    $ZONE_ID        = Get-State "route53_zone_id"
    $ACM_ARN        = Get-State "acm_certificate_arn"
    $YB_PASSWORD    = Get-State "yugabytedb_password"
    $ECR_BASE       = "$AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/prana-prod"

    $tfvars = @"
# Auto-generated by Start-Installation.ps1 — DO NOT COMMIT
platform_admin_role_arn = "$DEPLOY_ROLE"

api_image = "$ECR_BASE/prana-api:latest"
ai_image  = "$ECR_BASE/prana-ai:latest"
ask_image = "$ECR_BASE/prana-ask:latest"

yugabytedb_password = "$YB_PASSWORD"

domain_name      = "$DOMAIN"
api_subdomain    = "api"
route53_zone_id  = "$ZONE_ID"
acm_certificate_arn = "$ACM_ARN"
"@

    $tfvars | Set-Content "$ROOT\terraform\environments\prod\prod.tfvars" -Encoding UTF8
    Write-OK "prod.tfvars written (not committed — in .gitignore)"
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 7 — Terraform init + plan + apply (prod)
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 7) {
    Write-Step 7 "Terraform init + apply (full prod stack)"
    Write-Warn "This provisions: VPC, KMS, S3, MSK, ElastiCache, YugabyteDB, Kong, ECR, ECS, Temporal"
    Write-Warn "Estimated time: 25-40 minutes"
    Write-Warn "Estimated cost: ~$800-1200/month at prod sizing"

    Push-Location "$ROOT\terraform\environments\prod"
    try {
        Write-Info "terraform init..."
        terraform init -upgrade | Out-Null
        Write-OK "Init complete"

        Write-Info "terraform plan..."
        terraform plan -var-file="prod.tfvars" -out="prod.tfplan"

        if (-not $DryRun) {
            Pause-ForUser "Review the plan above. Press ENTER to apply, or Ctrl+C to abort."
            Write-Info "terraform apply (grab a coffee — ~30 min)..."
            terraform apply "prod.tfplan"

            # Capture outputs for next steps
            $S3_BUCKET      = terraform output -raw s3_documents_bucket 2>$null
            $TEMPORAL_ADDR  = terraform output -raw temporal_address 2>$null
            $API_URL        = terraform output -raw api_url 2>$null
            Save-State "s3_documents_bucket" $S3_BUCKET
            Save-State "temporal_address"    $TEMPORAL_ADDR
            Save-State "api_url"             $API_URL
            Write-OK "Infrastructure live.  API URL: $API_URL"
        }
    } finally {
        Pop-Location
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 8 — DB schema migrations
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 8 -and -not $DryRun) {
    Write-Step 8 "Apply database schema (prana-db/schema.sql)"

    Write-Info "Running schema via ECS one-off task on prana-api..."

    $NETWORK_CFG = Get-State "ecs_network_config"
    if (-not $NETWORK_CFG) {
        Write-Warn "ECS network config not saved yet."
        Write-Host "  Find your private subnet ID and API security group ID in the AWS Console." -ForegroundColor DarkGray
        $subnet_id = Read-Host "  Private subnet ID (e.g. subnet-0abc123)"
        $sg_id     = Read-Host "  API security group ID (e.g. sg-0abc123)"
        $NETWORK_CFG = "{`"awsvpcConfiguration`":{`"subnets`":[`"$subnet_id`"],`"securityGroups`":[`"$sg_id`"],`"assignPublicIp`":`"DISABLED`"}}"
        Save-State "ecs_network_config" $NETWORK_CFG
    }

    $TASK_ARN = aws ecs run-task `
        --cluster prana-prod `
        --task-definition prana-prod-api `
        --launch-type FARGATE `
        --network-configuration $NETWORK_CFG `
        --overrides '{"containerOverrides":[{"name":"prana-api","command":["python","-m","prana_db.migrate"]}]}' `
        --query 'tasks[0].taskArn' --output text

    Write-Info "Schema migration task: $TASK_ARN"
    Write-Info "Waiting for completion..."
    aws ecs wait tasks-stopped --cluster prana-prod --tasks $TASK_ARN

    $EXIT_CODE = aws ecs describe-tasks --cluster prana-prod --tasks $TASK_ARN `
        --query 'tasks[0].containers[0].exitCode' --output text

    if ($EXIT_CODE -eq "0") {
        Write-OK "Schema migration complete."
    } else {
        Write-Fail "Migration failed (exit $EXIT_CODE). Check CloudWatch logs: /prana/prod/api"
        exit 1
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 9 — Set GitHub Actions secrets
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 9 -and -not $DryRun) {
    Write-Step 9 "Set GitHub Actions secrets"

    $GITHUB_REPO    = Get-State "github_repo"
    $DEPLOY_ROLE    = Get-State "deploy_role_arn"
    $S3_BUCKET      = Get-State "s3_documents_bucket"
    $NETWORK_CFG    = Get-State "ecs_network_config"

    $secrets = @{
        "AWS_DEPLOY_ROLE_ARN"  = $DEPLOY_ROLE
        "S3_DOCUMENTS_BUCKET"  = $S3_BUCKET
        "ECS_NETWORK_CONFIG"   = $NETWORK_CFG
    }

    foreach ($kv in $secrets.GetEnumerator()) {
        gh secret set $kv.Key --repo $GITHUB_REPO --body $kv.Value
        Write-OK "Secret set: $($kv.Key)"
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 10 — Upload kong.yml to S3
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 10 -and -not $DryRun) {
    Write-Step 10 "Upload kong/kong.yml to S3"

    $S3_BUCKET = Get-State "s3_documents_bucket"

    aws s3 cp "$ROOT\kong\kong.yml" "s3://$S3_BUCKET/config/kong.yml" `
        --sse aws:kms `
        --content-type "application/yaml"

    Write-OK "kong.yml uploaded to s3://$S3_BUCKET/config/kong.yml"
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 11 — Trigger first deploys via GitHub Actions
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 11 -and -not $DryRun) {
    Write-Step 11 "Trigger first deployments"

    $GITHUB_REPO = Get-State "github_repo"

    foreach ($workflow in @("deploy-api.yml", "deploy-ai.yml", "deploy-ask.yml", "deploy-kong.yml")) {
        gh workflow run $workflow --repo $GITHUB_REPO --field environment=prod
        Write-OK "Triggered: $workflow"
        Start-Sleep 2
    }

    Write-Info "Watching deploy-api.yml run..."
    gh run watch --repo $GITHUB_REPO
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 12 — Smoke test
# ═══════════════════════════════════════════════════════════════════════════════

if ($Step -le 12 -and -not $DryRun) {
    Write-Step 12 "Smoke test"

    $API_URL = Get-State "api_url"

    Write-Info "Hitting $API_URL/health ..."
    try {
        $resp = Invoke-WebRequest "$API_URL/health" -UseBasicParsing -TimeoutSec 15
        if ($resp.StatusCode -eq 200) {
            Write-OK "API health check passed (200 OK)"
        } else {
            Write-Warn "Unexpected status: $($resp.StatusCode)"
        }
    } catch {
        Write-Warn "Health check failed: $_"
        Write-Host "  Check CloudWatch logs: /prana/prod/api" -ForegroundColor DarkGray
    }

    python "$ROOT\scripts\smoke_test_cluster.py" --api-url $API_URL 2>$null
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DONE
# ═══════════════════════════════════════════════════════════════════════════════

Write-Header "Installation Complete"
$API_URL = Get-State "api_url"
Write-Host ""
Write-Host "  API        : $API_URL" -ForegroundColor Green
Write-Host "  API docs   : $API_URL/docs" -ForegroundColor Green
Write-Host "  Temporal UI: http://temporal.prana.local:8080  (VPN/bastion only)" -ForegroundColor Green
Write-Host "  GitHub CI  : https://github.com/$(Get-State 'github_repo')/actions" -ForegroundColor Green
Write-Host ""
Write-Host "  State file : .install-state.json  — keep it, don't commit it." -ForegroundColor DarkGray
Write-Host "  Resume     : .\Start-Installation.ps1 -Step <N>" -ForegroundColor DarkGray
Write-Host ""
