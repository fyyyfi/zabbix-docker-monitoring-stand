"""Невеликий помічник для запитів до Zabbix API з командного рядка."""
import json, sys, urllib.request
U = "http://localhost:8081/api_jsonrpc.php"
_t = None
def api(m, p):
    global _t
    if _t is None and m != "user.login":
        _t = api("user.login", {"username": "Admin", "password": "zabbix"})
    r = urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "method": m, "params": p, "id": 1}).encode(),
                               {"Content-Type": "application/json-rpc"})
    if _t: r.add_header("Authorization", "Bearer " + _t)
    a = json.load(urllib.request.urlopen(r))
    if "error" in a: raise RuntimeError(a["error"])
    return a["result"]
