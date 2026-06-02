from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pdfplumber
from flask import current_app

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment, DiagnosticImportBatch, DiagnosticImportIssue, DiagnosticKesResult, DiagnosticResult, DiagnosticSession, DiagnosticStudentCode, DiagnosticTaskResult, SchoolClass


LEVEL_WORDS = ["Высокий", "Повышенный", "Базовый", "Низкий", "Ниже базового"]
SKIP_NAMES = ("__MACOSX", ".DS_Store")
CODE_RE = re.compile(r"0547\s*-\s*\d{4}")
DATE_RE = re.compile(r"(\d{2}[.-]\d{2}[.-]\d{4})")
CLASS_RE = re.compile(r"Класс:\s*([0-9]+[-– ]?[А-ЯA-ZЁ]{1,4}|[0-9]+[А-ЯA-ZЁ]{1,4})")
SUBJECT_RE = re.compile(r"Предмет:\s*([^\n]+?)(?:\s+Округ:|\s+Школа:|$)")


@dataclass
class ParsedDocument:
    doc_type: str
    filename: str
    text: str
    meta: dict = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)


@dataclass
class PreviewRow:
    row_type: str
    full_name: str | None = None
    class_name: str | None = None
    list_number: int | None = None
    participant_code: str | None = None
    total_score: float | None = None
    percent: float | None = None
    mark: str | None = None
    level: str | None = None
    variant: str | None = None
    source_kind: str = "main"
    tasks: list[dict] = field(default_factory=list)
    matched_child_id: int | None = None
    matched_class_id: int | None = None
    conflict_result_id: int | None = None
    recommended_action: str = "import"
    message: str | None = None


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def normalize_class_name(value: str | None) -> str | None:
    if not value:
        return None
    value = _normalize_spaces(value).upper().replace("КЛАСС", "").strip()
    value = value.replace("–", "-")
    value = value.replace(" ", "")
    if "-" in value:
        left, right = value.split("-", 1)
        return f"{left}{right}"
    return value


def normalize_fio(value: str | None) -> str:
    value = _normalize_spaces(value or "")
    repl = {
        "Ё": "Е",
        "ѐ": "е",
        "ё": "е",
    }
    for a, b in repl.items():
        value = value.replace(a, b)
    return value.upper()


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_doc_text(value: str) -> str:
    return _normalize_spaces((value or "").replace("\u00ad", " ")).upper()


def _decode_zip_name(name: str) -> str:
    value = name or ""
    try:
        fixed = value.encode("cp437").decode("cp866")
        if fixed:
            value = fixed
    except Exception:
        pass
    return value.replace("\\", "/")


def _is_pdf_doc_type(doc_type: str) -> bool:
    return doc_type in {
        "fg_result",
        "ekr_result",
        "mcko_result",
        "participant_codes",
        "workplaces",
        "ekr_codes",
    }


def extract_pdf_text(data: bytes) -> str:
    chunks = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def iter_zip_pdfs(file_storage) -> Iterable[tuple[str, bytes]]:
    raw = file_storage.read()
    file_storage.stream.seek(0)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            name = _decode_zip_name(info.filename)
            lower = name.lower()
            parts = [part for part in Path(name).parts if part]
            if any(part in SKIP_NAMES for part in parts):
                continue
            if any(part.startswith("._") for part in parts):
                continue
            if info.is_dir():
                continue
            if not lower.endswith(".pdf"):
                continue
            yield Path(name).name, zf.read(info)


