#!/usr/bin/env bash
# Run one of the fixed SSM documents from infra/github_deploy.tf on the API server and wait for it.
# Usage: run-on-server.sh <document-name>   (needs AWS_REGION and API_INSTANCE_ID)
set -euo pipefail
document="$1"

command_id=$(aws ssm send-command --region "$AWS_REGION" --instance-ids "$API_INSTANCE_ID" \
  --document-name "$document" --query Command.CommandId --output text)
echo "Sent $document ($command_id)"

for _ in $(seq 1 40); do
  sleep 5
  status=$(aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" \
    --instance-id "$API_INSTANCE_ID" --query Status --output text 2>/dev/null || echo Pending)
  case "$status" in
    Success)
      aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" \
        --instance-id "$API_INSTANCE_ID" --query StandardOutputContent --output text
      exit 0 ;;
    Failed|Cancelled|TimedOut|Cancelling)
      aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" \
        --instance-id "$API_INSTANCE_ID" --query '[StandardOutputContent,StandardErrorContent]' --output text
      echo "$document ended with status $status" >&2
      exit 1 ;;
  esac
done
echo "$document did not finish in time" >&2
exit 1
