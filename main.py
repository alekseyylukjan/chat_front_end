# app.py
import os
import json
import re
from typing import Dict, Any, List, Optional
from fastapi.middleware.cors import CORSMiddleware
import duckdb
import pandas as pd
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from pydantic import BaseModel

# =======================
# Конфиг из окружения
# =======================
EXCEL_PATH = os.getenv("EXCEL_PATH", "./data2.xlsx")
MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
BASE_URL = os.getenv("POLZA_BASE_URL", "https://api.polza.ai/api/v1")
API_KEY = os.getenv("API_KEY", "")
ACCESS_CODE = os.getenv("ACCESS_CODE", "777")  # по умолчанию 777

# =======================
# Доступ по коду (777)
# =======================
def require_access_code(
    x_access_code: Optional[str] = Header(default=None, alias="X-Access-Code"),
    code: Optional[str] = Query(default=None),
):
    provided = x_access_code or code
    if not provided or provided != str(ACCESS_CODE):
        raise HTTPException(status_code=401, detail="Недоступно. Неверный или отсутствующий код доступа.")
    return True

# =======================
# Данные и справочники
# =======================
SUPPORTED_DIMS_RU = [
    "Группировка по направлению",
    "Предприятие с его филиалом (только для ресурсов)",
    "БЕ",
    "Год",
    "Месяц",
    "Период"
]

ATOMIC_METRICS_RU = [
    'Количество уволенных (для оттока, без стажеров)',
    'Количество уволенных (нежелательно, без стажеров)',
    'Количество уволенных (всего)'
]

DERIVED_METRICS_RU = {
    "Текучесть": "SUM(\"Количество уволенных (нежелательно, без стажеров)\") / SUM(\"Фактическая среднесписочная численность\")",
    "Отток": "SUM(\"Количество уволенных (для оттока, без стажеров)\") / SUM(\"Фактическая среднесписочная численность\")",
    "Укомплектованность от бизнес-плана (БП)": "SUM(\"Фактическая среднесписочная численность\") / SUM(\"Плановая средняя численность\")",
    "Укомплектованность от штатного расписания (ШР)": "SUM(\"Численность для укомплектованности от ШР\") / SUM(\"Количество ШД для укомплектованности от ШР\")",
    "Абсентеизм (доля отсутствий)": "SUM(\"Абсентеизм (отсутствия), час.\") / SUM(\"Фонд рабочего времени, час.\")",
    "Доля отсутствий по причине отпуска основного": "SUM(\"Отсутствия по причине отпуска основного, час.\") / SUM(\"Фонд рабочего времени, час.\")",
    "Доля отсутствий по причине больничного работника": "SUM(\"Отсутствия по причине больничных работника, час.\") / SUM(\"Фонд рабочего времени, час.\")",
    "Доля отсутствий по причине прочих больничных (уход за детьми и подобное)": "SUM(\"Отсутствия по причине больничных прочих, час.\") / SUM(\"Фонд рабочего времени, час.\")",
    "Среднее количество уволенных в месяц (всего)": "SUM(\"Количество уволенных (всего)\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)",
    "Среднее количество уволенных в месяц (для оттока)": "SUM(\"Количество уволенных (для оттока, без стажеров)\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)",
    "Среднее количество уволенных в месяц (для нежелательной текучести)": "SUM(\"Количество уволенных (нежелательно, без стажеров)\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)",
    "Плановая средняя численность": "SUM(\"Плановая средняя численность\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)",
    "Фактическая средняя численность": "SUM(\"Фактическая средняя численность\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)",
    "Фактическая среднесписочная численность": "SUM(\"Фактическая среднесписочная численность\") / NULLIF(COUNT(DISTINCT (\"Месяц\")), 0)"
}

# =======================
# Утилиты
# =======================
def load_excel_df(path: str) -> pd.DataFrame:
    return pd.read_excel(path)