def detect_doc_type(text: str) -> str:
    head = _normalize_doc_text((text or "")[:5000])
    if not head:
        return "unknown"

    if "СПИСОК КОДОВ ЕКР" in head:
        return "ekr_codes"
    if "КОДЫ УЧАСТНИКОВ" in head or "КОД УЧАСТНИКА" in head:
        return "participant_codes"
    if "ЛИСТ ФИКСАЦИИ РАБОЧИХ МЕСТ" in head:
        return "workplaces"
    if "ФУНКЦИОНАЛЬНОЙ ГРАМОТНОСТ" in head and "РЕЗУЛЬТАТ" in head:
        return "fg_result"
    if "ЕДИНОЙ КОНТРОЛЬНОЙ РАБОТЫ" in head and "РЕЗУЛЬТАТ" in head:
        return "ekr_result"
    if "РЕЗУЛЬТАТЫ ПРОВЕРОЧНОЙ РАБОТЫ" in head or "РЕЗУЛЬТАТЫ ДИАГНОСТИЧЕСКОЙ РАБОТЫ" in head:
        return "mcko_result"
    if "ДИАГНОСТИЧЕСКОЙ РАБОТЫ" in head and "ФАМИЛИЯ, ИМЯ" in head and "БАЛЛ" in head:
        return "mcko_result"
    if "ПРОВЕРОЧНОЙ РАБОТЫ" in head and "ФАМИЛИЯ, ИМЯ" in head and "БАЛЛ" in head:
        return "mcko_result"
    if "ФУНКЦИОНАЛЬНОЙ ГРАМОТНОСТ" in head and "ФАМИЛИЯ, ИМЯ" in head and "%" in head:
        return "fg_result"
    return "unknown"


def parse_date(text: str):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    token = m.group(1).replace("-", ".")
    try:
        return datetime.strptime(token, "%d.%m.%Y").date()
    except Exception:
        return None


def extract_header_meta(text: str) -> dict:
    meta = {}
    if m := SUBJECT_RE.search(text or ""):
        meta["subject"] = _normalize_spaces(m.group(1))
    if m := CLASS_RE.search(text or ""):
        meta["class_name"] = normalize_class_name(m.group(1))
    meta["date"] = parse_date(text)
    return meta


def extract_result_task_headers(text: str) -> list[str]:
    for line in (text or "").splitlines():
        line = _normalize_spaces(line)
        if "Фамилия, имя" not in line or "Балл" not in line:
            continue
        line = line.replace("Код диагн.", "Код диагн ")
        match = re.search(r"Фамилия,\s*имя\s+№\s*уч\.\s+Вариант\s+(?:Код\s+диагн\.?\s+)?(.+?)\s+Балл\s+%\s*вып", line, flags=re.IGNORECASE)
        if match:
            tokens = re.findall(r"\S+", match.group(1))
            if tokens:
                return tokens
    return []


def parse_codes_text(text: str, source_type: str) -> ParsedDocument:
    meta = extract_header_meta(text)
    rows = []
    for line in text.splitlines():
        line = _normalize_spaces(line)
        if not line:
            continue
        if source_type == "participant_codes":
            m = re.match(r"^(\d+)\s+(.+?)\s+([0-9]+[-–]?[А-ЯA-ZЁ]{1,4})\s+.+?\s+(0547\s*-\s*\d{4})$", line)
            if m:
                rows.append({
                    "list_number": int(m.group(1)),
                    "full_name": m.group(2).title(),
                    "class_name": normalize_class_name(m.group(3)),
                    "participant_code": m.group(4).replace(" ", ""),
                    "source_type": source_type,
                })
        elif source_type == "workplaces":
            m = re.match(r"^(\d+)\s+(.+?)\s+([0-9]+[-–]?[А-ЯA-ZЁ]{1,4})\s+(0547\s*-\s*\d{4})", line)
            if m:
                rows.append({
                    "list_number": int(m.group(1)),
                    "full_name": m.group(2).title(),
                    "class_name": normalize_class_name(m.group(3)),
                    "participant_code": m.group(4).replace(" ", ""),
                    "source_type": source_type,
                })
        elif source_type == "ekr_codes":
            m = re.match(r"^(.+?)\s+(\d+)$", line)
            if m and not line.startswith("ФИО"):
                rows.append({
                    "full_name": m.group(1).title(),
                    "list_number": int(m.group(2)),
                    "class_name": meta.get("class_name"),
                    "source_type": source_type,
                })
    return ParsedDocument(source_type, "", text, meta, rows)


