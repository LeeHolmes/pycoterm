import codeop
import contextlib
import io
import json
import rlcompleter
import sys
import threading
import traceback
import builtins
from markdown_renderer import render_markdown as _render_markdown
from pygments.lexers import Python3Lexer

_startup_output = io.StringIO()
with contextlib.redirect_stdout(_startup_output), contextlib.redirect_stderr(_startup_output):
    import pyco


_globals = pyco.__dict__
_buffer = []
_input_callback = None
_input_condition = threading.Condition()
_input_value = None
_input_cancelled = False
_active_output = None
_python_lexer = Python3Lexer()
_completer = rlcompleter.Completer(_globals)


def set_input_callback(callback):
    global _input_callback
    _input_callback = callback


def _android_input(prompt=""):
    global _input_value, _input_cancelled

    if _input_callback is None:
        raise EOFError("Android input bridge is unavailable")

    with _input_condition:
        pending_output = ""
        if _active_output is not None:
            pending_output = _active_output.getvalue()
            _active_output.seek(0)
            _active_output.truncate(0)

        _input_value = None
        _input_cancelled = False
        _input_callback.requestInput(pending_output, str(prompt))
        while _input_value is None and not _input_cancelled:
            _input_condition.wait()
        if _input_cancelled:
            raise EOFError("Android input was cancelled")
        return _input_value


def provide_input(value):
    global _input_value
    with _input_condition:
        _input_value = value
        _input_condition.notify_all()


def cancel_input():
    global _input_cancelled
    with _input_condition:
        _input_cancelled = True
        _input_condition.notify_all()


builtins.input = _android_input


def _json_result(
    value=None, *, error=None, output=None, continuation=False, record_history=None
):
    result = {"continuation": continuation}
    if record_history is not None:
        result["recordHistory"] = record_history
    if error is not None:
        result["error"] = error
    elif output is not None:
        result["output"] = output
    else:
        result["result"] = value
    return json.dumps(result, default=str)


def initialize(customization=""):
    output = io.StringIO()
    output.write(_startup_output.getvalue())

    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            if customization:
                exec(compile(customization, "<customization>", "exec"), _globals, _globals)
            setup = _globals.get("setup")
            if callable(setup):
                setup()
        return _json_result(output.getvalue())
    except BaseException:
        traceback.print_exc(file=output)
        return _json_result(error=output.getvalue())


def execute_line(line):
    global _active_output, _buffer

    _buffer.append(line)
    source = "\n".join(_buffer)
    try:
        compiled = codeop.compile_command(source, "<pyco>", "single")
    except (OverflowError, SyntaxError, ValueError):
        compiled = None
        compile_error = True
    else:
        compile_error = False

    if compiled is None and not compile_error:
        return _json_result("", continuation=True)

    _buffer = []
    output = io.StringIO()
    _active_output = output
    try:
        if hasattr(pyco, "_pre_exec_hook"):
            pyco._pre_exec_hook(source)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            if compile_error:
                compile(source, "<pyco>", "single")
            else:
                exec(compiled, _globals, _globals)
        if hasattr(builtins, "_"):
            _globals["_"] = builtins._
        return _json_result(output.getvalue(), record_history=bool(source.strip()))
    except BaseException as error:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            sys.excepthook(type(error), error, error.__traceback__)
        return _json_result(
            error=output.getvalue(),
            record_history=not compile_error and bool(source.strip()),
        )
    finally:
        _active_output = None


def get_value(name):
    if name not in _globals:
        return _json_result(error=f"Unknown name: {name}")
    return _json_result(_globals[name])


def call_helper(name, argument):
    helper = _globals.get(name)
    if not callable(helper):
        return _json_result(error=f"Unknown helper: {name}")
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            result = helper(argument)
        if result is not None:
            return _json_result(result)
        printed = output.getvalue()
        return _json_result(output=printed) if printed else _json_result()
    except Exception as error:
        return _json_result(error=str(error))


def render_markdown(markdown_text):
    return _render_markdown(markdown_text)


def highlight_python(source):
    tokens = [[str(token_type), value] for token_type, value in _python_lexer.get_tokens(source)]
    if not source.endswith("\n") and tokens and tokens[-1][1].endswith("\n"):
        tokens[-1][1] = tokens[-1][1][:-1]
        if not tokens[-1][1]:
            tokens.pop()
    return json.dumps(tokens)


def get_completions(text):
    completions = []
    index = 0
    while True:
        completion = _completer.complete(text, index)
        if completion is None:
            return json.dumps(completions)
        completions.append(completion)
        index += 1