def build_inventory_with_values(df: pd.DataFrame) -> Dict[str, Any]:
    inventory: Dict[str, Any] = {}
    for dim in SUPPORTED_DIMS_RU:
        if dim in df.columns:
            s = df[dim].dropna()
            unique_vals = list(map(str, s.unique()))
            inventory[dim] = {"dtype": str(s.dtype), "values": unique_vals}
        else:
            inventory[dim] = {"dtype": "unknown", "values": []}
    return inventory

def openrouter_chat(messages, model: str) -> str:
    # Читает BASE_URL и API_KEY из окружения (см. верх)
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    completion = client.chat.completions.create(model=model, messages=messages)
    return completion.choices[0].message.content

def llm_build_sql(user_text: str, inventory: Dict[str, Any], history: List[Dict[str, str]]) -> str:
    kb_formulas = {"atomic": ATOMIC_METRICS_RU, "derived": DERIVED_METRICS_RU, "group_dims": SUPPORTED_DIMS_RU}
    sys = """
        Ты программист на SQL. Получаешь вопрос и на базе него строишь один SQL-запрос SELECT к таблице *hr_facts*.
        В качестве разрезов аналитики используй ТОЛЬКО переданные измерения из инвентаря. Все имена полей — на русском. 
        В качестве агрегируемых полей или метрик используй ТОЛЬКО метрики из *atomic* и *derived*. Не придумывай метрики сам!
        
        КРИТИЧЕСКОЕ ТРЕБОВАНИЕ:
        1) Никогда НЕ пиши формулы в явном виде. Вместо формул используй ПЛЕЙСХОЛДЕРЫ вида f{<Название метрики>}.
           Примеры: f{Текучесть}, f{"Количество уволенных (для оттока, без стажеров)"}.
           Плейсхолдеры можно использовать в SELECT, WHERE, HAVING, ORDER BY.  Избегай ошибки связанной с неправильным вложением агрегатных функций. PostgreSQL запрещает использование одной агрегатной функции внутри другой.
        2) Всегда экранируй русские идентификаторы двойными кавычками.
        3) Если запрошены разрезы — добавь их в SELECT и GROUP BY.
        4) Применяй фильтры по измерениям, если они однозначно указаны. Если не смог их найти, тогда опиши это в ответе и не формируй sql запрос.
        5) Используй только метрики из базы знаний: *atomic* и *derived*.
        6) Если перечисленные требования выполнены, верни ответ в формате JSON:
           {
               "success": "1",
               "answer": "SQL-запрос"
           }
        7) Если перечисленные требования НЕ выполнены, верни ответ в формате JSON:
           {
               "success": "0",
               "answer": "текстовое обоснование причины без технических тонкостей, человеческим языком, предложи имеющиеся варианты на базе *knowledge_base* и *inventory* "
           }
        8) Рассмотри возможность ответа на базе истории сообщений *history*, если она позволяет ответить на вопрос пользователя однозначно и полностью, то не формируй SQL запрос, верни ответ в формате JSON:
           {
               "success": "2",
               "answer": "ответ на базе истории сообщений"
           }   
    """
    usr = json.dumps({
        "user_query": user_text,
        "inventory": inventory,
        'history': history,
        "knowledge_base": kb_formulas,
        "examples": [
            {
                "ask": "Текучесть по БЕ за 2025-05",
                "answer": {
                    "success":"1",
                    "message":
                        "SELECT \"БЕ\", "
                        "f{Текучесть} AS \"Текучесть\" "
                        "FROM hr_facts WHERE \"Месяц\" IN ('Май') AND  \"Год\" IN ('2025')  GROUP BY \"БЕ\";"
                },
            },
            {
                "ask": "Какая Численность и Отток по БЕ за 2025 год",
                "answer": {
                    "success":"1",
                    "message":
                        "SELECT \"БЕ\", "
                        "f{\"Фактическая средняя численность\"} AS \"Фактическая средняя численность\", "
                        "f{Отток} AS \"Отток\" "
                        "FROM hr_facts WHERE \"Год\" IN ('2025') GROUP BY \"БЕ\";"
                },
            },
            {
                "ask": "Какая по прокатному цеху 103 за 2024 год",
                "answer": {
                    "success":"0",
                    "message":
                        "Извините, но я не располагаю информацией по прокатному цеху 103."
                        "Вы можете попросить меня дать информацию по следующим разрезам аналитики: " + ", ".join(SUPPORTED_DIMS_RU) + "."
                },
            },
            {
                "ask": "Что ты имелл ввиду в своем прошлом ответе, объясни, как была построена эта метрика?",
                "answer": {
                    "success":"2",
                    "message":
                        "В предыдущем ответе я рассчитал по вашему запросу метрику Отток, форму расчета следующая: SUM(\"Количество уволенных (для оттока, без стажеров)\") / SUM(\"Фактическая среднесписочная численность\")"
                },
            }
        ]
    }, ensure_ascii=False)

    raw = openrouter_chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        model=MODEL
    )
    return raw.strip()