def parse_result_text(text: str, doc_type: str) -> ParsedDocument:
    meta = extract_header_meta(text)
    meta["result_task_headers"] = extract_result_task_headers(text)
    meta["task_meta_by_variant"] = _parse_task_meta_by_variant(text)
    meta["kes_rows"] = _parse_kes_rows(text, meta.get("class_name"))
    rows = []
    lines = [_normalize_spaces(x) for x in text.splitlines()]
    capture = False
    for line in lines:
        if not line:
            continue
        if line.startswith("Фамилия, имя"):
            capture = True
            continue
        if capture and (line.startswith("Число учащихся:") or line.startswith("Среднее:") or line.startswith("Результаты по заданиям") or line.startswith("Анализ выполнения заданий") or line.startswith("Структура знаний")):
            break
        if not capture:
            continue
        if not re.match(r"^\d+\s+", line):
            continue
        tokens = line.split()
        if doc_type == "fg_result":
            rows.append(_parse_fg_result_row(tokens, meta))
        elif doc_type in {"mcko_result", "ekr_result"}:
            rows.append(_parse_regular_result_row(tokens, meta, doc_type, line))
    rows = [r for r in rows if r]
    return ParsedDocument(doc_type, "", text, meta, rows)


def _parse_fg_result_row(tokens: list[str], meta: dict) -> dict | None:
    if len(tokens) < 8:
        return None
    first_pct_idx = next((i for i, tok in enumerate(tokens) if tok.endswith("%")), None)
    if first_pct_idx is None or first_pct_idx < 6:
        return None
    tail_text = " ".join(tokens[-4:]).strip().lower()
    level = next((w for w in LEVEL_WORDS if w.lower() in tail_text), None)
    total_score = _to_float(tokens[first_pct_idx - 1])
    percent = _to_float(tokens[first_pct_idx].replace("%", ""))
    task_tokens = tokens[4:first_pct_idx - 1]
    task_rows = [{"task_number": str(i + 1), "raw_value": val} for i, val in enumerate(task_tokens)]
    return {
        "list_number": _to_int(tokens[0]),
        "participant_code": _normalize_code(tokens[1]),
        "variant": tokens[2],
        "total_score": total_score,
        "percent": percent,
        "mark": None,
        "level": level,
        "class_name": meta.get("class_name"),
        "tasks": task_rows,
    }


def _parse_regular_result_row(tokens: list[str], meta: dict, doc_type: str, raw_line: str) -> dict | None:
    task_headers = list(meta.get("result_task_headers") or [])
    if len(tokens) < 5:
        return None
    has_code = any(CODE_RE.fullmatch(tok.replace(" ", "")) for tok in tokens)
    code_token = next((tok for tok in tokens if CODE_RE.fullmatch(tok.replace(" ", ""))), None)
    if has_code:
        code_idx = tokens.index(code_token)
        if len(tokens) < code_idx + 4:
            return None
        total_score = _to_float(tokens[-3])
        percent = _to_float(tokens[-2].replace("%", ""))
        mark = tokens[-1]
        task_tokens = tokens[code_idx + 1:-3]
        return {
            "list_number": _to_int(tokens[0]),
            "variant": tokens[1] if code_idx >= 2 else None,
            "participant_code": _normalize_code(code_token),
            "total_score": total_score,
            "percent": percent,
            "mark": mark,
            "level": None,
            "class_name": meta.get("class_name"),
            "tasks": [{"task_number": str(task_headers[i]) if i < len(task_headers) else str(i + 1), "raw_value": val} for i, val in enumerate(task_tokens)],
        }
    # EKR without participant code
    total_score = _to_float(tokens[-2])
    percent = _to_float(tokens[-1].replace("%", ""))
    variant = tokens[1] if len(tokens) > 3 else None
    task_tokens = tokens[2:-2]
    return {
        "list_number": _to_int(tokens[0]),
        "variant": variant,
        "participant_code": None,
        "total_score": total_score,
        "percent": percent,
        "mark": None,
        "level": None,
        "class_name": meta.get("class_name"),
        "tasks": [{"task_number": str(task_headers[i]) if i < len(task_headers) else str(i + 1), "raw_value": val} for i, val in enumerate(task_tokens)],
    }




