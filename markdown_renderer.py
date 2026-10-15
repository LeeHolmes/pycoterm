import html
import re


def _format_inline(text):
    text = re.sub(
        r"`([^`]+)`",
        r'<code style="background-color: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-family: monospace;">\1</code>',
        text,
    )
    text = re.sub(r"\*\*\*([^*]+)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"___([^_]+)___", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color: #0066cc; text-decoration: none;">\1</a>',
        text,
    )
    return re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)


def render_markdown(markdown_text):
    lines = markdown_text.split("\n")
    rendered = []
    list_type = None
    index = 0

    def close_list():
        nonlocal list_type
        if list_type:
            rendered.append(f"</{list_type}>")
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            close_list()
            language = stripped[3:].strip()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            code = html.escape("\n".join(code_lines))
            label = (
                f'<div style="background-color: #e0e0e0; padding: 2px 8px; '
                f'font-size: 1.6em; color: #666; border-bottom: 1px solid #ccc;">'
                f"{html.escape(language)}</div>"
                if language
                else ""
            )
            language_class = f' class="language-{html.escape(language)}"' if language else ""
            rendered.append(
                '<div style="border: 1px solid #ddd; border-radius: 5px; margin: 8px 0; overflow: hidden;">'
                f"{label}<pre{language_class} style=\"background-color: #f8f8f8; padding: 15px; margin: 0; "
                "font-family: 'Courier New', Consolas, monospace; font-size: 1.8em; line-height: 1.0; "
                f'overflow-x: auto; white-space: pre-wrap;">{code}</pre></div>'
            )
        elif stripped.startswith("#"):
            close_list()
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                colors = ["#333", "#444", "#555", "#666", "#777", "#888"]
                border = (
                    " border-bottom: 2px solid #ccc; padding-bottom: 5px;"
                    if level == 1
                    else " border-bottom: 1px solid #ddd; padding-bottom: 3px;"
                    if level == 2
                    else ""
                )
                rendered.append(
                    f'<h{level} style="color: {colors[level - 1]};{border}">'
                    f"{_format_inline(match.group(2))}</h{level}>"
                )
        elif stripped.startswith(("- ", "* ")):
            if list_type != "ul":
                close_list()
                rendered.append('<ul style="margin: 5px 0; padding-left: 20px;">')
                list_type = "ul"
            rendered.append(
                f'<li style="margin: 2px 0;">{_format_inline(stripped[2:])}</li>'
            )
        elif re.match(r"^\d+\.\s+", stripped):
            if list_type != "ol":
                close_list()
                rendered.append('<ol style="margin: 5px 0; padding-left: 20px;">')
                list_type = "ol"
            content = re.sub(r"^\d+\.\s+", "", stripped)
            rendered.append(f'<li style="margin: 3px 0;">{_format_inline(content)}</li>')
        elif (
            "|" in stripped
            and index + 1 < len(lines)
            and "|" in lines[index + 1]
            and "-" in lines[index + 1]
        ):
            close_list()
            table_rows = []
            while index < len(lines) and "|" in lines[index].strip():
                table_rows.append(lines[index].strip())
                index += 1
            index -= 1
            cells = lambda row: [cell.strip() for cell in row.strip("|").split("|")]
            rendered.append(
                '<table style="border-collapse: collapse; margin: 8px 0; width: 100%;"><thead><tr>'
            )
            for cell in cells(table_rows[0]):
                rendered.append(
                    '<th style="border: 1px solid #ddd; padding: 8px; background-color: #f5f5f5; '
                    f'text-align: left; font-weight: bold;">{_format_inline(cell)}</th>'
                )
            rendered.append("</tr></thead>")
            if len(table_rows) > 2:
                rendered.append("<tbody>")
                for row in table_rows[2:]:
                    rendered.append("<tr>")
                    for cell in cells(row):
                        rendered.append(
                            f'<td style="border: 1px solid #ddd; padding: 8px;">{_format_inline(cell)}</td>'
                        )
                    rendered.append("</tr>")
                rendered.append("</tbody>")
            rendered.append("</table>")
        else:
            close_list()
            if stripped.startswith("> "):
                rendered.append(
                    '<blockquote style="margin: 5px 0; padding: 10px; border-left: 4px solid #ddd; '
                    f'background-color: #f9f9f9; font-style: italic;">{_format_inline(stripped[2:])}</blockquote>'
                )
            elif line.startswith(("    ", "\t")):
                code_lines = []
                while index < len(lines) and (
                    lines[index].startswith(("    ", "\t")) or not lines[index].strip()
                ):
                    current = lines[index]
                    code_lines.append(current[4:] if current.startswith("    ") else current[1:])
                    index += 1
                index -= 1
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                if code_lines:
                    rendered.append(
                        '<div style="border: 1px solid #ddd; border-radius: 5px; margin: 8px 0; overflow: hidden;">'
                        '<pre style="background-color: #f8f8f8; padding: 15px; margin: 0; '
                        "font-family: 'Courier New', Consolas, monospace; font-size: 1.8em; line-height: 1.0; "
                        f'overflow-x: auto; white-space: pre-wrap;">{html.escape(chr(10).join(code_lines))}</pre></div>'
                    )
            elif stripped in ("---", "***", "___"):
                rendered.append(
                    '<hr style="margin: 15px 0; border: none; border-top: 1px solid #ccc;">'
                )
            elif stripped:
                rendered.append(
                    f'<p style="margin: 5px 0; line-height: 1.0;">{_format_inline(stripped)}</p>'
                )
        index += 1

    close_list()
    return (
        '<html><head><style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", '
        "Roboto, sans-serif; font-size: 2em; line-height: 1.0; color: #333; max-width: 800px; "
        f'margin: 0 auto; padding: 20px; }}</style></head><body>{"".join(rendered)}</body></html>'
    )