def expand_metric_placeholders(
    sql_text: str,
    atomic_metrics: List[str],
    derived_metrics: Dict[str, str]
) -> str:
    atomic_set = set(atomic_metrics)
    derived_map = dict(derived_metrics)
    pattern = re.compile(r'f\{\s*"?([^"}]+)"?\s*\}')

    def _replace(m: re.Match) -> str:
        name = m.group(1).strip()
        if name in derived_map:
            return f"({derived_map[name]})"
        if name in atomic_set:
            return f"SUM(\"{name}\")"
        norm = " ".join(name.split())
        if norm in derived_map:
            return f"({derived_map[norm]})"
        if norm in atomic_set:
            return f"SUM(\"{norm}\")"
        raise ValueError(f"Неизвестная метрика в плейсхолдере: '{name}'. Допустимые метрики: atomic={list(atomic_set)}, derived={list(derived_map.keys())}")
    return pattern.sub(_replace, sql_text)

def _extract_json_blob(s: str) -> str:
    m = re.search(r'\{.*\}', s, flags=re.DOTALL)
    return m.group(0) if m else s

def _parse_llm_sql_response(s: str) -> Dict[str, Any]:
    blob = _extract_json_blob(s)
    try:
        obj = json.loads(blob)
    except Exception:
        return {"success": "0", "text": "Не удалось распарсить JSON из ответа модели."}
    success = str(obj.get("success", "0"))
    text = obj.get("answer") or obj.get("message") or ""
    return {"success": success, "text": text}

def _strip_code_fences(sql_text: str) -> str:
    t = sql_text.strip()
    t = re.sub(r'^\s*```(?:sql)?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*```\s*$', '', t)
    return t.strip()

# =======================
# FastAPI
# =======================
app = FastAPI(title="HR Metrics QA", version="1.0.0")

