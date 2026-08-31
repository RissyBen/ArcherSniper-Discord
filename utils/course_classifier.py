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
    "GEART", "GETHI", "GEMAT", "GEFIL", "GERPH", "GERZA",
    "GEPCO", "GESTS", "GEUSE", "GESPO", "GEDAN", "GEFTW",
    "GREAT", "NSTP", "LASARE", "SAS",
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
            "CCPROG", "CSARCH", "STSWENG", "STALGCM", "MOBDEVE", "INSSYS",
            "CSMATH", "DATAALG", "NETCOMM", "DISMATH", "COMPORG", "CSSYSAL",
            "THS-CS", "PRC-CS", "IS-PROJ", "ANIMAT", "GD-PROJ", "CCINFO",
            "CCAPDEV", "CCDSALG", "CSINTSY", "NSCOM", "CSMODEL", "STADVDB",
            "SE-PROJ", "IT-PROJ", "CSADPRG", "ST-MATH", "CCICOMP",
        ],
    ),
    "RVRCOB": (
        "RVR College of Business",
        [
            "DSOM", "FINA", "MARKET", "ACY", "COB", "MODENMA", "BUSNOTE",
            "COBLAW", "TAXAT", "ENTREP", "MANARES", "ORGBEH", "STRATMA",
            "OPEMAN", "CORPGOV", "ACC", "FIN", "MKT", "BSA", "BSIT",
            "ADVACC", "AUDPRAC", "INTACC", "COSTACC", "TREASUR",
        ],
    ),
    "GCOE": (
        "Gokongwei College of Engineering",
        [
            "ENG", "MEM", "CIV", "ECE", "CHE", "IE", "MEE", "LBY",
            "CPE", "MTHENG", "ENGSTAT", "ENGPHYS", "ENGCAD", "THERMO",
            "DIFFEQN", "NUMMETH", "ENVIENG", "MATERIA", "CIRCUIT",
        ],
    ),
    "CLA": (
        "College of Liberal Arts",
        [
            "AB", "PSY", "HIS", "LIT", "PHIL", "PHILO", "POLIS", "POLISCI", "SOCIO",
            "COMM", "DEVSTUD", "HUMA", "INTSTUD", "MALIKHA", "FORLANG",
            "JAPLANG", "CHNLANG", "SPANISH", "FRENCHN", "GERMAN",
            "THEOLOGY", "RELIGIO", "FILIPIN", "WRITCOM",
        ],
    ),
    "COS": (
        "College of Science",
        [
            "BIO", "CHEM", "PHY", "MTH", "SCIMAT", "ZOO", "BOT",
            "MATH", "ALGEBR", "TRIGON", "CALCUL", "GENBIO", "GENCHEM",
            "GENPHYS", "ANALYTC", "ORCHEM", "BIOCHEM", "ECOLOGY",
        ],
    ),
    "BAGCED": (
        "Br. Andrew Gonzalez College of Education",
        [
            "CED", "EDM", "EDF", "ECE", "SED", "SPE", "PED", "EDUC",
            "TEACHIN", "CURRIC", "CHILDDV", "SPECED", "COUNSEL",
        ],
    ),
    "SOE": (
        "School of Economics",
        [
            "ECO", "ECON", "APECO", "MINECO", "MARECO", "QUANTEC",
            "DEVECO", "INTECON", "LABOREC", "PUBFISC", "MONETAR",
        ],
    ),
}


def classify_course(course_code: str) -> CourseClassification:
    """
    Classifies a DLSU course code into GE, LC, or College category.
    """
    clean = re.sub(r"[^A-Z0-9-]", "", course_code.strip().upper())

    # 1. Check General Education (GE)
    if clean in GE_EXACT_CODES or any(clean.startswith(p) for p in GE_PREFIXES):
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
