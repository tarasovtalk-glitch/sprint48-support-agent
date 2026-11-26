# Прогон проверочного набора через публичный чат стенда (как клиент на странице).
# Запуск: python3 -I progon.py <nabor60.jsonl> <out.jsonl> [id1,id2,...]
import json, sys, time, urllib.request, urllib.error
from collections import deque

API = "https://analyzebot.ru/support/api"
UA = {"User-Agent": "smf-progon/1.0", "Origin": "https://analyzebot.ru", "Referer": "https://analyzebot.ru/support/"}


POST_WINDOW_SEC = 60
POST_LIMIT = 10
post_starts = deque(maxlen=POST_LIMIT)


def wait_for_post_slot():
    if len(post_starts) == POST_LIMIT:
        # Запас 0,1 с оставляет первую попытку за границей скользящего окна.
        delay = post_starts[0] + POST_WINDOW_SEC + 0.1 - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    post_starts.append(time.monotonic())


def call(method, path, body=None, token=None, tries=12):
    h = dict(UA)
    if body is not None:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        if method == "POST":
            wait_for_post_slot()
        t0 = time.time()
        try:
            req = urllib.request.Request(API + path, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
                return r.status, (json.loads(txt) if txt else {}), round(time.time() - t0, 2)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                print("лимит на реплику, жду 60 с", flush=True); time.sleep(60); continue
            if e.code < 500 or i == tries - 1:
                return e.code, {"error": e.read().decode()[:300]}, round(time.time() - t0, 2)
        except Exception as e:  # сеть
            if i == tries - 1:
                return 0, {"error": str(e)[:300]}, round(time.time() - t0, 2)
        time.sleep(3)


def main():
    src, out = sys.argv[1], sys.argv[2]
    only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    done = set()
    try:
        for l in open(out, encoding="utf-8"):
            done.add(json.loads(l)["id"])
    except FileNotFoundError:
        pass
    with open(out, "a", encoding="utf-8") as f:
        for line in open(src, encoding="utf-8"):
            d = json.loads(line)
            if (only and d["id"] not in only) or d["id"] in done:
                continue
            for k in range(40):
                st, r, sec = call("POST", "/sessions")
                if st != 429:
                    break
                print(d["id"], "лимит стенда, жду 60 с", flush=True)
                time.sleep(60)
            rec = {"id": d["id"], "session_status": st, "turns": []}
            tok = r.get("session_token")
            if not tok:
                rec["error"] = r
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                print(d["id"], "нет сессии", st, r, flush=True)
                continue
            for i, t in enumerate(d["turns"]):
                body = {"text": t["client"]}
                if i == 0 and d.get("page"):
                    body["page_url"] = "https://" + d["page"]
                st, r, sec = call("POST", "/case/messages", body, tok)
                rec["turns"].append({"client": t["client"], "status": st, "sec": sec, "resp": r})
                time.sleep(1)
            # итоговая история разговора
            st, r, sec = call("GET", "/case/messages", None, tok)
            rec["history"] = r
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            time.sleep(25)
            print(d["id"], "ок", [x["status"] for x in rec["turns"]], [x["sec"] for x in rec["turns"]], flush=True)


if __name__ == "__main__":
    main()
