from typing import Any, Dict, List, Set


def deduplicate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按 url 去重；url 缺失时按 title + source_id 去重。
    """
    deduplicated = []
    seen = set()  # type: Set[str]

    for item in items:
        url = str(item.get("url") or "")
        if url:
            key = "url:{}".format(url)
        else:
            key = "fallback:{}|{}".format(
                str(item.get("source_id") or ""), str(item.get("title") or "")
            )

        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)

    return deduplicated
