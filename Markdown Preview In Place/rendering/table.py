"""Lay out fixed-width table cells in Sublime Text's minihtml."""

from html import escape
import re
from unicodedata import category, east_asian_width


NON_ASCII = re.compile(r"[^\x00-\x7f]")
WORDS = re.compile(r"\S+|\s+")
TEXT_UNIT = 0.55  # Approximate Consolas character advance in rem.
COLUMN_UNIT = 0.58  # Reserve room for font fallback when sizing wrapped cells.
CELL_PADDING = 0.55
LINE_HEIGHT = 1.35
ROW_PADDING = 0.36


def text_width(text):
    if not NON_ASCII.search(text):
        return len(text)
    return sum(2 if east_asian_width(char) in ("F", "W") else 1
               for char in text if category(char) not in ("Mn", "Me", "Cf"))


class Cell:
    def __init__(self, align):
        self.align = align
        self.parts = []
        self.width = 0

    def append(self, markup):
        if markup:
            self.parts.append((False, markup))

    def add_text(self, text):
        self.parts.append((True, text))
        self.width += text_width(text)

    def lines(self, width):
        if self.width <= width:
            html = "".join(self.encode(part) if is_text else part for is_text, part in self.parts)
            return [(html, self.width)]
        lines, tags, fragments = [], [], []
        used = 0
        for is_text, part in self.parts:
            if not is_text:
                fragments.append(part)
                if part.startswith("</"):
                    tags.pop()
                else:
                    tag = part[1:-1].split(" ", 1)[0]
                    tags.append((part, "</{}>".format(tag)))
                continue
            for token in WORDS.findall(part):
                token_width = text_width(token)
                if used and used + token_width > width and token_width <= width:
                    lines.append(self.close_line(fragments, tags, used))
                    fragments, used = [tag[0] for tag in tags], 0
                    if token.isspace():
                        continue
                if token_width <= width:
                    fragments.append(self.encode(token))
                    used += token_width
                    continue
                for char in token:
                    char_width = text_width(char)
                    if used + char_width > width:
                        lines.append(self.close_line(fragments, tags, used))
                        fragments, used = [tag[0] for tag in tags], 0
                    fragments.append(self.encode(char))
                    used += char_width
        lines.append(("".join(fragments), used))
        return lines

    @staticmethod
    def encode(text):
        return escape(text, quote=False).replace(" ", "&nbsp;")

    @staticmethod
    def close_line(fragments, tags, used):
        fragments.extend(tag[1] for tag in reversed(tags))
        return "".join(fragments), used

    def render_line(self, line, width):
        html, used = line
        free = max(0, width - 2 * CELL_PADDING - used * TEXT_UNIT)
        left = free if self.align == "right" else 0
        if self.align == "center":
            left = free / 2
        return '<div style="margin-left:{:.3f}rem">{}</div>'.format(CELL_PADDING + left, html)


class Table:
    def __init__(self):
        self.rows = []
        self.widths = []

    def add_cell(self, cell):
        row = self.rows[-1]
        column = len(row)
        row.append(cell)
        if column == len(self.widths):
            self.widths.append(cell.width)
        else:
            self.widths[column] = max(self.widths[column], cell.width)

    def render(self, budget):
        count = len(self.widths)
        if not count:
            return ""
        available = max(count * 4, budget * 19 // 20 - 3 * count - 1)
        widths = [min(width, available // count) for width in self.widths]
        remaining = available - sum(widths)
        expanding = sum(width < natural for width, natural in zip(widths, self.widths))
        for index, natural in enumerate(self.widths):
            if widths[index] < natural:
                extra = min(natural - widths[index], (remaining + expanding - 1) // expanding)
                widths[index] += extra
                remaining -= extra
                expanding -= 1
        cell_widths = [width * COLUMN_UNIT + 2 * CELL_PADDING for width in widths]
        offsets = [0]
        for width in cell_widths:
            offsets.append(offsets[-1] + width)
        output = ['<div class="table">']
        for index, row in enumerate(self.rows):
            css_class = "table-cell"
            if index == 0:
                css_class = "table-header"
            elif index % 2 == 0:
                css_class = "table-stripe"
            columns = [cell.lines(width) for cell, width in zip(row, widths)]
            height = LINE_HEIGHT * max(map(len, columns)) + ROW_PADDING
            for column, (cell, cell_lines) in enumerate(zip(row, columns)):
                width = cell_widths[column]
                style = "margin-left:{:.3f}rem;width:{:.3f}rem;height:{:.3f}rem".format(
                    offsets[column], width, height)
                last = column == count - 1
                if last:
                    style += ";border-right:1px solid var(--table-border)"
                else:
                    # The final cell advances the row. Other cells paint at the same y.
                    output.append('<div class="table-slot">')
                output.append('<div class="{}" style="{}"><div class="table-content">'.format(
                    css_class, style))
                output.extend(cell.render_line(line, width) for line in cell_lines)
                output.append("</div></div>" if last else "</div></div></div>")
        output.append('<div class="table-bottom" style="width:{:.3f}rem"></div></div>'.format(
            offsets[-1]))
        return "".join(output)