def _strip_inline_result_tail(text: str) -> str:
    value = _normalize_spaces(text)
    patterns = [
        r"\s+(?:\d+|N|N-)(?:\s+(?:\d+|N|N-))*\s+\d+\s*балл\s*-\s*\d+%",
        r"\s+(?:\d+|N|N-)(?:\s+(?:\d+|N|N-))*\s+\d+\s*балла\s*-\s*\d+%",
        r"\s+\d+\s*балл\s*-\s*\d+%",
        r"\s+\d+\s*балла\s*-\s*\d+%",
    ]
    cut = len(value)
    for pattern in patterns:
        m = re.search(pattern, value, flags=re.IGNORECASE)
        if m:
            cut = min(cut, m.start())
    if cut != len(value):
        value = value[:cut]
    return _normalize_spaces(value).strip(" -—")


def _cleanup_task_skill_text(text: str) -> str:
    value = _normalize_spaces(text)
    value = re.sub(r"^Проверяемое\s+(?:знание/умение|умение)\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d+(?:\.[A-Za-zА-Яа-я0-9]+)*\s+", "", value)
    value = re.sub(r"^\d+\s+", "", value)
    value = _strip_inline_result_tail(value)
    value = re.sub(r"\s+(?:(?:\d+|N|N-)\s+)+(?:\d+\s*балл|\d+\s*балла).*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+Класс\s+Вся\s+выборка.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -—")



def _parse_task_meta_by_variant(text: str) -> dict:
    lines = [_normalize_spaces(x) for x in (text or "").splitlines()]
    current_variant = None
    current_task_num = None
    current_task_lines: list[str] = []
    task_map: dict[str, dict[str, dict[str, str]]] = {}

    task_num_re = re.compile(r"^(\d+(?:\.[A-Za-zА-Яа-я0-9]+)*)\s+(.*)$")
    only_values_re = re.compile(r"^(?:\d+|N|N-)(?:\s+(?:\d+|N|N-))*$")
    score_line_re = re.compile(r"^\d+\s*балл\s*-|^\d+\s*балла\s*-", flags=re.IGNORECASE)
    task_with_level_re = re.compile(r"^(\d+(?:\.[A-Za-zА-Яа-я0-9]+)*)\s+([0-9]+)\s+(.+)$")

    def flush_current():
        nonlocal current_task_num, current_task_lines
        if not current_variant or not current_task_num:
            current_task_num = None
            current_task_lines = []
            return
        skill = _cleanup_task_skill_text(" ".join(current_task_lines))
        if skill:
            task_map.setdefault(current_variant, {})[str(current_task_num)] = {"skill": skill}
        current_task_num = None
        current_task_lines = []

    for line in lines:
        if not line:
            continue
        if line.startswith("Вариант:"):
            flush_current()
            current_variant = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Структура знаний") or line.startswith("Структура овладения") or line.startswith("Код КЭС") or line.startswith("Код УУД") or line.startswith("Средний % выполнения"):
            flush_current()
            current_variant = None
            continue
        if not current_variant:
            continue
        if line.startswith("Номер") or line.startswith("номер учащегося") or line.startswith("Проверяемое знание/умение") or line.startswith("Проверяемое умение") or line.startswith("Результаты выполнения заданий") or line.startswith("Класс Вся выборка") or line in {"Класс", "Все", "Класс Все", "(город)", "задания", "задани", "я"}:
            continue
        if only_values_re.fullmatch(line):
            continue
        if score_line_re.search(line):
            if current_task_num:
                cleaned = _strip_inline_result_tail(line)
                if cleaned:
                    current_task_lines.append(cleaned)
            continue

        m = task_with_level_re.match(line)
        if m and m.group(2).isdigit():
            flush_current()
            current_task_num = m.group(1)
            cleaned = _strip_inline_result_tail(m.group(3))
            current_task_lines = [cleaned] if cleaned else []
            continue

        m = task_num_re.match(line)
        if m:
            rest = m.group(2)
            if not re.match(r"^(?:балл|балла|%|Класс|Вся выборка)\b", rest, flags=re.IGNORECASE):
                flush_current()
                current_task_num = m.group(1)
                cleaned = _strip_inline_result_tail(rest)
                current_task_lines = [cleaned] if cleaned else []
                continue

        if current_task_num:
            cleaned = _strip_inline_result_tail(line)
            if cleaned:
                current_task_lines.append(cleaned)

    flush_current()
    return task_map


