#!/bin/sh
# Сценарій експерименту: 2 хв спокою -> 5,5 хв навантаження -> аварійна
# зупинка demo-app -> 4 хв відновлення.
set -e
cd "$(dirname "$0")/.."
echo "$(date +%T) фон";            sleep 120
echo "$(date +%T) навантаження";   docker compose --profile load run --rm stress
echo "$(date +%T) kill demo-app";  docker compose kill demo-app
sleep 90
echo "$(date +%T) restart demo-app"; docker compose start demo-app
sleep 150
echo "$(date +%T) кінець"
