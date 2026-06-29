from __future__ import annotations

from collections.abc import Iterable


def format_hotpot_context(context: object) -> str:
    if not isinstance(context, dict):
        return str(context or "")
    titles = context.get("title") or []
    sentences = context.get("sentences") or []
    blocks: list[str] = []
    for title, sent_list in zip(titles, sentences, strict=False):
        text = " ".join(str(sentence).strip() for sentence in sent_list if str(sentence).strip())
        if text:
            blocks.append(f"[{title}] {text}")
    return "\n".join(blocks)


def _project_item(item: dict) -> dict[str, str]:
    return {
        "question": str(item["question"]),
        "answer": str(item["answer"]),
        "context": format_hotpot_context(item.get("context")),
    }


def _ensure_disjoint(train_pool: list[dict[str, str]], heldout: list[dict[str, str]]) -> None:
    train_q = {row["question"] for row in train_pool}
    held_q = {row["question"] for row in heldout}
    overlap = train_q & held_q
    if overlap:
        sample = next(iter(overlap))
        raise ValueError(f"train_pool and heldout overlap, for example: {sample!r}")
    if len(train_q) != len(train_pool):
        raise ValueError("train_pool contains duplicate questions")
    if len(held_q) != len(heldout):
        raise ValueError("heldout contains duplicate questions")


def load_hotpotqa(n_train: int, n_heldout: int, seed: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    from datasets import load_dataset

    total = n_train + n_heldout
    errors: list[Exception] = []
    for dataset_id in ("hotpot_qa", "hotpotqa/hotpot_qa"):
        try:
            ds = load_dataset(dataset_id, "distractor", split="validation")
            break
        except ValueError as exc:
            errors.append(exc)
            if "trust_remote_code" not in str(exc):
                continue
            try:
                ds = load_dataset(dataset_id, "distractor", split="validation", trust_remote_code=True)
                break
            except Exception as trusted_exc:  # noqa: BLE001
                errors.append(trusted_exc)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    else:
        raise RuntimeError(f"Unable to load HotpotQA validation split: {errors[-1]}") from errors[-1]
    ds = ds.shuffle(seed=seed).select(range(total))
    rows = [_project_item(dict(item)) for item in ds]
    train_pool = rows[:n_train]
    heldout = rows[n_train:]
    _ensure_disjoint(train_pool, heldout)
    return train_pool, heldout


def batch_without_replacement(train_pool: list[dict[str, str]], batch_size: int, t: int) -> list[dict[str, str]]:
    start = t * batch_size
    end = start + batch_size
    if end > len(train_pool):
        raise ValueError("not enough train examples for global no-replacement batches")
    return train_pool[start:end]


def gold_map(rows: Iterable[dict[str, str]]) -> dict[str, str]:
    return {row["question"]: row["answer"] for row in rows}
