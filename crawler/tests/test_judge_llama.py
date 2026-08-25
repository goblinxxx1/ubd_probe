import json

import httpx

from crawler.judge.llama import LlamaCppJudge, JudgeError


class _Cand:
    title = "Скачати пісню Chico - Допоможе ЗСУ безкоштовно"
    body = "Скачати пісню безкоштовно у mp3"
    discount_type = "free"
    discount_value = None
    article_url = "https://musiua.com/get-uamusic/dopomozhe-zsu/"


def _client(handler):
    return httpx.Client(base_url="http://llama:8080",
                        transport=httpx.MockTransport(handler))


def test_llama_judge_parses_verdict():
    def handler(request):
        payload = {"choices": [{"message": {"content":
                   json.dumps({"genuine": False, "page_scoped": True,
                               "reason": "ЗСУ — назва пісні"})}}]}
        return httpx.Response(200, json=payload)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    v = j.verdict(_Cand())
    assert v.genuine is False and v.page_scoped is True and "пісн" in v.reason


def test_llama_judge_http_error_raises_judge_error():
    def handler(request):
        return httpx.Response(500, text="boom")
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeError:
        pass


def test_llama_judge_bad_json_raises_judge_error():
    def handler(request):
        payload = {"choices": [{"message": {"content": "not json at all"}}]}
        return httpx.Response(200, json=payload)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeError:
        pass


def test_candidate_text_truncates_long_body():
    j = LlamaCppJudge(_client(lambda r: httpx.Response(200, json={})), model="m")

    class C:
        title = "T"; discount_type = "percent"; discount_value = 20
        article_url = "u"; body = "x" * 5000

    text = j._candidate_text(C())
    assert "x" * 2000 + "…" in text
    assert "x" * 2001 not in text          # не більше 2000 підряд перед трьома крапками


def test_candidate_text_keeps_short_body():
    j = LlamaCppJudge(_client(lambda r: httpx.Response(200, json={})), model="m")

    class C:
        title = "T"; discount_type = "free"; discount_value = None
        article_url = "u"; body = "short body"

    text = j._candidate_text(C())
    assert "short body" in text and "…" not in text