def _parse_kes_rows(text: str, class_name: str | None = None) -> list[dict]:
    lines = [_normalize_spaces(x) for x in (text or "").splitlines()]
    rows: list[dict] = []
    in_section = False
    current = None

    def flush_current():
        nonlocal current
        if not current:
            return
        buf = _normalize_spaces(current["text"])
        m = re.match(r"^(.*?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)$", buf)
        if m:
            rows.append({
                "class_name": class_name,
                "kes_code": current["code"],
                "kes_name": m.group(1).strip(),
                "class_percent": _to_float(m.group(2)),
                "city_percent": _to_float(m.group(3)),
            })
        current = None

    for line in lines:
        if not line:
            continue
        if line.startswith("Код КЭС") or line.startswith("Код УУД"):
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("Средний % выполнения") or line.startswith("Средний % выполнения теста") or line.startswith("Средний % выполнения диагн. работы") or line.startswith("Powered by") or line.startswith("www.mcko.ru"):
            flush_current()
            break
        if line in {"Класс", "Все", "Класс (%)", "Все (%)", "Код", "КЭС", "УУД"} or line.startswith("% выполнения заданий"):
            continue
        m = re.match(r"^(\d+(?:\.\d+)+)\s+(.+)$", line)
        if m:
            flush_current()
            current = {"code": m.group(1), "text": m.group(2)}
            if re.search(r"\d+(?:[.,]\d+)?\s+\d+(?:[.,]\d+)?$", current["text"]):
                flush_current()
            continue
        if current:
            current["text"] = f"{current['text']} {line}"
            if re.search(r"\d+(?:[.,]\d+)?\s+\d+(?:[.,]\d+)?$", current["text"]):
                flush_current()
    return rows


def _to_float(value):
    try:
        return float(str(value).replace(",", ".").replace("%", ""))
    except Exception:
        return None


def _to_int(value):
    try:
        return int(str(value))
    except Exception:
        return None


def _normalize_code(value: str | None) -> str | None:
    if not value:
        return None
    value = value.replace(" ", "")
    value = value.replace("–", "-")
    return value


