import ast
import asyncio
import inspect


async def aexec(code: str, args: dict = {}) -> any:
    body = ast.parse(code, "exec").body
    if body and isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(value=body[-1].value)

    name = "aexec"
    node = ast.Module(
        body=[
            ast.AsyncFunctionDef(
                name=name,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg=key) for key in args],
                    vararg=None,
                    kwonlyargs=[],
                    kw_defaults=[],
                    kwarg=None,
                    defaults=[],
                ),
                body=body,
                decorator_list=[],
                returns=None,
                type_params=[],
            )
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(node)
    temp = {}
    exec(compile(node, "<string>", "exec"), temp)
    coro = await temp[name](*args.values())
    return await coro if inspect.iscoroutine(coro) else coro


async def shell(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await proc.communicate()
        return (stdout + stderr).decode()
    finally:
        try:
            if not proc.returncode:
                proc.terminate()
        except ProcessLookupError:
            pass
        else:
            await proc.wait()