# Разрешенные источники (укажите свои, или "*" для всех)
origins = [
    "https://1t3w-8kjv-f78l.gw-1a.dockhost.net",
    # добавьте сюда другие домены, если нужно
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # или ["*"] для разрешения любых
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskPayload(BaseModel):
    question: str
    history: List[Dict[str, str]] = []

# Глобальные объекты (кэш в памяти)
df_global: Optional[pd.DataFrame] = None
inventory_global: Optional[Dict[str, Any]] = None


@app.on_event("startup")
def _startup():
    global df_global, inventory_global
    if not os.path.exists(EXCEL_PATH):
        raise RuntimeError(f"EXCEL_PATH не найден: {EXCEL_PATH}")
    df_global = load_excel_df(EXCEL_PATH)
    inventory_global = build_inventory_with_values(df_global)

@app.post("/ask")
def ask(payload: AskPayload, _=Depends(require_access_code)):
    """
    Принимает JSON: {"question": "..."}.
    Возвращает:
      - success != "1": текстовый ответ модели
      - success == "1": финальный ответ + предпросмотр данных
    """
    if df_global is None or inventory_global is None:
        raise HTTPException(status_code=500, detail="Данные ещё не готовы.")

    user_text = payload.question
    history = payload.history # history: List[Dict[str, str]] = []

    # 1) Построить SQL через LLM (с плейсхолдерами)
    llm_reply = llm_build_sql(user_text, inventory_global, history)
    resp = _parse_llm_sql_response(llm_reply)

    if resp["success"] != "1":
        final_answer = resp["text"] or "Модель не смогла сформировать SQL."
        return {
            "mode": "text_only",
            "success": resp["success"],
            "answer": final_answer
        }

    # 2) Подготовить SQL к выполнению
    sql_text_raw = _strip_code_fences(resp["text"])
    try:
        sql_text_expanded = expand_metric_placeholders(sql_text_raw, ATOMIC_METRICS_RU, DERIVED_METRICS_RU)
    except Exception as e:
        final_answer = f"Не удалось подготовить SQL: {e}"
        return {
            "mode": "prep_error",
            "success": "0",
            "answer": final_answer,
            "sql_text_raw": sql_text_raw
        }

    # 3) Выполнить SQL по данным
    con = duckdb.connect(database=":memory:")
    con.register('hr_facts', df_global)
    try:
        result_df = con.execute(sql_text_expanded).fetchdf()
    except Exception as e:
        final_answer = f"Не удалось выполнить SQL. Ошибка: {e}"
        return {
            "mode": "exec_error",
            "success": "0",
            "answer": final_answer,
            "sql_text_raw": sql_text_raw,
            "sql_text_expanded": sql_text_expanded
        }
    finally:
        try:
            con.close()
        except Exception:
            pass

    # 4) Сформировать финальный ответ через LLM (как в оригинале)
    rows_preview = json.loads(result_df.head(100).to_json(orient="records", force_ascii=False))
    payload_llm = {
        "instruction": (
            "Ответь на естественном русском языке, кратко и по делу. "
            "Обязательно учитывай четыре вещи: "
            "1) исходный вопрос пользователя, "
            "2) текст SQL-запроса, которым получены данные (до и после подстановки), "
            "3) сами полученные данные (превью и размер), "
            "4) инвентарь доступных значений/типов (inventory). "
            "Если в inventory поле «Месяц» содержит не все месяцы запрошенного периода, явно укажи фактический диапазон данных "
            "(минимальный и максимальный месяцы из inventory['Месяц']['values']) и поясни, что расчёт/агрегация сделаны только по этим месяцам. "
            "Ничего не выдумывай, не добавляй несуществующие периоды/значения. "
            "Если уместно, добавь проценты с двумя знаками после запятой и единицы измерения. "
            "Если данных недостаточно для точного ответа, чётко скажи, чего не хватает."
        ),
        "question": user_text,
        "sql_text_raw": sql_text_raw,
        "sql_text_expanded": sql_text_expanded,
        "columns": list(map(str, result_df.columns)),
        "rows_preview": rows_preview,
        "rows_count": int(len(result_df)),
        "inventory": inventory_global
    }

    followup_messages = [
        {
            "role": "system",
            "content": (
                "Ты аналитик по HR-данным. Пиши ясно и кратко. "
                "Строго опирайся на переданные поля payload: question, sql_text_raw, sql_text_expanded, "
                "columns, rows_preview, rows_count, inventory. "
                "Проверь покрытие по времени: если пользователь просил год/период, а в inventory['Месяц']['values'] "
                "присутствует только часть месяцев, обязательно сообщи фактический диапазон по месяцам и ограничение данных. "
                "Обязательно говори о том, какую конкретно метрику ты рассчитал, чтобы выдать ответ. Пиши человеческим приветливым языком без упоминаний технических тонкостей."
            )
        },
        {"role": "user", "content": json.dumps(payload_llm, ensure_ascii=False)}
    ]

    try:
        final_answer = openrouter_chat(followup_messages, model=MODEL)
    except Exception as e:
        final_answer = f"Не удалось получить финальный ответ от LLM. Ошибка: {e}"


    return {
        "mode": "ok",
        "success": "1",
        "answer": final_answer,
        "sql_text_raw": sql_text_raw,
        "sql_text_expanded": sql_text_expanded,
        "rows_count": int(len(result_df)),
        "rows_preview": rows_preview
    }
