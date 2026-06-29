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


def _try_load(dataset_ids: tuple[str, ...], config: str | None, split: str):
    from datasets import load_dataset

    errors: list[Exception] = []
    for dataset_id in dataset_ids:
        for trust in (False, True):
            try:
                kwargs = {"split": split}
                if trust:
                    kwargs["trust_remote_code"] = True
                if config is not None:
                    return load_dataset(dataset_id, config, **kwargs)
                return load_dataset(dataset_id, **kwargs)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
    raise RuntimeError(
        f"could not load any of {dataset_ids} (config={config}, split={split}): {errors[-1]}"
    ) from errors[-1]


def _boxed_answer(solution: str) -> str:
    """Extract the content of the last \\boxed{...} in a MATH solution (balanced braces)."""
    marker = solution.rfind("\\boxed")
    if marker == -1:
        return solution.strip().splitlines()[-1].strip() if solution.strip() else ""
    i = solution.find("{", marker)
    if i == -1:
        return ""
    depth, start = 0, i
    for j in range(i, len(solution)):
        if solution[j] == "{":
            depth += 1
        elif solution[j] == "}":
            depth -= 1
            if depth == 0:
                return solution[start + 1 : j].strip()
    return solution[start + 1 :].strip()


def _two_split_benchmark(
    train_ds, held_ds, project, n_train: int, n_heldout: int, seed: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    train_ds = train_ds.shuffle(seed=seed)
    held_ds = held_ds.shuffle(seed=seed)
    train_pool = [project(dict(x)) for x in train_ds.select(range(min(n_train, len(train_ds))))]
    heldout = [project(dict(x)) for x in held_ds.select(range(min(n_heldout, len(held_ds))))]
    _ensure_disjoint(train_pool, heldout)
    return train_pool, heldout


def load_gsm8k(n_train: int, n_heldout: int, seed: int):
    ds_train = _try_load(("gsm8k", "openai/gsm8k"), "main", "train")
    ds_test = _try_load(("gsm8k", "openai/gsm8k"), "main", "test")

    def project(item: dict) -> dict[str, str]:
        gold = str(item["answer"]).split("####")[-1].strip().replace(",", "")
        return {"question": str(item["question"]), "answer": gold, "context": ""}

    return _two_split_benchmark(ds_train, ds_test, project, n_train, n_heldout, seed)


def load_math(n_train: int, n_heldout: int, seed: int):
    ids = ("hendrycks/competition_math", "lighteval/MATH", "EleutherAI/hendrycks_math")
    ds_train = _try_load(ids, None, "train")
    ds_test = _try_load(ids, None, "test")

    def project(item: dict) -> dict[str, str]:
        return {
            "question": str(item.get("problem", item.get("question", ""))),
            "answer": _boxed_answer(str(item.get("solution", ""))),
            "context": "",
        }

    return _two_split_benchmark(ds_train, ds_test, project, n_train, n_heldout, seed)


def _load_closed_book_qa(ids: tuple[str, ...], config: str | None, n_train: int, n_heldout: int, seed: int):
    ds_train = _try_load(ids, config, "train")
    try:
        ds_held = _try_load(ids, config, "validation")
    except RuntimeError:
        ds_held = _try_load(ids, config, "dev")

    def project(item: dict) -> dict[str, str]:
        answer = item.get("answer")
        if isinstance(answer, dict):  # some schemas store {"value": ...} or {"aliases": [...]}
            answer = answer.get("value") or (answer.get("aliases") or [""])[0]
        return {"question": str(item.get("question", "")), "answer": str(answer or ""), "context": ""}

    return _two_split_benchmark(ds_train, ds_held, project, n_train, n_heldout, seed)


def load_musique(n_train: int, n_heldout: int, seed: int):
    # Closed-book; adjust the id if your environment uses a different MuSiQue mirror.
    return _load_closed_book_qa(("dgslibisey/MuSiQue", "musique"), None, n_train, n_heldout, seed)


def load_2wikimultihop(n_train: int, n_heldout: int, seed: int):
    return _load_closed_book_qa(
        ("voidful/2WikiMultihopQA", "scholarly-shadows-syndicate/2WikiMultihopQA_wikipedia"),
        None, n_train, n_heldout, seed,
    )


def load_benchmark(name: str, n_train: int, n_heldout: int, seed: int):
    """Dispatch to the right benchmark loader. Returns (train_pool, heldout)."""
    loaders = {
        "hotpotqa": load_hotpotqa,
        "gsm8k": load_gsm8k,
        "math": load_math,
        "musique": load_musique,
        "2wikimultihop": load_2wikimultihop,
    }
    if name not in loaders:
        raise ValueError(f"unknown dataset {name!r}; choose from {sorted(loaders)}")
    return loaders[name](n_train, n_heldout, seed)


def batch_without_replacement(train_pool: list[dict[str, str]], batch_size: int, t: int) -> list[dict[str, str]]:
    start = t * batch_size
    end = start + batch_size
    if end > len(train_pool):
        raise ValueError("not enough train examples for global no-replacement batches")
    return train_pool[start:end]


def gold_map(rows: Iterable[dict[str, str]]) -> dict[str, str]:
    return {row["question"]: row["answer"] for row in rows}
