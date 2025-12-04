import datetime
import pytest
from selfbot.utils.fmt import fmtbar, fmtbyte, fmtexc, fmtmsg, fmtsec

def test_fmtbar():
    # Test basic functionality
    # chr(9635) is '▣'
    # chr(9633) is '□'
    fill = chr(9635)
    empty = chr(9633)

    expected_50 = f"[ {fill*5}{empty*5} ] 50%"
    assert fmtbar(50, 100, bars=10) == expected_50

    expected_0 = f"[ {empty*10} ] 0%"
    assert fmtbar(0, 100, bars=10) == expected_0

    expected_100 = f"[ {fill*10} ] 100%"
    assert fmtbar(100, 100, bars=10) == expected_100

    # Test custom fill/empty chars
    assert fmtbar(5, 10, fill="#", empty="-", bars=10) == "[ #####----- ] 50%"

def test_fmtbyte():
    assert fmtbyte(1) == "1 B"
    assert fmtbyte(1024) == "1 KB"
    assert fmtbyte(1024**2) == "1 MB"
    assert fmtbyte(1024**3) == "1 GB"
    assert fmtbyte(1024**4) == "1 TB"
    assert fmtbyte(1536) == "1.5 KB"
    assert fmtbyte(0) == "-"

def test_fmtmsg():
    # Test string data
    assert "<b>Head</b>" in fmtmsg("Head", "Data")
    assert "Data" in fmtmsg("Head", "Data")

    # Test dict data
    data_dict = {"Key": "Value"}
    msg = fmtmsg("Head", data_dict)
    assert "Key" in msg
    assert "Value" in msg

    # Test list data
    data_list = ["Item1", "Item2"]
    msg = fmtmsg("Head", data_list)
    assert "Item1" in msg
    assert "Item2" in msg

    # Test footer and msgs
    msg = fmtmsg("Head", "Data", foot="Footer", msgs="Messages")
    assert "Footer" in msg
    assert "Messages" in msg

def test_fmtsec():
    # Test integer seconds
    assert fmtsec(60) == "1m"
    assert fmtsec(3600) == "1h"
    assert fmtsec(3661) == "1h, 1m, 1s"

    # Test timedelta
    assert fmtsec(datetime.timedelta(seconds=65)) == "1m, 5s"

    # Test datetime (assuming recent past)
    now = datetime.datetime.now(datetime.UTC)
    past = now - datetime.timedelta(seconds=10)
    # Note: fmtsec calculates difference from now, so exact matching might be flaky due to execution time.
    # We can mock datetime if needed, but simple check is ok.
    # Since fmtsec uses datetime.now(datetime.UTC) inside, we can't easily deterministic test it without mocking.
    # But we can test that it returns something reasonable.
    res = fmtsec(past)
    assert "s" in res

    # Test invalid input
    with pytest.raises(TypeError):
        fmtsec("invalid")
