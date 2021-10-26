from typing import TypeVar, Iterable, Callable, Union, Sequence, List, Dict, Any, MutableMapping

T = TypeVar("T")


def _first_last_pred_default(item) -> bool:
    return item is True


def last(
        iterable: Iterable[T],
        pred: Callable[[T], bool] = _first_last_pred_default,
        index: bool = False) -> Union[int, T, None]:
    match = None
    imatch = -1

    for i, it in enumerate(iterable):
        if pred(it):
            match, imatch = it, i

    if index:
        return imatch
    return match


def first(
        iterable: Iterable[T],
        pred: Callable[[T], bool] =
        _first_last_pred_default, index: bool = False) -> Union[int, T, None]:
    for i, it in enumerate(iterable):
        if pred(it):
            if index:
                return i
            return it
    return -1


def startswith(seq: Sequence[T], prefix: Sequence[T]) -> bool:
    if len(seq) < len(prefix):
        return False

    it = iter(seq)
    for i in prefix:
        if i != next(it):
            return False
    return True


def insert_or_append(l: List[T], index: int, item: T) -> None:
    if index >= len(l):
        l.append(item)
    else:
        l.insert(index, item)


def nested_dict_del(nd: Dict[str, Any], path: Sequence[str]):
    r = nd
    for p in path[:-1]:
        rp = r.get(p)
        if rp is None:
            rp = r[p] = {}
        elif not isinstance(rp, MutableMapping):
            raise ValueError(f"path {path} pass through a terminal {p}")
        r = rp

    if r:
        del r[path[-1]]

def nested_dict_set(nd: Dict[str, Any], path: Sequence[str], value: Any):
    r = nd
    for p in path[:-1]:
        rp = r.get(p)
        if rp is None:
            rp = r[p] = {}
        elif not isinstance(rp, MutableMapping):
            raise ValueError(f"path {path} pass through a terminal {p}")
        r = rp

    r[path[-1]] = value

def nested_dict_get(nd: Dict[str, Any], path: Sequence[str]) -> Any:
    r = nd
    for p in path[:-1]:
        rp = r.get(p)
        if rp is None:
            return None
        elif not isinstance(rp, MutableMapping):
            raise ValueError(f"path {path} pass through a terminal {p}")
        r = rp

    return r[path[-1]]
