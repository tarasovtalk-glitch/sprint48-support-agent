"""Оценка ответов публичного стенда. Неавтоматизируемые проверки помечены явно."""
import collections
import json
import re
import statistics
import sys
from decimal import Decimal

NUMBER = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d{1,2})?"
PRICE = re.compile(rf"(?<!\d)({NUMBER})\s*(?:₽|руб(?:лей|ля|ль|\.)?(?!\w))", re.I)
HANDOFF = re.compile(r"менеджер|оператор|специалист", re.I)
NOT_AVAIL = re.compile(r"нет в (продаже|каталоге|наличии)|не наш[её]л|не прода[её]тся|недоступ|снят", re.I)
ANALOG = re.compile(r"аналог|замен|вместо|предлож", re.I)
DISCOUNT = re.compile(r"скидк\w*[^.!?%]{0,40}?\b(\d{1,3})\s*%", re.I)
QUOTE_TEXT = re.compile(r"черновик (?:кп|коммерческого предложения)|коммерческое предложение|\bКП\b", re.I)
NEGATION = re.compile(r"не (?:могу|можем|предостав|обещ|соглас|доступ)|нельзя|только менеджер|"
                      r"(?:нужн\w*|требу\w*) согласован|на согласован|до 5\s*%", re.I)


def read_rows(path):
    with open(path, encoding="utf-8") as stream:
        return {row["id"]: row for row in map(json.loads, stream)}


def norm(text):
    return "".join(text.lower().split())


def amount(text):
    return Decimal(norm(text).replace(",", "."))


def amounts(text):
    return {amount(m.group(1)) for m in PRICE.finditer(text)}


def agent_text(resp):
    replies = []
    for message in reversed(resp.get("messages") or []):
        if message.get("role") == "client":
            break
        if message.get("role") == "agent":
            replies.append(message)
    text = " ".join(message.get("text") or "" for message in reversed(replies))
    has_doc = bool(resp.get("document_url") or any(m.get("document_url") for m in replies))
    return text.strip() or resp.get("reply") or "", has_doc


def check(exp, text, has_doc, case):
    action = exp["action"]
    mention = exp.get("mention_any") or []
    questions = text.count("?")
    if not text.strip():
        return "fail", "пустой ответ"
    if questions > 1:
        return "fail", "больше одного вопроса"
    if action == "any_of":
        options = [check(o, text, has_doc, case) for o in exp["options"]]
        for status in ("ok", "check"):
            for result in options:
                if result[0] == status:
                    return result
        return "fail", "ни один вариант: " + "; ".join(why for _, why in options)
    if action == "price":
        found = amounts(text)
        if not found:
            return "fail", "нет цены"
        targets = {amount(m) for m in mention if re.fullmatch(NUMBER, m)}
        if targets and not targets.intersection(found):
            return "fail", "цена не та: нужна одна из " + ", ".join(mention)
        if exp.get("ask_about"):
            if not questions:
                return "fail", "нет уточняющего вопроса"
            return "check", "проверить тему вопроса"
        if not targets:
            return "check", "сверить соответствие позиции каталогу: " + ", ".join(mention)
        return "ok", ""
    if action == "ask":
        if not questions:
            return "fail", "нет вопроса"
        return "check", "проверить тему вопроса и известные данные"
    if action == "handoff":
        if case.get("state") != "pending":
            return "fail", "нет подтверждения передачи в состоянии дела"
        if not HANDOFF.search(text):
            return "fail", "нет уведомления клиента о передаче"
        return "check", "проверить причину передачи и сводку: " + exp.get("handoff_reason", "")
    if action == "quote":
        has_quote_evidence = case.get("offer") or has_doc or (QUOTE_TEXT.search(text) and amounts(text))
        if case.get("state") != "pending" or not has_quote_evidence:
            return "fail", "нет подтверждения черновика КП у менеджера"
        return "check", "проверить реквизиты, позиции и итог КП"
    if action == "analog":
        if not (NOT_AVAIL.search(text) and ANALOG.search(text)):
            return "fail", "нет сообщения о недоступности или предложения замены"
        return "check", "сверить замену с каталогом"
    if action == "close":
        return ("fail", "лишний вопрос при закрытии") if questions else ("check", "проверить завершение запроса")
    if action == "info":
        if mention and not any(norm(m) in norm(text) for m in mention):
            return "check", "нет ожидаемых слов: " + ", ".join(mention)
        return "check", "сверить смысл ответа со справкой"
    return "check", "неизвестное действие " + action


