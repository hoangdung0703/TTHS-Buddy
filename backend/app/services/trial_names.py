"""Code-assigned names for every person in a mock-trial case (design doc Mục 3.2, 5.4).

The model never writes a name: it writes placeholders ("{BI_CAO}") and this module fills them from
fixed pools of common Vietnamese surnames, middle and given names. Combinations are drawn with a
seeded RNG, so a case's names are reproducible from its seed.

Names found in the sample judgment (data/private/, gitignored) are excluded. Only their SHA-256
hashes are stored there - by data/private/build_style_card.py - so neither the repo nor this
module ever contains them. The file is optional: without it (production, CI) no exclusion
applies, which is acceptable because the pools hold generic full names only.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.models.trial import Participant

_REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_NAME_HASHES_PATH = _REPO_ROOT / "data" / "private" / "sample_name_hashes.json"

SURNAMES = ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi",
            "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Trịnh", "Mai", "Tạ")
MIDDLE_NAMES = {"nam": ("Văn", "Hữu", "Đức", "Minh", "Quốc", "Thành", "Công", "Xuân"),
                "nu": ("Thị", "Ngọc", "Thu", "Thanh", "Mỹ", "Kim", "Phương", "Hồng")}
GIVEN_NAMES = {"nam": ("An", "Bình", "Cường", "Dũng", "Hải", "Hùng", "Khoa", "Long", "Nam", "Phúc",
                       "Quân", "Sơn", "Tâm", "Thắng", "Tuấn", "Việt"),
               "nu": ("Anh", "Chi", "Dung", "Hà", "Hạnh", "Hoa", "Lan", "Linh", "Mai", "Nga", "Oanh",
                      "Phượng", "Thảo", "Trang", "Uyên", "Yến")}

# Court-side people the model never describes; their gender is drawn here.
COURT_ROLES: dict[str, str] = {
    "CHU_TOA": "Thẩm phán - Chủ tọa phiên tòa",
    "HOI_THAM_1": "Hội thẩm nhân dân",
    "HOI_THAM_2": "Hội thẩm nhân dân",
    "THU_KY": "Thư ký phiên tòa",
    "KSV": "Kiểm sát viên",
    "LUAT_SU": "Luật sư bào chữa cho bị cáo",
}

# Surname + capitalised word: what an invented personal name looks like in generated text. Used
# by the case validator to reject a draft that wrote a name instead of a placeholder.
NAME_LIKE_PATTERN = re.compile(
    r"\b(?:" + "|".join(SURNAMES) + r")\s+[A-ZĐÂĂÊÔƠƯÁÀẢÃẠÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÚÙỦŨỤÝỲỶỸỴ][a-zà-ỹđ]+"
)


# Lay participants: shown abbreviated in the case-file panel (trial_anonymise.py). Their short
# forms must differ within a case, so assign_names keeps them apart.
ANONYMISED_ID_PREFIXES = ("BI_CAO", "BI_HAI", "NLC_", "NLQ")


def is_anonymised(person_id: str) -> bool:
    return person_id.startswith(ANONYMISED_ID_PREFIXES)


def short_name(full: str) -> str:
    """Surname + middle names + initial of the given name: "Trần Đức Hùng" -> "Trần Đức H"."""
    tokens = unicodedata.normalize("NFC", full).split()
    if not tokens:
        return full
    return " ".join([*tokens[:-1], tokens[-1][0]])


def normalise_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFC", name).split()).casefold()


def name_hash(name: str) -> str:
    return hashlib.sha256(normalise_name(name).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _excluded_hashes() -> frozenset[str]:
    try:
        return frozenset(json.loads(SAMPLE_NAME_HASHES_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return frozenset()


def assign_names(people: list[tuple[str, str, str]], seed: int,
                 excluded: frozenset[str] | None = None) -> dict[str, Participant]:
    """`people` = [(id, role label, gender)]. Returns id -> Participant with a unique full name
    no two people share a given name, no two anonymised people share a short form, and none whose
    hash is in the exclusion set."""
    rng = random.Random(seed)
    blocked = _excluded_hashes() if excluded is None else excluded
    used_given: set[str] = set()
    used_short: set[str] = set()
    result: dict[str, Participant] = {}
    for person_id, role, gender in people:
        anonymised = is_anonymised(person_id)
        for _ in range(500):
            given = rng.choice(GIVEN_NAMES[gender])
            full = f"{rng.choice(SURNAMES)} {rng.choice(MIDDLE_NAMES[gender])} {given}"
            if (given not in used_given and name_hash(full) not in blocked
                    and not (anonymised and short_name(full) in used_short)):
                break
        else:  # pragma: no cover - pools are far larger than any case
            raise RuntimeError("Name pool exhausted")
        used_given.add(given)
        if anonymised:
            used_short.add(short_name(full))
        result[person_id] = Participant(id=person_id, role=role, name=full, gender=gender)
    return result


_PLACEHOLDER = re.compile(r"\{([A-Z_0-9]+)\}")


def placeholders_in(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def render(text: str, participants: dict[str, Participant]) -> str:
    return _PLACEHOLDER.sub(lambda m: participants[m.group(1)].name if m.group(1) in participants
                            else m.group(0), text)