def build_preview(result_zip, codes_zip=None, reserve=False, session_id=None) -> dict:
    docs: list[ParsedDocument] = []
    issues = []
    file_names = []
    for name, data in iter_zip_pdfs(result_zip):
        file_names.append(name)
        text = extract_pdf_text(data)
        doc_type = detect_doc_type(text)
        parsed = parse_result_text(text, doc_type) if doc_type.endswith("_result") else ParsedDocument(doc_type, name, text, extract_header_meta(text), [])
        if doc_type == "unknown":
            current_app.logger.warning("Unknown diagnostic PDF: %s | head=%r", name, _normalize_spaces(text[:500]))
        parsed.filename = name
        docs.append(parsed)
        if doc_type == "unknown":
            issues.append({"type": "unknown_pdf", "message": f"Не определён тип документа: {name}"})

    code_rows = []
    if codes_zip:
        for name, data in iter_zip_pdfs(codes_zip):
            text = extract_pdf_text(data)
            doc_type = detect_doc_type(text)
            if doc_type == "unknown":
                current_app.logger.warning("Unknown codes PDF: %s | head=%r", name, _normalize_spaces(text[:500]))
            if doc_type in {"participant_codes", "workplaces", "ekr_codes"}:
                parsed = parse_codes_text(text, doc_type)
                parsed.filename = name
                docs.append(parsed)
                code_rows.extend(parsed.rows)

    preview_rows: list[PreviewRow] = []
    code_lookup_by_key = {}
    code_lookup_by_code = {}
    for row in code_rows:
        key = (normalize_class_name(row.get("class_name")), row.get("list_number"))
        if row.get("list_number"):
            code_lookup_by_key[key] = row
        if row.get("participant_code"):
            code_lookup_by_code[_normalize_code(row.get("participant_code"))] = row

    for doc in docs:
        if not doc.doc_type.endswith("_result"):
            continue
        for row in doc.rows:
            full_name = None
            class_name = normalize_class_name(row.get("class_name") or doc.meta.get("class_name"))
            participant_code = _normalize_code(row.get("participant_code"))
            list_number = row.get("list_number")
            if participant_code and participant_code in code_lookup_by_code:
                code_row = code_lookup_by_code[participant_code]
                full_name = code_row.get("full_name")
                class_name = normalize_class_name(code_row.get("class_name") or class_name)
            elif list_number and (class_name, list_number) in code_lookup_by_key:
                code_row = code_lookup_by_key[(class_name, list_number)]
                full_name = code_row.get("full_name")
                participant_code = participant_code or code_row.get("participant_code")
            task_variant_map = doc.meta.get("task_meta_by_variant") or {}
            task_meta = task_variant_map.get(str(row.get("variant") or "").strip(), {})
            enriched_tasks = []
            for task in (row.get("tasks") or []):
                extra = task_meta.get(str(task.get("task_number") or "").strip(), {})
                enriched_task = dict(task)
                if extra.get("skill"):
                    enriched_task["skill"] = extra.get("skill")
                enriched_tasks.append(enriched_task)
            p = PreviewRow(
                row_type="result",
                full_name=full_name,
                class_name=class_name,
                list_number=list_number,
                participant_code=participant_code,
                total_score=row.get("total_score"),
                percent=row.get("percent"),
                mark=row.get("mark"),
                level=row.get("level"),
                variant=row.get("variant"),
                source_kind="reserve" if reserve else "main",
                tasks=enriched_tasks,
            )
            match_preview_row(p, session_id=session_id)
            preview_rows.append(p)

    kes_rows = []
    for doc in docs:
        if doc.meta.get("kes_rows"):
            kes_rows.extend(doc.meta.get("kes_rows") or [])

    digest = hashlib.sha256(("|".join(sorted(file_names))).encode("utf-8", "ignore")).hexdigest()
    return {
        "rows": [row.__dict__ for row in preview_rows],
        "issues": issues,
        "kes_rows": kes_rows,
        "source_kind": "reserve" if reserve else "main",
        "file_hash": digest,
    }


def match_preview_row(row: PreviewRow, session_id=None):
    child_id = None
    class_id = None
    if row.participant_code and session_id:
        code_link = DiagnosticStudentCode.query.filter_by(session_id=session_id, participant_code=row.participant_code).first()
        if code_link:
            child_id = code_link.child_id
            class_id = code_link.school_class_id
    if not child_id and row.full_name:
        child_id, class_id = find_child_by_name(row.full_name, row.class_name)
    row.matched_child_id = child_id
    row.matched_class_id = class_id
    if not child_id:
        row.recommended_action = "skip"
        row.message = "Не найден ученик в базе"
    if session_id and (child_id or row.participant_code or row.list_number):
        existing = find_existing_result(session_id, child_id, row.participant_code, row.list_number)
        if existing:
            row.conflict_result_id = existing.id
            row.recommended_action = "replace" if row.source_kind == "reserve" and (existing.mark == "2" or existing.mark == 2) else "keep_existing"
            row.message = f"Уже есть результат: балл {existing.total_score}, % {existing.percent}"


