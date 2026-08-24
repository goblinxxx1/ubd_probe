"""LLM-суддя через локальний llama.cpp (llama-server, OpenAI-сумісний API).
Qwen2.5-7B-Instruct. Будь-яка помилка HTTP/парсингу -> JudgeError, щоб
circuit-breaker у RelevanceGate відкотив на поведінку-як-сьогодні."""

import json
import logging

from crawler.judge.base import Verdict

log = logging.getLogger(__name__)

_SYSTEM = (
    "Ти — модератор бази знижок для військових, ветеранів, УБД та інших "
    "захисників. Оціни кандидата-офер за ДВОМА вимірами й поверни СУВОРО JSON "
    "{\"genuine\": bool, \"page_scoped\": bool, \"reason\": \"<коротко українською>\"}.\n"
    "genuine=true, лише якщо текст пропонує РЕАЛЬНУ знижку/безкоштовну вигоду САМЕ "
    "цій аудиторії. Вигода для РОДИНИ захисника — дітям, дружині/чоловіку, батькам "
    "військового/ветерана/УБД — ТЕЖ рахується як genuine=true (це категорія «родина "
    "військового»); «знижка для дітей батьків УБД» чи «за наявності посвідчення УБД» "
    "= валідна вигода. genuine=false, якщо аудиторне слово чи знижка згадані випадково "
    "й не пов'язані (назва пісні/фільму, новина, цитата, пункт договору/публічної "
    "оферти, загальний каталог).\n"
    "page_scoped=true, якщо знижка є промо саме цієї сторінки; page_scoped=false, "
    "якщо це сайт-широкий банер, випадковий на сторінці з іншим змістом."
)

# Few-shot із реальних кейсів (негативи + позитиви).
_EXAMPLES = [
    ("Скачати пісню «Chico - Допоможе ЗСУ» безкоштовно у mp3 | musiua.com/get-uamusic/dopomozhe-zsu",
     {"genuine": False, "page_scoped": True, "reason": "«ЗСУ» — назва пісні, безкоштовне завантаження музики, не знижка для військових"}),
    ("Публічна оферта. 6. Знижки. 6.1 Дітям до 6 років безкоштовно | vidviday.ua/public-offer",
     {"genuine": False, "page_scoped": True, "reason": "пункт публічної оферти (умови), не промо"}),
    ("Імплантація зубів Osstem під ключ. Знижка 10% для учасників бойових дій (УБД) | whiteclinic.ua/promotions/implant",
     {"genuine": True, "page_scoped": False, "reason": "сторінка про імпланти; «10% УБД» — сайт-банер, не промо цієї сторінки"}),
    ("Знижка 15% для ветеранів та учасників бойових дій на всі послуги | clinic.ua/veteranam",
     {"genuine": True, "page_scoped": True, "reason": "присвячена сторінка знижки для ветеранів"}),
    ("Зоопарк Animal Park. Дітям до 7 років — знижка для дітей батьків УБД (при собі свідоцтво про народження), тільки за наявності посвідчення УБД | tickets.animalpark.com.ua",
     {"genuine": True, "page_scoped": True, "reason": "знижка дітям батьків УБД — вигода родині захисника (родина військового)"}),
]


class JudgeError(Exception):
    pass


class LlamaCppJudge:
    def __init__(self, client, model: str, timeout: float = 30.0):
        self._client = client
        self._model = model
        self._timeout = timeout

    def _candidate_text(self, cand) -> str:
        disc = f"{getattr(cand, 'discount_type', None)} {getattr(cand, 'discount_value', None)}"
        return (f"{getattr(cand, 'title', '') or ''}\n"
                f"{getattr(cand, 'body', '') or ''}\n"
                f"знижка: {disc}\n"
                f"url: {getattr(cand, 'article_url', '') or ''}")

    def _messages(self, cand):
        msgs = [{"role": "system", "content": _SYSTEM}]
        for text, out in _EXAMPLES:
            msgs.append({"role": "user", "content": text})
            msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": self._candidate_text(cand)})
        return msgs

    def verdict(self, cand) -> Verdict:
        body = {
            "model": self._model,
            "messages": self._messages(cand),
            "temperature": 0.0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        try:
            r = self._client.post("/v1/chat/completions", json=body, timeout=self._timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return Verdict(genuine=bool(parsed["genuine"]),
                           page_scoped=bool(parsed["page_scoped"]),
                           reason=str(parsed.get("reason", "")))
        except Exception as exc:  # noqa: BLE001 — будь-яка помилка -> JudgeError для circuit-breaker
            raise JudgeError(str(exc)) from exc