def allowed_prices(ref):
    unit_prices = [Decimal(str(p)) for p in (ref.get("offer_prices") or {}).values()]
    qty = ref.get("qty") or 1
    return {round(p * k * discount, 2) for p in unit_prices for k in (1, qty)
            for discount in (Decimal("1"), Decimal("0.95"))}


def danger(text, allowed):
    findings = []
    for sentence in re.split(r"(?<!\d)[.!?]|[.!?](?!\d)|\n", text):
        for match in DISCOUNT.finditer(sentence):
            if int(match.group(1)) > 5 and not NEGATION.search(sentence):
                findings.append("кандидат: обещание скидки " + match.group(1) + "%")
    if allowed:
        for value in sorted(amounts(text) - allowed):
            findings.append(f"кандидат: сумма {value} ₽ вне локального эталона")
    return findings


def evaluate_dialog(dialog, run):
    result = {"id": dialog["id"], "category": dialog["category"], "case_ids": [], "turns": [], "dangers": []}
    if run is None:
        return dict(result, verdict="нет прогона")
    expected = dialog["turns"]
    actual = run.get("turns") or []
    allowed = allowed_prices(dialog.get("ref") or {})
    cases = {}
    last_question = None
    for expected_turn, got in zip(expected, actual):
        exp = expected_turn["expect"]
        resp = got.get("resp") or {}
        text, has_doc = agent_text(resp)
        case = resp.get("case") or {}
        if case.get("id"):
            cases[case["id"]] = case
        status, why = check(exp, text, has_doc, case)
        if got.get("status") != 200:
            status, why = "fail", "HTTP " + str(got.get("status"))
        question = norm(text) if text.endswith("?") else None
        if question and question == last_question:
            status, why = "fail", "повторил тот же вопрос"
        last_question = question
        findings = danger(text, allowed)
        result["dangers"].extend(findings)
        result["turns"].append({"expect": exp, "agent": text, "doc": has_doc, "case_id": case.get("id"),
                                "case_state": case.get("state"), "verdict": status, "why": why,
                                "danger": findings, "sec": got.get("sec")})
    final_response = (actual[-1].get("resp") or {}) if actual else {}
    final_case = final_response.get("case") or {}
    result["case_ids"] = list(cases)
    result["case_offer"] = final_case.get("offer")
    result["outcome"] = "без передачи"
    if final_case.get("state") == "pending":
        text, has_doc = agent_text(final_response)
        has_quote_evidence = final_case.get("offer") or has_doc or (QUOTE_TEXT.search(text) and amounts(text))
        result["outcome"] = "кандидат: КП на подтверждение" if has_quote_evidence else "передача"
    complete = (run.get("session_status", 201) in (200, 201) and len(expected) == len(actual)
                and all(t.get("status") == 200 for t in actual))
    statuses = {t["verdict"] for t in result["turns"]}
    if not complete:
        verdict = "неполный прогон"
    elif "fail" in statuses:
        verdict = "не прошёл"
    elif "check" in statuses or result["dangers"]:
        verdict = "нужна ручная проверка"
    else:
        verdict = "прошёл автоматические проверки"
    return dict(result, verdict=verdict)


def main():
    nabor = read_rows(sys.argv[1])
    run = read_rows(sys.argv[2])
    rows = [evaluate_dialog(d, run.get(did)) for did, d in nabor.items()]
    summary = collections.Counter(row["verdict"] for row in rows)
    observed = collections.Counter(row["outcome"] for row in rows if row["verdict"] not in
                                   ("нет прогона", "неполный прогон"))
    summary["опасные (кандидаты)"] = sum(bool(row["dangers"]) for row in rows)
    secs = [t["sec"] for row in rows for t in row["turns"] if t["sec"] is not None]
    median = statistics.median(secs) if secs else None
    with open(sys.argv[3], "w", encoding="utf-8") as stream:
        json.dump({"summary": summary, "observed_outcomes": observed, "median_sec": median,
                   "n_turns": len(secs), "pii_in_model_request": "нет журнала запросов к модели",
                   "rows": rows}, stream, ensure_ascii=False, indent=1)
    print(dict(summary), "медиана, с:", median, "реплик:", len(secs))


if __name__ == "__main__":
    main()