def find_existing_result(session_id, child_id, participant_code, list_number):
    q = DiagnosticResult.query.filter_by(session_id=session_id, is_final=True)
    if child_id:
        found = q.filter_by(child_id=child_id).first()
        if found:
            return found
    if participant_code:
        found = q.filter_by(participant_code=participant_code).first()
        if found:
            return found
    if list_number:
        return q.filter_by(list_number=list_number).first()
    return None


def find_child_by_name(full_name: str, class_name: str | None):
    target = normalize_fio(full_name)
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    q = Child.query
    candidates = []
    for child in q.limit(5000).all():
        fio = normalize_fio(getattr(child, "fio", None) or f"{child.last_name} {child.first_name} {child.middle_name or ''}")
        if fio == target:
            candidates.append(child)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        child = candidates[0]
        class_id = _active_class_id_for_child(child.id, current_year.id if current_year else None, class_name)
        return child.id, class_id
    for child in candidates:
        class_id = _active_class_id_for_child(child.id, current_year.id if current_year else None, class_name)
        if class_id:
            return child.id, class_id
    return candidates[0].id, None


def _active_class_id_for_child(child_id: int, academic_year_id: int | None, class_name: str | None):
    q = ChildEnrollment.query.filter_by(child_id=child_id, status="ACTIVE")
    if academic_year_id:
        q = q.filter_by(academic_year_id=academic_year_id)
    enrollments = q.all()
    if not enrollments:
        return None
    if class_name:
        nclass = normalize_class_name(class_name)
        for enr in enrollments:
            if enr.school_class and normalize_class_name(enr.school_class.name) == nclass:
                return enr.school_class_id
    return enrollments[0].school_class_id


