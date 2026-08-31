"""
Unit Tests for Course and College Classifier
"""

from utils.course_classifier import classify_course


def test_ge_classification():
    ge_subjects = ["GEARTAP", "GETHICS", "GEMATHT", "GEFILI1", "GERPHIS", "GERZAL", "GEPCOMM", "NSTP101", "LASARE1"]
    for code in ge_subjects:
        res = classify_course(code)
        assert res.is_ge_lc is True
        assert res.category_type == "GE"
        assert res.feed_channel_key == "ge_lc"


def test_lc_classification():
    lc_subjects = ["LCFILIA", "LCFILIB", "LCLSONE", "LCLSTWO", "LCLSTRI", "LCFAITH"]
    for code in lc_subjects:
        res = classify_course(code)
        assert res.is_ge_lc is True
        assert res.category_type == "LC"
        assert res.feed_channel_key == "ge_lc"


def test_college_classifications():
    # CCS
    assert classify_course("STSWENG").college_code == "CCS"
    assert classify_course("CCPROG2").college_code == "CCS"
    assert classify_course("CSARCH1").college_code == "CCS"
    assert classify_course("STSWENG").feed_channel_key == "ccs"

    # RVRCOB
    assert classify_course("DSOMINT").college_code == "RVRCOB"
    assert classify_course("FINAMAN").college_code == "RVRCOB"
    assert classify_course("MODENMA").college_code == "RVRCOB"
    assert classify_course("DSOMINT").feed_channel_key == "rvrcob"

    # GCOE
    assert classify_course("ENGPHYS").college_code == "GCOE"
    assert classify_course("LBYME1A").college_code == "GCOE"
    assert classify_course("ENGPHYS").feed_channel_key == "gcoe"

    # CLA
    assert classify_course("PSYCHOL").college_code == "CLA"
    assert classify_course("PHILMAN").college_code == "CLA"
    assert classify_course("PSYCHOL").feed_channel_key == "cla"

    # COS
    assert classify_course("GENCHEM").college_code == "COS"
    assert classify_course("GENPHYS").college_code == "COS"
    assert classify_course("GENCHEM").feed_channel_key == "cos"

    # BAGCED
    assert classify_course("CEDSECD").college_code == "BAGCED"
    assert classify_course("EDUC101").college_code == "BAGCED"
    assert classify_course("CEDSECD").feed_channel_key == "bagced"

    # SOE
    assert classify_course("ECONDEV").college_code == "SOE"
    assert classify_course("APECO10").college_code == "SOE"
    assert classify_course("ECONDEV").feed_channel_key == "soe"
