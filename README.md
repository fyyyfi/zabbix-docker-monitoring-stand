# Стенд: моніторинг вузла та Docker-контейнерів за допомогою Zabbix 7.0

Склад: PostgreSQL 16, Zabbix server, веб-інтерфейс (nginx + PHP-FPM), два Zabbix agent 2,
приймач вебхуків, тестовий контейнер demo-app і генератор навантаження stress-ng.

## Запуск

```bash
docker compose up -d                  # ~1 хв на створення схеми БД
python3 scripts/setup_zabbix.py       # вузол docker-node, власні метрики, тригер, вебхук, дашборд
```

Веб-інтерфейс: http://localhost:8081, обліковий запис за замовчуванням `Admin` / `zabbix`.
Дашборд: «Панелі → Моніторинг вузла Docker».

## Експеримент

```bash
./scripts/scenario.sh                 # ~12 хв: фон -> stress-ng -> kill demo-app -> відновлення
docker compose exec alert-receiver cat /data/alerts.log
```

## Файли

| Файл | Призначення |
|---|---|
| `docker-compose.yml` | опис усіх сервісів і мереж |
| `.env` | паролі СУБД (лише для навчального стенду) |
| `agent/lab_params.conf` | власні метрики агента (UserParameter) |
| `receiver/receiver.py` | приймач вебхуків Zabbix |
| `load/Dockerfile` | образ зі stress-ng |
| `scripts/setup_zabbix.py` | налаштування через Zabbix API |
| `scripts/scenario.sh` | сценарій експерименту |
| `scripts/zbx.py` | помічник для ручних запитів до API |

Зупинити й видалити дані: `docker compose down -v`.
