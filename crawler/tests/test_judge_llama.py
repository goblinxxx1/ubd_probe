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
