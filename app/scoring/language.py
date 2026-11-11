"""Language checks for user-facing feedback; English source quotes stay intact."""

import re
from collections.abc import Iterable


def require_chinese_feedback(texts: Iterable[str]) -> None:
    """Reject untranslated explanations while allowing English terms in Chinese."""

    for text in texts:
        if not re.search(r"[\u3400-\u9fff]", text):
            raise ValueError(
                "所有评分说明、亮点和修改建议必须使用简体中文；英文原文引句除外"
            )
