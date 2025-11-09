#!/usr/bin/env python3
"""
pyco - Python Console Terminal
A terminal-style application for interactive Python execution with full keyboard navigation.
"""

import sys
import os
import io
import traceback
import contextlib
import urllib.request
import urllib.error
import json
import re
from typing import List, Optional, Any
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget, 
    QHBoxLayout, QLabel, QMenuBar, QMenu, QMessageBox, QDialog,
    QTextBrowser, QSplitter, QFrame, QProgressDialog, QPushButton,
    QSizePolicy, QSlider, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import (
    QFont, QTextCursor, QTextCharFormat, QColor, QKeySequence,
    QAction, QPalette, QSyntaxHighlighter, QTextDocument, QIcon,
    QPainter, QPen, QLinearGradient, QClipboard
)



class PycoDownloader(QThread):
    """Thread for downloading pyco.py and README.md from GitHub"""
    download_finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, install_dir: str):
        super().__init__()
        self.install_dir = install_dir
        self.pyco_url = "https://raw.githubusercontent.com/LeeHolmes/pyco/refs/heads/main/pyco.py"
        self.readme_url = "https://raw.githubusercontent.com/LeeHolmes/pyco/refs/heads/main/README.md"
        
    def run(self):
        """Download pyco.py and README.md from GitHub"""
        try:
            # Download pyco.py
            pyco_path = os.path.join(self.install_dir, "pyco.py")
            response = urllib.request.urlopen(self.pyco_url, timeout=10)
            content = response.read().decode('utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            with open(pyco_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            
            # Download README.md
            readme_path = os.path.join(self.install_dir, "README.md")
            response = urllib.request.urlopen(self.readme_url, timeout=10)
            content = response.read().decode('utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            with open(readme_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
                
            self.download_finished.emit(True, "Downloaded pyco.py and README.md")
            
        except urllib.error.URLError as e:
            self.download_finished.emit(False, f"Network error: {e}")
        except Exception as e:
            self.download_finished.emit(False, f"Download failed: {e}")

class PythonExecutor(QThread):
    """Thread for executing Python code safely"""
    execution_finished = pyqtSignal(str, bool)  # output, is_error
    input_requested = pyqtSignal(str)  # prompt text
    output_ready = pyqtSignal(str)  # output without prompt insertion
    
    def __init__(self):
        super().__init__()
        self.code = ""
        self.globals_dict = {"__name__": "__main__"}
        self.locals_dict = {}
        self.input_response = None
        self.input_event = None
        self.interrupted = False
        self.initial_globals = set()  # Track what was available before pyco.py
        self.setup_python_environment()
        
    def setup_python_environment(self):
        """Setup Python environment with proper sys module access"""
        # Make sys and builtins modules available in the globals so displayhook/excepthook can be customized
        import sys
        import builtins
        self.globals_dict['sys'] = sys
        self.globals_dict['builtins'] = builtins
        
        # Record initial state - everything available before pyco.py
        self.initial_globals = set(self.globals_dict.keys())
        # Also include Python builtins as part of initial state
        self.initial_globals.update(name for name in dir(builtins) if not name.startswith('_'))
        
    def set_code(self, code: str):
        self.code = code
        
    def provide_input(self, user_input: str):
        """Provide user input response"""
        self.input_response = user_input
        if self.input_event:
            self.input_event.set()
    
    def interrupt_execution(self):
        """Interrupt the current execution"""
        self.interrupted = True
        if self.input_event:
            self.input_event.set()
        
    def run(self):
        """Execute Python code and capture output"""
        # Reset interrupted flag at start of execution
        self.interrupted = False
        
        if not self.code.strip():
            self.execution_finished.emit("", False)
            return
            
        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Create a custom input function that requests input from the main thread
        def interactive_input(prompt=""):
            # Check for any pending output and emit it before requesting input
            pending_output = stdout_capture.getvalue()
            if pending_output:
                # Clear the capture buffer
                stdout_capture.seek(0)
                stdout_capture.truncate(0)
                # Emit the pending output without inserting a prompt
                self.output_ready.emit(pending_output)
                # Small delay to allow UI to update
                import time
                time.sleep(0.01)
            
            # Flush any remaining output
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Import threading here to avoid import issues
            import threading
            self.input_event = threading.Event()
            self.input_response = None
            
            # Request input from main thread (prompt will be displayed inline)
            self.input_requested.emit(prompt)
            
            # Wait for response
            self.input_event.wait()
            
            # Check if we were interrupted
            if self.interrupted:
                raise KeyboardInterrupt()
            
            # Return the response (no echo needed since it's already displayed inline)
            response = self.input_response or ""
            return response
        
        # Initialize old_input before try block to avoid UnboundLocalError
        # Handle both cases where __builtins__ can be a module or dict
        import builtins
        old_input = getattr(builtins, 'input', input)
        result_value = None  # Initialize result_value in broader scope
        exception_occurred = False  # Track if any exception occurred during execution
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            # Override input function to use interactive input
            builtins.input = interactive_input
            
            # Try to compile as an expression first (for interactive results)
            try:
                compiled = compile(self.code, '<input>', 'eval')
                result = eval(compiled, self.globals_dict, self.locals_dict)
                if result is not None:
                    # Use sys.displayhook if available, otherwise fall back to print(repr())
                    if hasattr(sys, 'displayhook') and callable(sys.displayhook):
                        # Save current builtins._ value to detect if displayhook changes it
                        import builtins
                        old_underscore = getattr(builtins, '_', object())  # Use sentinel if _ doesn't exist
                        
                        displayhook_result = sys.displayhook(result)
                        
                        # Check if displayhook modified builtins._ (like CPython's __displayhook__ does)
                        new_underscore = getattr(builtins, '_', object())
                        if new_underscore is not old_underscore:
                            # displayhook set builtins._, sync it with our globals dict
                            self.globals_dict['_'] = new_underscore
                            # Clear result_value since _ was already set by displayhook
                            result_value = None
                        else:
                            # displayhook didn't set _, use normal logic
                            result_value = displayhook_result if displayhook_result is not None else result
                    else:
                        print(repr(result))
                        result_value = result  # Store the actual result
            except SyntaxError:
                # If that fails, try as a statement
                try:
                    compiled = compile(self.code, '<input>', 'exec')
                    exec(compiled, self.globals_dict, self.locals_dict)
                except KeyboardInterrupt:
                    raise  # Re-raise to be caught by outer handler
                except Exception as e:
                    exception_occurred = True
                    # Use sys.excepthook if available, otherwise fall back to basic error output
                    if hasattr(sys, 'excepthook') and callable(sys.excepthook):
                        excepthook_result = sys.excepthook(type(e), e, e.__traceback__)
                        # If excepthook returns a value, store it in result_value
                        if excepthook_result is not None:
                            result_value = excepthook_result
                            exception_occurred = False  # Allow updating _ if excepthook returned a value
                    else:
                        stderr_capture.write(f"{type(e).__name__}: {e}\n")
            except KeyboardInterrupt:
                raise  # Re-raise to be caught by outer handler
            except Exception as e:
                exception_occurred = True
                # Use sys.excepthook if available, otherwise fall back to basic error output
                if hasattr(sys, 'excepthook') and callable(sys.excepthook):
                    excepthook_result = sys.excepthook(type(e), e, e.__traceback__)
                    # If excepthook returns a value, store it in result_value
                    if excepthook_result is not None:
                        result_value = excepthook_result
                        exception_occurred = False  # Allow updating _ if excepthook returned a value
                else:
                    stderr_capture.write(f"{type(e).__name__}: {e}\n")
                
        except KeyboardInterrupt:
            # Handle Ctrl+C interruption specially
            exception_occurred = True
            # Emit a special signal for keyboard interrupt to avoid treating it as normal output
            self.execution_finished.emit("^C\nKeyboardInterrupt", True)
            return
        except Exception as e:
            exception_occurred = True
            # Use sys.excepthook if available for top-level execution errors
            if hasattr(sys, 'excepthook') and callable(sys.excepthook):
                excepthook_result = sys.excepthook(type(e), e, e.__traceback__)
                # If excepthook returns a value, store it in result_value
                if excepthook_result is not None:
                    result_value = excepthook_result
                    exception_occurred = False  # Allow updating _ if excepthook returned a value
            else:
                stderr_capture.write(f"Execution error: {e}\n")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
            # Restore original input function
            builtins.input = old_input
            
        # Get captured output
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        output = stdout_output
        is_error = False
        
        if stderr_output:
            output = stderr_output if not stdout_output else f"{stdout_output}\n{stderr_output}"
            is_error = True
        
        # Store the result in the '_' variable for the next command
        # This follows the convention of interactive Python environments
        # Don't update '_' if an exception occurred (matching CPython behavior)
        # Only update '_' for expression results, not statement outputs
        if not exception_occurred and result_value is not None:
            self.globals_dict['_'] = result_value
            # Also set builtins._ to maintain consistency with CPython
            import builtins
            builtins._ = result_value
            
        self.execution_finished.emit(output, is_error)

class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Smart Python syntax highlighter that only highlights input, not output"""
    
    def __init__(self, document: QTextDocument, terminal_widget=None):
        super().__init__(document)
        self.terminal_widget = terminal_widget
        self.setup_highlighting()
        
    def setup_highlighting(self):
        # Define colors
        self.keyword_color = QColor(86, 156, 214)  # Blue
        self.string_color = QColor(206, 145, 120)   # Orange
        self.comment_color = QColor(106, 153, 85)   # Green
        self.number_color = QColor(181, 206, 168)   # Light green
        
        # Python keywords
        self.keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield', 'True', 'False',
            'None', 'async', 'await'
        ]
        
    def is_input_line(self, text: str) -> bool:
        """Check if this line is user input (starts with prompt)"""
        if not self.terminal_widget:
            return True  # Default to highlighting if no terminal widget
            
        # Check if line starts with prompt indicators
        prompt_indicators = [">>> ", "... ", "pyco> "]
        return any(text.startswith(prompt) for prompt in prompt_indicators)
        
    def highlightBlock(self, text: str):
        # Only highlight if this is an input line
        if not self.is_input_line(text):
            return
            
        # Get the text after the prompt
        input_text = text
        input_offset = 0
        
        # Find where the actual input starts (after prompt)
        for prompt in [">>> ", "... ", "pyco> "]:
            if text.startswith(prompt):
                input_text = text[len(prompt):]
                input_offset = len(prompt)
                break
                
        # Highlight keywords
        for keyword in self.keywords:
            format = QTextCharFormat()
            format.setForeground(self.keyword_color)
            format.setFontWeight(QFont.Weight.Bold)
            
            index = 0
            while index < len(input_text):
                index = input_text.find(keyword, index)
                if index == -1:
                    break
                    
                # Check if it's a whole word
                if (index == 0 or not input_text[index-1].isalnum()) and \
                   (index + len(keyword) == len(input_text) or not input_text[index + len(keyword)].isalnum()):
                    self.setFormat(input_offset + index, len(keyword), format)
                    
                index += len(keyword)
                
        # Highlight strings
        string_format = QTextCharFormat()
        string_format.setForeground(self.string_color)
        
        # Single and double quotes
        for match in ['"', "'"]:
            index = 0
            while index < len(input_text):
                start = input_text.find(match, index)
                if start == -1:
                    break
                end = input_text.find(match, start + 1)
                if end == -1:
                    end = len(input_text)
                else:
                    end += 1
                self.setFormat(input_offset + start, end - start, string_format)
                index = end
                
        # Highlight comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(self.comment_color)
        comment_index = input_text.find('#')
        if comment_index != -1:
            self.setFormat(input_offset + comment_index, len(input_text) - comment_index, comment_format)

class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """JSON syntax highlighter that only highlights valid JSON"""
    
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self.setup_highlighting()
        
    def setup_highlighting(self):
        # Define colors for JSON elements
        self.string_color = QColor(206, 145, 120)   # Orange for strings
        self.number_color = QColor(181, 206, 168)   # Light green for numbers
        self.keyword_color = QColor(86, 156, 214)   # Blue for true/false/null
        self.bracket_color = QColor(255, 255, 255)  # White for brackets
        
    def is_valid_json(self, text: str) -> bool:
        """Check if text is valid JSON"""
        text = text.strip()
        if not text:
            return False
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
        
    def highlightBlock(self, text: str):
        # Only highlight if the entire document block contains valid JSON
        if not self.is_valid_json(text):
            return
            
        # Highlight JSON strings
        string_format = QTextCharFormat()
        string_format.setForeground(self.string_color)
        
        in_string = False
        escape_next = False
        start_pos = 0
        
        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"':
                if not in_string:
                    in_string = True
                    start_pos = i
                else:
                    in_string = False
                    self.setFormat(start_pos, i - start_pos + 1, string_format)
                    
        # Highlight JSON numbers
        number_format = QTextCharFormat()
        number_format.setForeground(self.number_color)
        
        import re
        # JSON number pattern
        number_pattern = r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?'
        for match in re.finditer(number_pattern, text):
            # Make sure it's not inside a string
            pos = match.start()
            if not self.is_inside_string(text, pos):
                self.setFormat(pos, len(match.group()), number_format)
                
        # Highlight JSON keywords (true, false, null)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(self.keyword_color)
        keyword_format.setFontWeight(QFont.Weight.Bold)
        
        for keyword in ['true', 'false', 'null']:
            index = 0
            while index < len(text):
                index = text.find(keyword, index)
                if index == -1:
                    break
                if not self.is_inside_string(text, index):
                    self.setFormat(index, len(keyword), keyword_format)
                index += len(keyword)
                
        # Highlight brackets and braces
        bracket_format = QTextCharFormat()
        bracket_format.setForeground(self.bracket_color)
        bracket_format.setFontWeight(QFont.Weight.Bold)
        
        for char in '{}[]':
            index = 0
            while index < len(text):
                index = text.find(char, index)
                if index == -1:
                    break
                if not self.is_inside_string(text, index):
                    self.setFormat(index, 1, bracket_format)
                index += 1
                
    def is_inside_string(self, text: str, pos: int) -> bool:
        """Check if position is inside a JSON string"""
        in_string = False
        escape_next = False
        
        for i in range(pos):
            if escape_next:
                escape_next = False
                continue
                
            if text[i] == '\\':
                escape_next = True
                continue
                
            if text[i] == '"':
                in_string = not in_string
                
        return in_string

class CRTEffectsOverlay(QWidget):
    """Overlay widget that draws scanlines and glow effects for retro CRT appearance"""
    
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        
    def paintEvent(self, event):
        """Draw scanlines and glow effects"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Sharp lines for scanlines
        
        # Draw more prominent horizontal scanlines
        pen = QPen(QColor(0, 0, 0, 80))  # More visible dark lines
        pen.setWidth(1)
        painter.setPen(pen)
        
        # Draw very thin horizontal lines every 2 pixels for authentic CRT look
        for y in range(1, self.height(), 2):
            painter.drawLine(0, y, self.width(), y)
        
        # Add more prominent overall glow/bloom effect
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Horizontal glow gradient (left to right fade) - more prominent
        h_gradient = QLinearGradient(0, 0, self.width(), 0)
        h_gradient.setColorAt(0.0, QColor(0, 255, 0, 25))  # Stronger green glow at edges
        h_gradient.setColorAt(0.1, QColor(0, 255, 0, 15))
        h_gradient.setColorAt(0.3, QColor(0, 255, 0, 8))
        h_gradient.setColorAt(0.5, QColor(0, 255, 0, 3))   # Minimal glow in center
        h_gradient.setColorAt(0.7, QColor(0, 255, 0, 8))
        h_gradient.setColorAt(0.9, QColor(0, 255, 0, 15))
        h_gradient.setColorAt(1.0, QColor(0, 255, 0, 25))
        painter.fillRect(self.rect(), h_gradient)
        
        # Vertical glow gradient (top to bottom fade) - more prominent
        v_gradient = QLinearGradient(0, 0, 0, self.height())
        v_gradient.setColorAt(0.0, QColor(0, 255, 0, 25))  # Stronger green glow at top/bottom
        v_gradient.setColorAt(0.1, QColor(0, 255, 0, 15))
        v_gradient.setColorAt(0.3, QColor(0, 255, 0, 8))
        v_gradient.setColorAt(0.5, QColor(0, 255, 0, 3))   # Minimal glow in center
        v_gradient.setColorAt(0.7, QColor(0, 255, 0, 8))
        v_gradient.setColorAt(0.9, QColor(0, 255, 0, 15))
        v_gradient.setColorAt(1.0, QColor(0, 255, 0, 25))
        painter.fillRect(self.rect(), v_gradient)

class TerminalWithCRTEffects(QWidget):
    """Container widget that combines terminal with CRT effects overlay"""
    
    def __init__(self):
        super().__init__()
        self.setup_crt_terminal()
        
    def setup_crt_terminal(self):
        """Setup terminal with CRT effects overlay"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create terminal widget
        self.terminal = TerminalWidget()
        layout.addWidget(self.terminal)
        
        # Create CRT effects overlay on top
        self.crt_overlay = CRTEffectsOverlay()
        self.crt_overlay.setParent(self)
        
    def resizeEvent(self, event):
        """Ensure overlay matches widget size"""
        super().resizeEvent(event)
        if hasattr(self, 'crt_overlay'):
            self.crt_overlay.setGeometry(self.rect())

class TerminalWidget(QTextEdit):
    """Custom text widget that behaves like a terminal"""
    
    command_executed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_terminal()
        self.command_history: List[str] = []
        self.history_index = -1
        self.prompt = ">>> "
        self.continuation_prompt = "... "
        self.current_prompt = self.prompt
        self.command_start_position = 0
        self.python_executor = PythonExecutor()
        self.python_executor.execution_finished.connect(self.on_execution_finished)
        self.python_executor.input_requested.connect(self.on_input_requested)
        self.python_executor.output_ready.connect(self.append_output_only)
        self.pyco_download_pending = False  # Flag for pyco download prompt
        self.waiting_for_input = False  # Flag when waiting for user input
        self.input_prompt = ""  # Store the input prompt
        self.last_input_cursor_position = None  # Track cursor position in input area
        
        # Setup syntax highlighting for input
        self.python_highlighter = PythonSyntaxHighlighter(self.document(), self)
        # Also keep JSON highlighter for output
        self.json_highlighter = JSONSyntaxHighlighter(None)
        
        # Note: insert_prompt() will be called after pyco.py is loaded
        
    def setup_terminal(self):
        """Configure the terminal appearance and behavior"""
        # Set monospace font
        font = QFont("Consolas", 12)
        if not font.exactMatch():
            font = QFont("Courier New", 12)
        font.setFixedPitch(True)
        self.setFont(font)
        
        # Set colors (retro CRT theme - greenish background)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(20, 35, 20))  # Dark green CRT background
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 255, 0))   # Bright green text
        self.setPalette(palette)
        
        # Also set direct stylesheet to ensure CRT styling takes effect
        self.setStyleSheet("""
            QTextEdit {
                background-color: rgb(24, 42, 24) !important;  /* 20% brighter dark green CRT background */
                color: rgb(0, 255, 0) !important;              /* Bright green text */
                
                /* Create multi-layered green gradient border effect */
                border: 3px solid rgb(18, 32, 18);             /* Inner border - lighter green */
                
                selection-background-color: rgb(0, 128, 0);
                selection-color: rgb(24, 42, 24);
                padding: 2px;
            }
        """)
        
        # Set cursor
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        
    def insert_prompt(self):
        """Insert a new prompt at the end"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Insert prompt with different color
        prompt_format = QTextCharFormat()
        prompt_format.setForeground(QColor(100, 200, 100))  # Green
        cursor.insertText(self.current_prompt, prompt_format)
        
        self.command_start_position = cursor.position()
        self.last_input_cursor_position = cursor.position()
        self.setTextCursor(cursor)
        
    def append_output_only(self, output: str):
        """Append output without inserting a prompt (used during input requests)"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if output:
            # Check if output is valid Python and apply highlighting if so
            if self.is_valid_python(output):
                self.apply_python_highlighting(cursor, output)
            else:
                cursor.insertText(output)
            
            # Only add newline if output doesn't already end with one
            if not output.endswith('\n'):
                cursor.insertText("\n")
            
        self.setTextCursor(cursor)
        
    def append_system_message(self, message: str):
        """Append a system message without a prompt"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Insert system message with different color
        system_format = QTextCharFormat()
        system_format.setForeground(QColor(200, 200, 100))  # Yellow
        cursor.insertText(message, system_format)
        
        self.setTextCursor(cursor)
        
    def get_current_command(self) -> str:
        """Get the current command being typed"""
        cursor = self.textCursor()
        cursor.setPosition(self.command_start_position)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText()
        
    def set_current_command(self, command: str):
        """Set the current command text"""
        cursor = self.textCursor()
        cursor.setPosition(self.command_start_position)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(command)
        
    def get_completions(self, text: str, cursor_pos: int):
        """Get tab completions for the given text at cursor position"""
        # Get the word being completed
        words = text[:cursor_pos].split()
        if not words:
            # No input - return all available names
            return self.get_all_completions()
            
        last_word = words[-1]
        
        # Check if we're completing an attribute (contains a dot)
        if '.' in last_word:
            parts = last_word.split('.')
            if len(parts) >= 2:
                obj_name = '.'.join(parts[:-1])
                attr_prefix = parts[-1]
                
                try:
                    # Get the object from the Python environment
                    obj = eval(obj_name, self.python_executor.globals_dict)
                    # Get all attributes of the object
                    attrs = [attr for attr in dir(obj) if attr.startswith(attr_prefix)]
                    return [f"{obj_name}.{attr}" for attr in attrs]
                except:
                    return []
        else:
            # Complete global variables and functions
            completions = []
            
            # Get from Python executor's globals
            for name in self.python_executor.globals_dict:
                if name.startswith(last_word) and not name.startswith('_'):
                    completions.append(name)
            
            # Add Python builtins
            import builtins
            for name in dir(builtins):
                if name.startswith(last_word) and not name.startswith('_'):
                    completions.append(name)
                    
            return sorted(list(set(completions)))
    
    def get_all_completions(self):
        """Get all available completions when no input is provided (only new items after pyco.py)"""
        completions = []
        
        # Get from Python executor's globals, excluding initial globals
        for name in self.python_executor.globals_dict:
            if not name.startswith('_') and name not in self.python_executor.initial_globals:
                completions.append(name)
                
        return sorted(list(set(completions)))
        
    def handle_tab_completion(self):
        """Handle tab completion"""
        current_command = self.get_current_command()
        cursor = self.textCursor()
        cursor_pos = cursor.position() - self.command_start_position
        
        completions = self.get_completions(current_command, cursor_pos)
        
        if not completions:
            return
            
        if len(completions) == 1:
            # Single completion - insert it
            words = current_command[:cursor_pos].split()
            if words:
                last_word = words[-1]
                completion = completions[0]
                
                # Calculate the part to insert
                if '.' in last_word:
                    # For attribute completion, replace only the part after the last dot
                    parts = last_word.split('.')
                    prefix_to_replace = parts[-1]
                    attr_name = completion.split('.')[-1]
                    insert_text = attr_name[len(prefix_to_replace):]
                else:
                    # For regular completion, insert the remaining part
                    insert_text = completion[len(last_word):]
                
                # Insert the completion
                cursor = self.textCursor()
                cursor.insertText(insert_text)
                self.setTextCursor(cursor)
        else:
            # Multiple completions - show them
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n")
            
            # Display completions in columns
            max_width = max(len(comp) for comp in completions)
            cols = max(1, 80 // (max_width + 2))
            
            for i, completion in enumerate(completions):
                if i > 0 and i % cols == 0:
                    cursor.insertText("\n")
                cursor.insertText(f"{completion:<{max_width + 2}}")
            
            cursor.insertText("\n")
            self.setTextCursor(cursor)
            self.insert_prompt()
            
            # Restore the command being typed
            cursor = self.textCursor()
            cursor.insertText(current_command)
            self.setTextCursor(cursor)
        
    def keyPressEvent(self, event):
        """Handle key press events with terminal-like behavior"""
        key = event.key()
        modifiers = event.modifiers()
        cursor = self.textCursor()
        
        # Ignore modifier-only key presses (Ctrl, Alt, Shift by themselves)
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return
        
        # Only prevent editing (not selection) before the current command
        # Allow Ctrl+C and other control operations even when cursor is before command start
        prevent_editing = (cursor.position() < self.command_start_position and 
                          not (modifiers & Qt.KeyboardModifier.ControlModifier))
            
        # Handle special keys
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if prevent_editing:
                return
            self.handle_return()
        elif key == Qt.Key.Key_Tab and not self.waiting_for_input:
            if prevent_editing:
                return
            self.handle_tab_completion()
        elif key == Qt.Key.Key_Up and not self.waiting_for_input:
            if prevent_editing:
                return
            self.navigate_history(-1)
        elif key == Qt.Key.Key_Down and not self.waiting_for_input:
            if prevent_editing:
                return
            self.navigate_history(1)
        elif key == Qt.Key.Key_Home:
            cursor.setPosition(self.command_start_position)
            self.setTextCursor(cursor)
            self.last_input_cursor_position = cursor.position()
        elif key == Qt.Key.Key_End:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            self.last_input_cursor_position = cursor.position()
        elif key == Qt.Key.Key_Backspace:
            if cursor.position() <= self.command_start_position:
                return  # Don't allow backspace before command start
            super().keyPressEvent(event)
            # Update cursor position after backspace
            new_cursor = self.textCursor()
            if new_cursor.position() >= self.command_start_position:
                self.last_input_cursor_position = new_cursor.position()
        elif key == Qt.Key.Key_Left:
            if cursor.position() <= self.command_start_position:
                return  # Don't allow moving left before command start
            super().keyPressEvent(event)
            # Update cursor position after move
            new_cursor = self.textCursor()
            if new_cursor.position() >= self.command_start_position:
                self.last_input_cursor_position = new_cursor.position()
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self.handle_ctrl_c()
            elif key == Qt.Key.Key_D:
                # Quit application with Ctrl+D
                main_window = self.window()
                if main_window:
                    main_window.close()
            elif key == Qt.Key.Key_L:
                self.clear()
                self.insert_prompt()
            elif key == Qt.Key.Key_A:
                # Select all text in current input (from prompt to end of line)
                cursor.setPosition(self.command_start_position)
                cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cursor)
            elif key == Qt.Key.Key_E:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
            elif key == Qt.Key.Key_K:
                # Clear from cursor to end of line
                cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            elif key == Qt.Key.Key_U:
                # Clear entire command
                self.set_current_command("")
            else:
                super().keyPressEvent(event)
        else:
            # Only allow typing if not preventing editing
            if not prevent_editing:
                # Track cursor position when user is working in input area
                if cursor.position() >= self.command_start_position:
                    self.last_input_cursor_position = cursor.position()
                super().keyPressEvent(event)
                
    def handle_return(self):
        """Handle Enter key press"""
        command = self.get_current_command()
        
        # Move cursor to end and add newline
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n")
        self.setTextCursor(cursor)
        
        # Check if we're waiting for input from Python code
        if self.waiting_for_input:
            # Provide the input to the executor
            self.python_executor.provide_input(command)
            self.waiting_for_input = False
            self.input_prompt = ""
            return
        
        # Check if we're waiting for pyco download response
        if self.pyco_download_pending:
            response = command.strip().lower()
            if response in ['y', 'yes']:
                # Find the main window to start download
                main_window = self.window()
                if hasattr(main_window, 'download_pyco'):
                    main_window.download_pyco()
                return
            elif response in ['n', 'no']:
                self.append_system_message("Download cancelled.\n")
                self.pyco_download_pending = False
                self.insert_prompt()
                return
            else:
                self.append_system_message("Please enter 'y' for yes or 'n' for no: ")
                # Reset command start position for next input
                self.command_start_position = self.textCursor().position()
                return
        
        if command.strip():
            # Add to history
            if not self.command_history or self.command_history[-1] != command:
                self.command_history.append(command)
            self.history_index = len(self.command_history)
            
            # Execute command
            self.python_executor.set_code(command)
            self.python_executor.start()
        else:
            self.insert_prompt()
            
    def handle_ctrl_c(self):
        """Handle Ctrl+C - Copy if text is selected, otherwise keyboard interrupt"""
        cursor = self.textCursor()
        
        # Check if there's selected text - be more thorough
        has_selection = cursor.hasSelection()
        selected_text = cursor.selectedText() if has_selection else ""
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()
        
        if has_selection and selected_text.strip():
            # Copy selected text to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(selected_text)
            
            # Clear the selection and restore cursor to where user was working
            cursor.clearSelection()
            if self.last_input_cursor_position is not None:
                # Restore to the last known input position
                cursor.setPosition(self.last_input_cursor_position)
                restore_pos = self.last_input_cursor_position
            else:
                # Fallback to end of document
                cursor.movePosition(QTextCursor.MoveOperation.End)
                restore_pos = cursor.position()
            self.setTextCursor(cursor)
            
            return  # Important: Don't continue to keyboard interrupt
        
        # No text selected, handle keyboard interrupt
        
        # If we're waiting for input, interrupt the executor thread
        if self.waiting_for_input:
            self.waiting_for_input = False
            self.input_prompt = ""
            # Interrupt the Python executor thread
            self.python_executor.interrupt_execution()
            # Don't insert text here - let the executor handle the KeyboardInterrupt output
        else:
            # Normal keyboard interrupt (when not executing code)
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\nKeyboardInterrupt\n")
            self.setTextCursor(cursor)
            self.insert_prompt()
        
    def is_valid_python(self, text: str) -> bool:
        """Check if text is valid Python code"""
        text = text.strip()
        if not text:
            return False
        try:
            compile(text, '<string>', 'eval')
            return True
        except SyntaxError:
            try:
                compile(text, '<string>', 'exec')
                return True
            except SyntaxError:
                return False
    
    def apply_python_highlighting(self, cursor: QTextCursor, text: str):
        """Apply Python syntax highlighting to the given text"""
        # Insert the text first without any formatting
        start_position = cursor.position()
        cursor.insertText(text)
        
        # Now apply formatting using regex patterns
        self.highlight_python_in_range(start_position, start_position + len(text))
        
    def highlight_python_in_range(self, start_pos: int, end_pos: int):
        """Apply Python highlighting to a specific range in the document"""
        document = self.document()
        cursor = QTextCursor(document)
        
        # Get the text in the range
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        text = cursor.selectedText()
        
        # Define colors for Python elements (same as input highlighting)
        keyword_color = QColor(86, 156, 214)  # Blue
        string_color = QColor(206, 145, 120)   # Orange  
        comment_color = QColor(106, 153, 85)   # Green
        number_color = QColor(181, 206, 168)   # Light green
        
        # Highlight Python keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(keyword_color)
        keyword_format.setFontWeight(QFont.Weight.Bold)
        
        import re
        python_keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield', 'True', 'False',
            'None', 'async', 'await'
        ]
        
        for keyword in python_keywords:
            keyword_pattern = r'\b' + re.escape(keyword) + r'\b'
            for match in re.finditer(keyword_pattern, text):
                # Make sure it's not inside a string
                if not self.is_position_in_python_string(text, match.start()):
                    cursor.setPosition(start_pos + match.start())
                    cursor.setPosition(start_pos + match.end(), QTextCursor.MoveMode.KeepAnchor)
                    cursor.setCharFormat(keyword_format)
                    
        # Highlight Python strings first (they have priority)
        string_format = QTextCharFormat()
        string_format.setForeground(string_color)
        
        # Find all Python strings (single and double quotes)
        string_patterns = [
            r'"(?:[^"\\]|\\.)*"',  # Double quotes
            r"'(?:[^'\\]|\\.)*'"   # Single quotes
        ]
        
        for pattern in string_patterns:
            for match in re.finditer(pattern, text):
                cursor.setPosition(start_pos + match.start())
                cursor.setPosition(start_pos + match.end(), QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(string_format)
                
        # Highlight Python numbers
        number_format = QTextCharFormat()
        number_format.setForeground(number_color)
        
        number_pattern = r'\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b'
        for match in re.finditer(number_pattern, text):
            # Make sure it's not inside a string
            if not self.is_position_in_python_string(text, match.start()):
                cursor.setPosition(start_pos + match.start())
                cursor.setPosition(start_pos + match.end(), QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(number_format)
                
        # Highlight Python comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(comment_color)
        
        comment_pattern = r'#.*$'
        for match in re.finditer(comment_pattern, text, re.MULTILINE):
            # Make sure it's not inside a string
            if not self.is_position_in_python_string(text, match.start()):
                cursor.setPosition(start_pos + match.start())
                cursor.setPosition(start_pos + match.end(), QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(comment_format)
                
    def is_position_in_python_string(self, text: str, pos: int) -> bool:
        """Check if position is inside a Python string"""
        # Count unescaped quotes (both single and double) before this position
        double_quote_count = 0
        single_quote_count = 0
        i = 0
        while i < pos:
            if text[i] == '"':
                # Check if it's escaped
                escape_count = 0
                j = i - 1
                while j >= 0 and text[j] == '\\':
                    escape_count += 1
                    j -= 1
                # If even number of escapes (including 0), quote is not escaped
                if escape_count % 2 == 0:
                    double_quote_count += 1
            elif text[i] == "'":
                # Check if it's escaped  
                escape_count = 0
                j = i - 1
                while j >= 0 and text[j] == '\\':
                    escape_count += 1
                    j -= 1
                # If even number of escapes (including 0), quote is not escaped
                if escape_count % 2 == 0:
                    single_quote_count += 1
            i += 1
        # If odd number of quotes, we're inside a string
        return (double_quote_count % 2 == 1) or (single_quote_count % 2 == 1)
        
    def is_position_inside_json_string(self, text: str, pos: int) -> bool:
        """Check if position is inside a JSON string"""
        in_string = False
        escape_next = False
        
        for i in range(pos):
            if escape_next:
                escape_next = False
                continue
                
            if text[i] == '\\':
                escape_next = True
                continue
                
            if text[i] == '"':
                in_string = not in_string
                
        return in_string

    @pyqtSlot(str, bool)
    def on_execution_finished(self, output: str, is_error: bool):
        """Handle completion of Python code execution"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if output:
            # Format output
            if is_error:
                error_format = QTextCharFormat()
                error_format.setForeground(QColor(255, 100, 100))  # Red
                cursor.insertText(output, error_format)
            else:
                # Check if output is valid Python and apply highlighting if so
                if self.is_valid_python(output):
                    self.apply_python_highlighting(cursor, output)
                else:
                    cursor.insertText(output)
            cursor.insertText("\n")
            
        self.setTextCursor(cursor)
        self.insert_prompt()
        
    def on_input_requested(self, prompt: str):
        """Handle input request from Python execution thread - display inline"""
        if self.waiting_for_input:
            return
            
        self.waiting_for_input = True
        self.input_prompt = prompt
        
        # Display the input prompt inline in the terminal
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(prompt)
        
        # Update command start position to be after the prompt
        self.command_start_position = cursor.position()
        self.setTextCursor(cursor)
        
    def navigate_history(self, direction: int):
        """Navigate through command history"""
        if not self.command_history:
            return
            
        new_index = self.history_index + direction
        
        if 0 <= new_index < len(self.command_history):
            self.history_index = new_index
            self.set_current_command(self.command_history[self.history_index])
        elif new_index >= len(self.command_history):
            self.history_index = len(self.command_history)
            self.set_current_command("")

class PythonREPLTerminal(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.install_dir = self.get_app_data_dir()
        self.drag_start_position = None
        self.setup_ui()
        self.setup_menus()
        self.check_pyco_file()
        
    def get_app_data_dir(self):
        """Get the cross-platform application data directory"""
        import platform
        system = platform.system()
        
        if system == "Windows":
            app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
        elif system == "Darwin":  # macOS
            app_data = os.path.expanduser('~/Library/Application Support')
        else:  # Linux and other Unix-like systems
            app_data = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        
        # Create pyco subdirectory
        pyco_dir = os.path.join(app_data, 'pyco')
        os.makedirs(pyco_dir, exist_ok=True)
        
        return pyco_dir
        
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is in menu bar area
            menu_bar_rect = self.menu_bar.geometry()
            if menu_bar_rect.contains(event.pos()):
                # Check if clicking on empty space in menu bar
                local_pos = event.pos() - menu_bar_rect.topLeft()
                menu_action = self.menu_bar.actionAt(local_pos)
                if menu_action is None:
                    self.drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    event.accept()
                    return
            else:
                # Clicking outside menu bar - enable dragging
                self.drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start_position)
            event.accept()
            return
        super().mouseMoveEvent(event)
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("pyco - Python Console Terminal")
        self.setGeometry(100, 100, 480, 510)
        
        # Remove title bar for retro look
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # Set retro computer styling - dark mode with custom borders
        self.setStyleSheet("""
            QMainWindow {
                background-color: rgb(40, 40, 40);     /* Dark background */
                border: 5px solid #8a8375;             /* 20% brighter custom brownish-beige border */
                color: rgb(220, 220, 220);             /* Light text */
            }
            QMenuBar {
                background-color: rgb(50, 50, 50);     /* Dark menu background */
                color: rgb(220, 220, 220);             /* Light text */
                border-bottom: 1px solid #8a8375;
                font-family: "Courier New";
                font-size: 14px;
                font-weight: bold;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 8px 8px;
                color: rgb(220, 220, 220);
                font-family: "Courier New";
                font-size: 14px;
                font-weight: bold;
                line-height: 1.2;
            }
            QMenuBar::item:selected {
                background-color: #8a8375;
                color: rgb(255, 255, 255);
            }
            QMenu {
                background-color: rgb(50, 50, 50);
                color: rgb(220, 220, 220);
                border: 1px solid #8a8375;
                font-family: "Courier New";
                font-size: 13px;
                font-weight: bold;
            }
            QMenu::item:selected {
                background-color: #8a8375;
                color: rgb(255, 255, 255);
            }
            QStatusBar {
                background-color: #8a8375;             /* 20% brighter custom brownish-beige status bar */
                color: rgb(255, 255, 255);             /* White text for better contrast */
                border-top: 1px solid #8a8375;
            }
            QStatusBar::item {
                border: none;                          /* Remove any separator lines between status bar items */
            }
        """)
        
        # Set window icon - handle both development and PyInstaller environments
        if getattr(sys, 'frozen', False):
            # PyInstaller bundle - icon is in the temp directory
            icon_path = os.path.join(sys._MEIPASS, "pyco.ico")
        else:
            # Development - icon is in the source directory
            icon_path = os.path.join(self.install_dir, "pyco.ico")
        
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Create central widget with lighter background to show terminal border
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: rgb(113, 108, 95);")  # Same as border color for contrast
        
        # Enable mouse tracking for dragging from border areas
        central_widget.setMouseTracking(True)
        central_widget.mousePressEvent = self.central_widget_mouse_press
        central_widget.mouseMoveEvent = self.central_widget_mouse_move
        
        self.setCentralWidget(central_widget)
        
        # Create layout with margins to show the terminal border
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 10, 15, 15)  # Increased top margin for 15px top border
        
        # Add color control panel
        self.setup_color_controls(layout)
        
        # Create terminal widget with CRT effects and 6 layered borders
        self.terminal_with_effects = TerminalWithCRTEffects()
        self.terminal = self.terminal_with_effects.terminal  # For compatibility with existing code
        
        # Create dynamic border layers
        self.create_border_layers()
        
        # Add the outermost layer to the main layout  
        layout.addWidget(self.border_layers[0])
        
        # Initialize colors after border layers are created
        self.update_colors()
        
        # Status bar with centered text
        status_bar = self.statusBar()
        status_label = QLabel("pyco")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Set old-style font (monospace/typewriter style)
        status_font = QFont("Courier New", 16, QFont.Weight.Bold)
        status_font.setStyleHint(QFont.StyleHint.TypeWriter)
        status_label.setFont(status_font)
        
        # Style the label to match the retro theme
        status_label.setStyleSheet("""
            QLabel {
                color: #d4c4a0;
                background-color: transparent;
                padding: 2px;
            }
        """)
        
        # Clear any default message and add our custom label
        status_bar.clearMessage()
        status_bar.addWidget(status_label, 1)  # Stretch factor 1 to center it
        
        # Set focus to terminal
        self.terminal.setFocus()
        
    def setup_color_controls(self, layout):
        """Setup static border colors without controls"""
        # Initialize border layers first
        self.border_layers = []
        self.border_layouts = []
        
        # Static CRT colors - Inner: #244024, Outer: #1b301b
        self.inner_color = (36, 64, 36)  # #244024
        self.outer_color = (27, 48, 27)  # #1b301b
        
    def apply_static_colors(self):
        """Apply static border colors after border layers are created"""
        self.update_colors()
        
    def create_border_layers(self):
        """Create the 6 border layers dynamically"""
        self.border_layers = []
        self.border_layouts = []
        
        # Create 6 layers
        for i in range(6):
            layer = QWidget()
            layout_obj = QVBoxLayout(layer)
            layout_obj.setContentsMargins(2, 2, 2, 2)
            
            self.border_layers.append(layer)
            self.border_layouts.append(layout_obj)
        
        # Nest the layers (outermost first)
        self.border_layouts[5].addWidget(self.terminal_with_effects)  # Layer 1 (innermost) contains terminal
        self.border_layouts[4].addWidget(self.border_layers[5])       # Layer 2 contains Layer 1
        self.border_layouts[3].addWidget(self.border_layers[4])       # Layer 3 contains Layer 2
        self.border_layouts[2].addWidget(self.border_layers[3])       # Layer 4 contains Layer 3
        self.border_layouts[1].addWidget(self.border_layers[2])       # Layer 5 contains Layer 4
        self.border_layouts[0].addWidget(self.border_layers[1])       # Layer 6 contains Layer 5
        
        # Apply static colors after layers are created
        self.update_colors()
        
    def update_colors(self):
        """Update border colors with static fade between inner and outer"""
        # Check if border layers exist
        if not hasattr(self, 'border_layers') or not self.border_layers:
            return
            
        # Use static colors
        inner_r, inner_g, inner_b = self.inner_color
        outer_r, outer_g, outer_b = self.outer_color
        
        # Calculate even fade steps for 6 layers
        colors = []
        for i in range(6):
            # i=0 is outermost, i=5 is innermost
            factor = i / 5.0  # 0.0 to 1.0 for even fade
            r = int(outer_r + (inner_r - outer_r) * factor)
            g = int(outer_g + (inner_g - outer_g) * factor)
            b = int(outer_b + (inner_b - outer_b) * factor)
            colors.append((r, g, b))
        
        # Apply colors to layers
        for i, (r, g, b) in enumerate(colors):
            style = f"QWidget {{ background-color: rgb({r}, {g}, {b}); border: 2px solid rgb({r}, {g}, {b}); }}"
            if i < len(self.border_layers):
                self.border_layers[i].setStyleSheet(style)
        
    def load_pyco_file(self):
        """Load pyco.py into the Python environment"""
        pyco_path = os.path.join(self.install_dir, "pyco.py")
        
        if os.path.exists(pyco_path):
            try:
                # Load pyco.py into the Python executor's globals
                with open(pyco_path, 'r', encoding='utf-8') as f:
                    pyco_code = f.read()
                
                # Execute pyco.py in the Python environment with proper stdout capture
                import io
                old_stdout = sys.stdout
                stdout_capture = io.StringIO()
                
                try:
                    sys.stdout = stdout_capture
                    exec(pyco_code, self.terminal.python_executor.globals_dict)
                    
                    # Get any output from pyco.py execution and display it
                    output = stdout_capture.getvalue()
                    if output.strip():
                        # Remove only leading newlines to avoid extra space at top, preserve indentation
                        clean_output = output.lstrip('\n')
                        self.terminal.append_system_message(clean_output)
                finally:
                    sys.stdout = old_stdout
                    
                return True
            except Exception as e:
                self.terminal.append_system_message(f"Error loading pyco.py: {str(e)}\n")
                return False
        return False
        
    def check_pyco_file(self):
        """Check if pyco.py exists, load it if it does, or offer to download if not"""
        pyco_path = os.path.join(self.install_dir, "pyco.py")
        
        if os.path.exists(pyco_path):
            # Load the existing pyco.py file
            self.load_pyco_file()
            # Insert prompt after loading is complete
            self.terminal.insert_prompt()
        else:
            # Add message to terminal about missing pyco.py
            self.terminal.append_system_message(
                "pyco.py not found in application directory.\n"
                "Would you like to download pyco.py and README.md from GitHub? (y/n): "
            )
            self.terminal.pyco_download_pending = True
            # Set a special prompt for the response
            self.terminal.command_start_position = self.terminal.textCursor().position()
            
    def download_pyco(self):
        """Download pyco.py and README.md from GitHub"""
        self.progress_dialog = QProgressDialog("Downloading pyco.py and README.md...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        
        self.downloader = PycoDownloader(self.install_dir)
        self.downloader.download_finished.connect(self.on_download_finished)
        self.progress_dialog.canceled.connect(self.downloader.terminate)
        self.downloader.start()
        
    @pyqtSlot(bool, str)
    def on_download_finished(self, success: bool, message: str):
        """Handle download completion"""
        self.progress_dialog.hide()
        
        if success:
            # Automatically load the downloaded pyco.py file
            if self.load_pyco_file():
                # File loaded successfully - don't show the loading message
                pass
            else:
                self.terminal.append_system_message("Error: Could not load pyco.py after download\n")
        else:
            self.terminal.append_system_message(f"✗ {message}\n")
            
        self.terminal.pyco_download_pending = False
        self.terminal.insert_prompt()
        
    def setup_menus(self):
        """Setup application menus"""
        menubar = self.menuBar()
        
        # Store reference to menubar for dragging
        self.menu_bar = menubar
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        # Update pyco action
        update_pyco_action = QAction("Update pyco.py", self)
        update_pyco_action.setShortcut(QKeySequence("Ctrl+U"))
        update_pyco_action.setStatusTip("Download or update pyco.py and README.md from GitHub")
        update_pyco_action.triggered.connect(self.download_pyco)
        file_menu.addAction(update_pyco_action)
        
        file_menu.addSeparator()
        
        # Clear action
        clear_action = QAction("Clear Terminal", self)
        clear_action.setShortcut(QKeySequence("Ctrl+L"))
        clear_action.triggered.connect(self.clear_terminal)
        file_menu.addAction(clear_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        # About action
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # Help action
        help_action = QAction("Help", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.show_readme)
        help_menu.addAction(help_action)
        
        # Create a single corner widget with both draggable area and power button
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 10, 0)
        corner_layout.setSpacing(0)
        
        # Calculate the width needed to span from Help menu to power button
        # Get the menu bar width and subtract the menu items width
        menubar_width = self.width() if hasattr(self, 'width') else 800
        estimated_menus_width = 100  # Approximate width of "File" and "Help" menus
        button_width = 80  # Larger power button + extra margins and spacing
        drag_width = max(200, menubar_width - estimated_menus_width - button_width)
        
        # Add large draggable spacer with calculated width
        self.drag_spacer = QWidget()
        self.drag_spacer.setMinimumWidth(drag_width)
        self.drag_spacer.setStyleSheet("background-color: transparent;")
        self.drag_spacer.mousePressEvent = self.drag_spacer_mouse_press
        self.drag_spacer.mouseMoveEvent = self.drag_spacer_mouse_move
        self.drag_spacer.mouseReleaseEvent = self.drag_spacer_mouse_release
        corner_layout.addWidget(self.drag_spacer)
        
        # Add spacing before power button
        corner_layout.addSpacing(15)
        
        # Add power button
        power_button = QPushButton()
        power_button.setFixedSize(40, 40)
        power_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(180, 50, 50);
                border: 1px solid rgb(120, 30, 30);
                border-radius: 20px;
                color: white;
                font-weight: bold;
                font-size: 20px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: rgb(200, 60, 60);
            }
            QPushButton:pressed {
                background-color: rgb(160, 40, 40);
            }
        """)
        power_button.setText("⏻")
        power_button.clicked.connect(self.close)
        corner_layout.addWidget(power_button, 0)  # No stretch for the button
        
        # Add spacing after power button
        corner_layout.addSpacing(10)
        
        menubar.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        

    def central_widget_mouse_press(self, event):
        """Handle mouse press on central widget (border areas) for window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def central_widget_mouse_move(self, event):
        """Handle mouse move on central widget for window dragging"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start_position)
            event.accept()
            
    def drag_spacer_mouse_press(self, event):
        """Handle mouse press on drag spacer for window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def drag_spacer_mouse_move(self, event):
        """Handle mouse move on drag spacer for window dragging"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start_position)
            event.accept()
        else:
            # Reset drag position when not dragging
            self.drag_start_position = None

    def drag_spacer_mouse_release(self, event):
        """Handle mouse release on drag spacer to end dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = None
            event.accept()
            
    def resizeEvent(self, event):
        """Handle window resize to update drag spacer width"""
        super().resizeEvent(event)
        
        # Only update drag spacer width if we're not currently dragging
        if hasattr(self, 'drag_spacer') and self.drag_start_position is None:
            menubar_width = self.width()
            estimated_menus_width = 100  # Approximate width of "File" and "Help" menus
            button_width = 80  # Larger power button + extra margins and spacing
            drag_width = max(200, menubar_width - estimated_menus_width - button_width)
            
            # Only update if the width has changed significantly to avoid unnecessary updates
            current_width = self.drag_spacer.minimumWidth()
            if abs(drag_width - current_width) > 10:
                self.drag_spacer.setMinimumWidth(drag_width)
            
    def clear_terminal(self):
        """Clear the terminal"""
        self.terminal.clear()
        self.terminal.insert_prompt()
        
    def show_about(self):
        """Show about dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle("About")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            "<h3>Pyco - Happy Calculating!</h3>"
            "<p>Your fully featured EDC - Every Day Calculator</p>"
            "<p>Lee Holmes and Contributors<br>"
            "<a href='https://github.com/LeeHolmes/pycoterm'>https://github.com/LeeHolmes/pycoterm</a></p>"
        )
        msg.exec()
                         

    def show_readme(self):
        """Show README.md content in a dialog"""
        readme_path = os.path.join(self.install_dir, "README.md")
        
        if not os.path.exists(readme_path):
            QMessageBox.information(self, "README Not Found", 
                                  "README.md not found in application directory.\n"
                                  "Try downloading pyco files from the File menu.")
            return
            
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read README.md: {e}")
            return
            
        readme_dialog = QDialog(self)
        readme_dialog.setWindowTitle("Pyco Help")
        readme_dialog.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        readme_dialog.setFixedSize(700, 500)
        
        layout = QVBoxLayout(readme_dialog)
        readme_browser = QTextBrowser()
        
        # Convert basic markdown to HTML for better display
        html_content = self.markdown_to_html(readme_content)
        readme_browser.setHtml(html_content)
        
        layout.addWidget(readme_browser)
        
        readme_dialog.exec()
        
    def markdown_to_html(self, markdown_text):
        """Convert markdown to HTML with comprehensive support"""
        lines = markdown_text.split('\n')
        html_lines = []
        in_code_block = False
        in_list = False
        code_block_content = []
        code_block_lang = ""
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Handle code blocks (multi-line fences)
            if stripped.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_block_lang = stripped[3:].strip()
                    code_block_content = []
                else:
                    in_code_block = False
                    # Process the collected code block content
                    escaped_content = '\n'.join(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') for line in code_block_content)
                    lang_class = f' class="language-{code_block_lang}"' if code_block_lang else ''
                    lang_label = f'<div style="background-color: #e0e0e0; padding: 2px 8px; font-size: 1.6em; color: #666; border-bottom: 1px solid #ccc;">{code_block_lang}</div>' if code_block_lang else ''
                    html_lines.append(f'<div style="border: 1px solid #ddd; border-radius: 5px; margin: 8px 0; overflow: hidden;">{lang_label}<pre{lang_class} style="background-color: #f8f8f8; padding: 15px; margin: 0; font-family: \'Courier New\', Consolas, monospace; font-size: 1.8em; line-height: 1.0; overflow-x: auto; white-space: pre-wrap;">{escaped_content}</pre></div>')
                i += 1
                continue
            
            if in_code_block:
                # Collect lines for the code block
                code_block_content.append(line)
                i += 1
                continue
            
            # Handle headers
            if stripped.startswith('# '):
                html_lines.append(f'<h1 style="color: #333; border-bottom: 2px solid #ccc; padding-bottom: 5px;">{stripped[2:]}</h1>')
            elif stripped.startswith('## '):
                html_lines.append(f'<h2 style="color: #444; border-bottom: 1px solid #ddd; padding-bottom: 3px;">{stripped[3:]}</h2>')
            elif stripped.startswith('### '):
                html_lines.append(f'<h3 style="color: #555;">{stripped[4:]}</h3>')
            elif stripped.startswith('#### '):
                html_lines.append(f'<h4 style="color: #666;">{stripped[5:]}</h4>')
            elif stripped.startswith('##### '):
                html_lines.append(f'<h5 style="color: #777;">{stripped[6:]}</h5>')
            elif stripped.startswith('###### '):
                html_lines.append(f'<h6 style="color: #888;">{stripped[7:]}</h6>')
            
            # Handle lists
            elif stripped.startswith('- ') or stripped.startswith('* '):
                if not in_list:
                    html_lines.append('<ul style="margin: 5px 0; padding-left: 20px;">')
                    in_list = True
                content = self._format_inline_markdown(stripped[2:])
                html_lines.append(f'<li style="margin: 2px 0;">{content}</li>')
            elif re.match(r'^\d+\. ', stripped):
                if not in_list:
                    html_lines.append('<ol style="margin: 5px 0; padding-left: 20px;">')
                    in_list = True
                content = self._format_inline_markdown(re.sub(r'^\d+\. ', '', stripped))
                html_lines.append(f'<li style="margin: 3px 0;">{content}</li>')
            else:
                # Close list if we were in one
                if in_list:
                    html_lines.append('</ul>' if any(l.strip().startswith(('- ', '* ')) for l in lines[:i] if l.strip()) else '</ol>')
                    in_list = False
                
                # Handle tables
                if '|' in stripped and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Check if next line is a table separator (contains | and -)
                    if '|' in next_line and '-' in next_line:
                        # This looks like a table
                        table_rows = []
                        table_start = i
                        
                        # Collect all table rows
                        while i < len(lines) and '|' in lines[i].strip():
                            table_rows.append(lines[i].strip())
                            i += 1
                        
                        if len(table_rows) >= 2:
                            # Process the table
                            html_lines.append('<table style="border-collapse: collapse; margin: 8px 0; width: 100%;">')
                            
                            # Header row
                            header_cells = [cell.strip() for cell in table_rows[0].split('|')[1:-1]]  # Remove empty first/last
                            html_lines.append('<thead>')
                            html_lines.append('<tr>')
                            for cell in header_cells:
                                content = self._format_inline_markdown(cell)
                                html_lines.append(f'<th style="border: 1px solid #ddd; padding: 8px; background-color: #f5f5f5; text-align: left; font-weight: bold;">{content}</th>')
                            html_lines.append('</tr>')
                            html_lines.append('</thead>')
                            
                            # Body rows (skip separator row at index 1)
                            if len(table_rows) > 2:
                                html_lines.append('<tbody>')
                                for row in table_rows[2:]:
                                    cells = [cell.strip() for cell in row.split('|')[1:-1]]  # Remove empty first/last
                                    html_lines.append('<tr>')
                                    for cell in cells:
                                        content = self._format_inline_markdown(cell)
                                        html_lines.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{content}</td>')
                                    html_lines.append('</tr>')
                                html_lines.append('</tbody>')
                            
                            html_lines.append('</table>')
                        
                        i -= 1  # Adjust because the outer loop will increment
                        i += 1
                        continue
                
                # Handle blockquotes
                if stripped.startswith('> '):
                    content = self._format_inline_markdown(stripped[2:])
                    html_lines.append(f'<blockquote style="margin: 5px 0; padding: 10px; border-left: 4px solid #ddd; background-color: #f9f9f9; font-style: italic;">{content}</blockquote>')
                
                # Handle indented code blocks (4 spaces or 1 tab)
                elif line.startswith('    ') or line.startswith('\t'):
                    # Collect consecutive indented lines
                    code_lines = []
                    while i < len(lines) and (lines[i].startswith('    ') or lines[i].startswith('\t') or not lines[i].strip()):
                        if lines[i].startswith('    '):
                            code_lines.append(lines[i][4:])  # Remove 4 spaces
                        elif lines[i].startswith('\t'):
                            code_lines.append(lines[i][1:])  # Remove 1 tab
                        else:
                            code_lines.append(lines[i])  # Empty line
                        i += 1
                    
                    # Remove trailing empty lines
                    while code_lines and not code_lines[-1].strip():
                        code_lines.pop()
                    
                    if code_lines:
                        escaped_code = '\n'.join(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') for line in code_lines)
                        html_lines.append(f'<div style="border: 1px solid #ddd; border-radius: 5px; margin: 8px 0; overflow: hidden;"><pre style="background-color: #f8f8f8; padding: 15px; margin: 0; font-family: \'Courier New\', Consolas, monospace; font-size: 1.8em; line-height: 1.0; overflow-x: auto; white-space: pre-wrap;">{escaped_code}</pre></div>')
                    
                    i -= 1  # Adjust because the outer loop will increment
                
                # Handle horizontal rules
                elif stripped in ['---', '***', '___']:
                    html_lines.append('<hr style="margin: 15px 0; border: none; border-top: 1px solid #ccc;">')
                
                # Handle regular paragraphs
                elif stripped:
                    content = self._format_inline_markdown(stripped)
                    html_lines.append(f'<p style="margin: 5px 0; line-height: 1.0;">{content}</p>')
                
                # Handle empty lines - just skip them (they naturally separate paragraphs)
                else:
                    pass
            
            i += 1
        
        # Close any remaining lists
        if in_list:
            html_lines.append('</ul>')
        
        return f'<html><head><style>body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 2em; line-height: 1.0; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}</style></head><body>{"".join(html_lines)}</body></html>'
    
    def _format_inline_markdown(self, text):
        """Format inline markdown elements"""
        # Handle code spans first (to avoid conflicts)
        text = re.sub(r'`([^`]+)`', r'<code style="background-color: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-family: monospace;">\1</code>', text)
        
        # Handle bold and italic (order matters)
        text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'<strong><em>\1</em></strong>', text)  # Bold + italic
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)  # Italic
        
        # Handle alternative bold/italic syntax
        text = re.sub(r'___([^_]+)___', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)
        text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)
        
        # Handle links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #0066cc; text-decoration: none;" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">\1</a>', text)
        
        # Handle strikethrough
        text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)
        
        return text

def main():
    """Main application entry point"""
    # Windows-specific: Set App User Model ID for proper taskbar grouping and icon
    try:
        import ctypes
        # Set the App User Model ID to make Windows treat this as a unique application
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pyco.pyco.1.0")
    except:
        pass
    
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("pyco")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("pyco")
    app.setApplicationDisplayName("pyco")
    
    # Set application icon - handle both development and PyInstaller environments
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle - icon is in the temp directory
        icon_path = os.path.join(sys._MEIPASS, "pyco.ico")
    else:
        # Development - icon is in the source directory
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pyco.ico")
    
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Create and show main window
    window = PythonREPLTerminal()
    window.show()
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()