def save_preview(preview: dict) -> str:
    preview_id = hashlib.sha256(json.dumps(preview, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    preview_dir = Path(current_app.instance_path) / "diagnostics_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / f"{preview_id}.json").write_text(json.dumps(preview, ensure_ascii=False), encoding="utf-8")
    return preview_id


def load_preview(preview_id: str) -> dict:
    preview_dir = Path(current_app.instance_path) / "diagnostics_previews"
    path = preview_dir / f"{preview_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def apply_preview(session: DiagnosticSession, preview: dict, actions: dict[str, str], filename: str, created_by=None):
    batch = DiagnosticImportBatch(
        session_id=session.id,
        import_kind=preview.get("source_kind") or "main",
        filename=filename,
        file_hash=preview.get("file_hash"),
        status="processed",
        created_by=created_by,
    )
    db.session.add(batch)
    db.session.flush()

    for row in preview.get("rows", []):
        action = actions.get(_row_key(row), row.get("recommended_action") or "import")
        if action == "skip":
            db.session.add(DiagnosticImportIssue(
                session_id=session.id,
                import_batch_id=batch.id,
                issue_type="skipped_row",
                message=f"Пропущена запись: {row.get('full_name') or row.get('participant_code') or row.get('list_number')}",
                payload_json=json.dumps(row, ensure_ascii=False),
            ))
            continue

        existing = None
        if row.get("conflict_result_id"):
            existing = DiagnosticResult.query.get(row["conflict_result_id"])

        if existing and action == "keep_existing":
            _store_nonfinal_copy(session.id, batch.id, row, created_by, final=False)
            continue

        if existing and action == "replace":
            existing.is_final = False
            _store_nonfinal_copy(session.id, batch.id, row, created_by, final=True, replaced_result_id=existing.id)
            continue

        if existing and action == "store_both":
            _store_nonfinal_copy(session.id, batch.id, row, created_by, final=False)
            continue

        _store_nonfinal_copy(session.id, batch.id, row, created_by, final=True)

        if row.get("participant_code") or row.get("list_number"):
            existing_code = DiagnosticStudentCode.query.filter_by(
                session_id=session.id,
                participant_code=row.get("participant_code"),
                list_number=row.get("list_number"),
            ).first()
            if not existing_code:
                db.session.add(DiagnosticStudentCode(
                    session_id=session.id,
                    child_id=row.get("matched_child_id"),
                    school_class_id=row.get("matched_class_id"),
                    full_name_raw=row.get("full_name"),
                    class_name_raw=row.get("class_name"),
                    participant_code=row.get("participant_code"),
                    list_number=row.get("list_number"),
                    source_type="import",
                ))

    DiagnosticKesResult.query.filter_by(import_batch_id=batch.id).delete(synchronize_session=False)
    for kes in preview.get("kes_rows") or []:
        db.session.add(DiagnosticKesResult(
            session_id=session.id,
            import_batch_id=batch.id,
            class_name_raw=kes.get("class_name"),
            kes_code=kes.get("kes_code"),
            kes_name=kes.get("kes_name"),
            class_percent=kes.get("class_percent"),
            city_percent=kes.get("city_percent"),
        ))

    session.status = "imported_reserve" if preview.get("source_kind") == "reserve" else "imported_main"
    db.session.commit()
    return batch


def _store_nonfinal_copy(session_id, batch_id, row, created_by=None, final=True, replaced_result_id=None):
    result = DiagnosticResult(
        session_id=session_id,
        child_id=row.get("matched_child_id"),
        school_class_id=row.get("matched_class_id"),
        import_batch_id=batch_id,
        full_name_raw=row.get("full_name"),
        class_name_raw=row.get("class_name"),
        list_number=row.get("list_number"),
        participant_code=row.get("participant_code"),
        variant=row.get("variant"),
        total_score=row.get("total_score"),
        percent=row.get("percent"),
        mark=row.get("mark"),
        level=row.get("level"),
        source_kind=row.get("source_kind") or "main",
        is_final=final,
        replaced_result_id=replaced_result_id,
    )
    db.session.add(result)
    db.session.flush()
    for task in row.get("tasks") or []:
        db.session.add(DiagnosticTaskResult(
            result_id=result.id,
            task_number=str(task.get("task_number")),
            raw_value=task.get("raw_value"),
            topic=task.get("topic"),
            skill=task.get("skill"),
            kes_code=task.get("kes_code"),
            block_name=task.get("block_name"),
        ))
    return result


def build_report(session: DiagnosticSession):
    rows = DiagnosticResult.query.filter_by(session_id=session.id, is_final=True).order_by(DiagnosticResult.class_name_raw.asc(), DiagnosticResult.full_name_raw.asc()).all()
    by_class = {}
    tasks = {}
    for row in rows:
        cls = row.class_name_raw or "Без класса"
        bucket = by_class.setdefault(cls, {"rows": [], "avg_score": 0, "avg_percent": 0})
        bucket["rows"].append(row)
        for task in row.task_results:
            tb = tasks.setdefault(task.task_number, {"count": 0, "success": 0, "raw_values": []})
            tb["count"] += 1
            raw = (task.raw_value or "").strip().upper()
            tb["raw_values"].append(raw)
            if raw and raw not in {"0", "N", "N-", "0+", "0-"}:
                tb["success"] += 1
    for cls, bucket in by_class.items():
        if bucket["rows"]:
            scores = [r.total_score for r in bucket["rows"] if r.total_score is not None]
            perc = [r.percent for r in bucket["rows"] if r.percent is not None]
            bucket["avg_score"] = round(sum(scores) / len(scores), 2) if scores else None
            bucket["avg_percent"] = round(sum(perc) / len(perc), 2) if perc else None
    task_stats = []
    for task_number, data in sorted(tasks.items(), key=lambda x: (len(x[0]), x[0])):
        success_percent = round(data["success"] * 100 / data["count"], 2) if data["count"] else None
        task_stats.append({"task_number": task_number, "success_percent": success_percent, "count": data["count"]})
    return {"rows": rows, "by_class": by_class, "task_stats": task_stats}


def _row_key(row: dict) -> str:
    return f"{row.get('participant_code') or ''}|{row.get('list_number') or ''}|{row.get('matched_child_id') or ''}|{row.get('class_name') or ''}"
