"""Налаштування стенду через Zabbix API (JSON-RPC 2.0).

Створює вузол docker-node, власні елементи даних і тригер, медіатип-вебхук,
дію для сповіщень і дашборд. Скрипт ідемпотентний: повторний запуск
пропускає вже створені об'єкти.

Запуск:  python3 scripts/setup_zabbix.py [http://localhost:8081]
"""
import json
import sys
import time
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081") + "/api_jsonrpc.php"
TOKEN = None


def api(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    req = urllib.request.Request(URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json-rpc"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        answer = json.load(resp)
    if "error" in answer:
        raise RuntimeError(f"{method}: {answer['error']['data']}")
    return answer["result"]


def one(method, flt, **extra):
    res = api(method, {"output": "extend", "filter": flt, **extra})
    return res[0] if res else None


# --- 0. Очікування веб-інтерфейсу й вхід -----------------------------------
for _ in range(60):
    try:
        print("Zabbix API", api("apiinfo.version", {}))
        break
    except Exception:
        time.sleep(5)
TOKEN = api("user.login", {"username": "Admin", "password": "zabbix"})

# --- 1. Вузол «Zabbix server»: агент доступний за DNS-ім'ям контейнера -----
srv = one("host.get", {"host": "Zabbix server"}, selectInterfaces="extend")
iface = srv["interfaces"][0]
api("hostinterface.update", {"interfaceid": iface["interfaceid"],
                             "useip": 0, "dns": "zabbix-agent", "ip": ""})
# Поріг тригера «High CPU utilization» знижено з 90 до 75 % для демонстрації
macros = api("usermacro.get", {"hostids": srv["hostid"], "filter": {"macro": "{$CPU.UTIL.CRIT}"}})
if not macros:
    api("usermacro.create", {"hostid": srv["hostid"], "macro": "{$CPU.UTIL.CRIT}", "value": "75"})

# --- 2. Група і вузол docker-node з шаблоном Docker -----------------------
grp = one("hostgroup.get", {"name": "Docker-вузли"})
gid = grp["groupid"] if grp else api("hostgroup.create", {"name": "Docker-вузли"})["groupids"][0]
tpl = one("template.get", {"host": "Docker by Zabbix agent 2"})

node = one("host.get", {"host": "docker-node"})
if not node:
    hid = api("host.create", {
        "host": "docker-node",
        "name": "docker-node",
        "groups": [{"groupid": gid}],
        "templates": [{"templateid": tpl["templateid"]}],
        "interfaces": [{"type": 1, "main": 1, "useip": 0, "ip": "",
                        "dns": "docker-node", "port": "10050"}],
        "tags": [{"tag": "env", "value": "lab"}],
        # виявляти лише контейнери цього стенду (проєкт zbx-lab)
        "macros": [{"macro": "{$DOCKER.LLD.FILTER.CONTAINER.MATCHES}", "value": "^/?zbx-lab"}],
    })["hostids"][0]
else:
    hid = node["hostid"]
iface_id = api("hostinterface.get", {"hostids": hid})[0]["interfaceid"]

# --- 3. Власні елементи даних (UserParameter з agent/lab_params.conf) -----
ITEMS = [
    ("Навантаження на ядро (LA1/CPU)", "lab.load.per_cpu", 0, ""),
    ("Процесів у черзі виконання", "lab.proc.running", 3, ""),
]
for name, key, vtype, units in ITEMS:
    if not one("item.get", {"key_": key}, hostids=hid):
        api("item.create", {"hostid": hid, "interfaceid": iface_id, "name": name,
                            "key_": key, "type": 0, "value_type": vtype,
                            "units": units, "delay": "15s", "history": "7d",
                            "tags": [{"tag": "component", "value": "cpu"}]})

# --- 4. Власний тригер ----------------------------------------------------
TRIGGER = "Перевантаження CPU на {HOST.NAME}: LA/ядро > 1.2"
if not one("trigger.get", {"description": TRIGGER}):
    api("trigger.create", {
        "description": TRIGGER,
        "expression": "avg(/docker-node/lab.load.per_cpu,2m)>1.2",
        "recovery_mode": 1,
        "recovery_expression": "avg(/docker-node/lab.load.per_cpu,2m)<0.8",
        "priority": 4,  # High
        "manual_close": 1,
        "comments": "Середнє за 2 хв навантаження на одне ядро перевищило 1,2.",
        "tags": [{"tag": "scope", "value": "performance"}],
    })

# --- 5. Медіатип «Webhook» -> контейнер alert-receiver --------------------
SCRIPT = r"""
var p = JSON.parse(value);
var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
var body = JSON.stringify({status: p.status, severity: p.severity, host: p.host,
                           subject: p.subject, event_id: p.event_id});
req.post(p.url, body);
if (req.getStatus() !== 200) { throw 'HTTP ' + req.getStatus(); }
return 'OK';
"""
mt = one("mediatype.get", {"name": "Lab webhook"})
if not mt:
    mtid = api("mediatype.create", {
        "name": "Lab webhook", "type": 4, "status": 0, "script": SCRIPT, "timeout": "10s",
        "parameters": [
            {"name": "url", "value": "http://alert-receiver:9000/"},
            {"name": "status", "value": "{EVENT.STATUS}"},
            {"name": "severity", "value": "{EVENT.SEVERITY}"},
            {"name": "host", "value": "{HOST.NAME}"},
            {"name": "subject", "value": "{ALERT.SUBJECT}"},
            {"name": "event_id", "value": "{EVENT.ID}"},
        ],
        "message_templates": [
            {"eventsource": 0, "recovery": 0, "subject": "Проблема: {EVENT.NAME}",
             "message": "Вузол {HOST.NAME}, важливість {EVENT.SEVERITY}"},
            {"eventsource": 0, "recovery": 1, "subject": "Вирішено: {EVENT.NAME}",
             "message": "Тривалість {EVENT.DURATION}"},
        ],
    })["mediatypeids"][0]
else:
    mtid = mt["mediatypeid"]

admin = one("user.get", {"username": "Admin"}, selectMedias="extend")
if not any(m["mediatypeid"] == mtid for m in admin["medias"]):
    api("user.update", {"userid": admin["userid"], "medias": [
        {"mediatypeid": mtid, "sendto": "lab", "active": 0,
         "severity": 60, "period": "1-7,00:00-24:00"}]})

# --- 6. Дія: сповіщати про проблеми з важливістю >= Average ---------------
if not one("action.get", {"name": "Сповіщення в лабораторний вебхук"}):
    op = {"operationtype": 0, "opmessage": {"default_msg": 1, "mediatypeid": mtid},
          "opmessage_usr": [{"userid": admin["userid"]}]}
    api("action.create", {
        "name": "Сповіщення в лабораторний вебхук", "eventsource": 0,
        "esc_period": "1m",
        "filter": {"evaltype": 0, "conditions": [
            {"conditiontype": 4, "operator": 5, "value": "3"}]},
        "operations": [op],
        "recovery_operations": [{"operationtype": 11,
                                 "opmessage": {"default_msg": 1}}],
    })

# --- 7. Примусово запустити виявлення контейнерів (за замовчуванням 15 хв)
rules = api("discoveryrule.get", {"hostids": hid, "output": ["itemid", "name"]})
api("task.create", [{"type": 6, "request": {"itemid": r["itemid"]}} for r in rules])

# --- 8. Дашборд ----------------------------------------------------------
def graph(x, y, w, h, title, series):
    fields = []
    for i, (host, item, color) in enumerate(series):
        fields += [{"type": 1, "name": f"ds.{i}.hosts.0", "value": host},
                   {"type": 1, "name": f"ds.{i}.items.0", "value": item},
                   {"type": 1, "name": f"ds.{i}.color", "value": color}]
    return {"type": "svggraph", "name": title, "x": x, "y": y,
            "width": w, "height": h, "fields": fields}


DASH = "Моніторинг вузла Docker"
if not one("dashboard.get", {"name": DASH}):
    widgets = [
        graph(0, 0, 36, 5, "CPU, %", [("Zabbix server", "CPU utilization", "E53935"),
                                     ("Zabbix server", "CPU iowait time", "1E88E5")]),
        graph(36, 0, 36, 5, "Навантаження на ядро (власна метрика)",
              [("docker-node", "Навантаження на ядро (LA1/CPU)", "8E24AA")]),
        graph(0, 5, 36, 5, "Пам'ять", [("Zabbix server", "Available memory", "43A047")]),
        graph(36, 5, 36, 5, "Процесів у черзі виконання (власна метрика)",
              [("docker-node", "Процесів у черзі виконання", "FB8C00")]),
        {"type": "problems", "name": "Активні проблеми", "x": 0, "y": 10,
         "width": 48, "height": 5, "fields": [{"type": 0, "name": "show_lines", "value": 10}]},
        {"type": "item", "name": "Запущено контейнерів", "x": 48, "y": 10,
         "width": 24, "height": 5, "fields": [
             {"type": 4, "name": "itemid.0", "value": one(
                 "item.get", {"key_": "docker.containers.running"}, hostids=hid)["itemid"]}]},
    ]
    api("dashboard.create", {"name": DASH, "display_period": 30, "auto_start": 1,
                             "pages": [{"widgets": widgets}]})

print("Готово: вузол docker-node =", hid, "медіатип =", mtid)
