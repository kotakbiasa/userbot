import asyncio
import pytest
from selfbot.utils.debug import aexec

@pytest.mark.asyncio
async def test_aexec_basic():
    code = "1 + 1"
    result = await aexec(code)
    assert result == 2

@pytest.mark.asyncio
async def test_aexec_return_value():
    code = "return 10"
    result = await aexec(code)
    assert result == 10

@pytest.mark.asyncio
async def test_aexec_async():
    code = """
import asyncio
await asyncio.sleep(0.01)
1 + 2
"""
    result = await aexec(code, {"asyncio": asyncio})
    assert result == 3

@pytest.mark.asyncio
async def test_aexec_args():
    code = "x * 2"
    result = await aexec(code, {"x": 5})
    assert result == 10

@pytest.mark.asyncio
async def test_aexec_exception():
    code = "raise ValueError('oops')"
    with pytest.raises(ValueError, match="oops"):
        await aexec(code)
