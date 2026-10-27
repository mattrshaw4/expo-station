#!/usr/bin/env bash
# Fire a batch of random orders at the kitchen. Usage: ./scripts/fire-orders.sh [count] [delay_seconds]
set -euo pipefail

COUNT="${1:-20}"
DELAY="${2:-0.2}"
API="${API:-http://localhost:8000}"
DISHES=(burger fries salad steak risotto)

for ((i = 1; i <= COUNT; i++)); do
  dish="${DISHES[RANDOM % ${#DISHES[@]}]}"
  curl -s -X POST "$API/orders" -H 'Content-Type: application/json' -d "{\"dish\":\"$dish\"}"
  echo
  sleep "$DELAY"
done
