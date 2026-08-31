"""
ArcherSniper - Course & College Classifier
Categorizes DLSU course codes into General Education (GE), Lasallian Core (LC),
and respective DLSU Manila colleges (CCS, RVRCOB, GCOE, CLA, COS, BAGCED, SOE).
"""

import re
from dataclasses import dataclass


@dataclass
class CourseClassification:
    course_code: str
    is_ge_lc: bool
    category_type: str  # "GE", "LC", "COLLEGE", "OTHER"
    college_code: str | None  # "CCS", "RVRCOB", "GCOE", "CLA", "COS", "BAGCED", "SOE"
    college_name: str | None
    feed_channel_key: str  # key used in server_channels table


# GE Course Codes & Prefixes
GE_EXACT_CODES = {
    "GEARTAP", "GETHICS", "GEMATHT", "GEFILI1", "GEFILI2", "GERPHIS",
    "GERZAL", "GEPCOMM", "GESTSOC", "GEUSELF", "GESPORT", "GEDANCE",
    "GEFTWEL", "GREATWY", "NSTP101", "NSTP001", "NSTP002", "LASARE1",
    "LASARE2", "LASARE3", "SAS1000", "SAS2000", "SAS3000",
}
GE_PREFIXES = (
    "GE", "NSTP", "LASARE", "SAS", "GREAT",
)

# Lasallian Core (LC) Codes & Prefixes
LC_EXACT_CODES = {
    "LCFILIA", "LCFILIB", "LCLSONE", "LCLSTWO", "LCLSTRI", "LCFAITH",
    "LCTHONE", "LCTHTWO", "LCTHTRI",
}
LC_PREFIXES = ("LC",)

# College Prefixes Mapping
COLLEGE_PREFIX_MAP: dict[str, tuple[str, list[str]]] = {
    "CCS": (
        "College of Computer Studies",
        [
            "CC", "CS", "ST", "IT", "IS", "GD", "WD", "NS", "MOB", "DAT",
            "NET", "COMP", "THS", "PRC", "ANIM", "CY",
        ],
    ),
    "RVRCOB": (
        "RVR College of Business",
        [
            "DSOM", "FIN", "MKT", "MARKET", "ACY", "COB", "MODENMA", "BUS",
            "COBLAW", "TAX", "ENTREP", "MAN", "ORG", "STRAT", "OPE",
            "CORP", "ACC", "BSA", "BSIT", "AUD", "COST", "TREAS", "LAW",
        ],
    ),
    "GCOE": (
        "Gokongwei College of Engineering",
        [
            "ENG", "MEM", "CIV", "ECE", "CHE", "IE", "MEE", "LBY",
            "CPE", "MTHENG", "ENGSTAT", "ENGPHYS", "ENGCAD", "THERM",
            "DIFF", "NUM", "ENVI", "MATERIA", "CIRC",
        ],
    ),
    "CLA": (
        "College of Liberal Arts",
        [
            "AB", "PSY", "HIS", "LIT", "PHIL", "PHL", "POL", "SOC",
            "COM", "DEV", "HUM", "INT", "MALIK", "FOR", "JAP", "CHN",
            "SPA", "FRE", "GER", "KOR", "ITL", "RUS", "THEO", "REL",
            "FIL", "WRIT",
        ],
    ),
    "COS": (
        "College of Science",
        [
            "BIO", "CHEM", "CHM", "PHY", "MTH", "SCIMAT", "ZOO", "BOT",
            "MATH", "ALG", "TRIG", "CALC", "GENB", "GENC", "GENP",
            "ANAL", "ORCH", "BIOCHEM", "ECOL",
        ],
    ),
    "BAGCED": (
        "Br. Andrew Gonzalez College of Education",
        [
            "CED", "EDM", "EDF", "ECE", "SED", "SPE", "PED", "EDUC",
            "TEA", "CUR", "CHIL", "COUN",
        ],
    ),
    "SOE": (
        "School of Economics",
        [
            "ECO", "ECON", "APECO", "MINECO", "MARECO", "QUANT",
            "DEVECO", "INTECO", "LABOR", "PUBFISC", "MONET",
        ],
    ),
}


def classify_course(course_code: str) -> CourseClassification:
    """
    Classifies a DLSU course code into GE, LC, or College category.
    """
    clean = re.sub(r"[^A-Z0-9-]", "", course_code.strip().upper())

    # 1. Check General Education (GE) - Exclude GEN (General Science e.g. GENCHEM)
    if (
        clean in GE_EXACT_CODES
        or (clean.startswith("GE") and not clean.startswith("GEN"))
        or any(clean.startswith(p) for p in ("NSTP", "LASARE", "SAS", "GREAT"))
    ):
        return CourseClassification(
            course_code=clean,
            is_ge_lc=True,
            category_type="GE",
            college_code=None,
            college_name="General Education",
            feed_channel_key="ge_lc",
        )

    # 2. Check Lasallian Core (LC)
    if clean in LC_EXACT_CODES or any(clean.startswith(p) for p in LC_PREFIXES):
        return CourseClassification(
            course_code=clean,
            is_ge_lc=True,
            category_type="LC",
            college_code=None,
            college_name="Lasallian Core",
            feed_channel_key="ge_lc",
        )

    # 3. Check College Prefix Maps
    for col_code, (col_name, prefixes) in COLLEGE_PREFIX_MAP.items():
        for prefix in prefixes:
            if clean.startswith(prefix):
                return CourseClassification(
                    course_code=clean,
                    is_ge_lc=False,
                    category_type="COLLEGE",
                    college_code=col_code,
                    college_name=col_name,
                    feed_channel_key=col_code.lower(),
                )

    # 4. Fallback for unclassified / departmental subjects
    return CourseClassification(
        course_code=clean,
        is_ge_lc=False,
        category_type="OTHER",
        college_code=None,
        college_name="DLSU Course",
        feed_channel_key="other",
    )
