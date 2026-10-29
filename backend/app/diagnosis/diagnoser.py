from __future__ import annotations

from typing import Any, Iterable, List, Sequence

from app.lexer.errors import LexicalError
from app.parser.errors import ParseDiagnostic
from app.diagnosis.rules import DiagnosisResult, DiagnosisRecord, classify_error


class Diagnoser:
    def __init__(self) -> None:
        self._rules = []

    def diagnose(self, errors: Iterable[Any]) -> DiagnosisResult:
        records: List[DiagnosisRecord] = []
        for error in errors or []:
            if error is None:
                continue
            records.append(classify_error(error))
        return DiagnosisResult(records)

    def diagnose_lexical(self, errors: Sequence[LexicalError]) -> DiagnosisResult:
        return self.diagnose(list(errors))

    def diagnose_syntax(self, errors: Sequence[ParseDiagnostic]) -> DiagnosisResult:
        return self.diagnose(list(errors))

    def diagnose_mixed(self, lexical_errors: Sequence[LexicalError], syntax_errors: Sequence[ParseDiagnostic]) -> DiagnosisResult:
        combined: List[Any] = []
        combined.extend(lexical_errors)
        combined.extend(syntax_errors)
        return self.diagnose(combined)
