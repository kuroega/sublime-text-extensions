"""Show a live Markdown preview in a Sublime Text tab."""

import math
import os
from time import monotonic
import traceback

import sublime
import sublime_plugin

PREVIEW_KEY = "markdown_preview_in_place"
SPLIT = {"cols": [0.0, 0.5, 1.0], "rows": [0.0, 1.0],
         "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn", ".mdtxt"}
previews = {}


def is_markdown(view):
    if not view or view.settings().get(PREVIEW_KEY):
        return False
    extension = os.path.splitext(view.file_name() or "")[1].lower()
    return extension in MARKDOWN_EXTENSIONS or view.match_selector(0, "text.html.markdown")


def preview_group(window, source):
    cells = window.get_layout()["cells"]
    group = window.get_view_index(source)[0]
    _, top, right, bottom = cells[group]
    for index, (left, other_top, _, other_bottom) in enumerate(cells):
        if left == right and max(top, other_top) < min(bottom, other_bottom):
            return index
    return (group + 1) % len(cells)


class Preview:
    def __init__(self, window, source):
        self.window = window
        self.original_layout = None
        self.deadline = 0
        self.timer_pending = False
        self.render_pending = False
        self.rendered_source = None
        self.view = window.new_file()
        self.view.set_scratch(True)
        self.view.set_read_only(True)
        settings = self.view.settings()
        settings.set(PREVIEW_KEY, True)
        settings.set("gutter", False)
        settings.set("line_numbers", False)
        settings.set("highlight_line", False)
        settings.set("draw_white_space", "none")
        settings.set("scroll_past_end", False)
        self.source = source

    def show(self, source, to_side):
        if self.source.id() != source.id():
            self.view.set_viewport_position((0, 0), False)
        self.source = source
        if to_side and self.window.num_groups() == 1:
            self.original_layout = self.window.get_layout()
            self.window.set_layout(SPLIT)
        group = preview_group(self.window, source) if to_side else self.window.get_view_index(source)[0]
        if self.window.get_view_index(self.view)[0] != group:
            self.window.set_view_index(self.view, group, len(self.window.views_in_group(group)))
        if to_side:
            active_preview = self.window.active_view_in_group(group)
            if not active_preview or active_preview.id() != self.view.id():
                self.window.focus_view(self.view)
            self.window.focus_view(source)
        else:
            self.restore_layout()
            self.window.focus_view(self.view)
        self.queue_render(0)

    def queue_render(self, delay=250):
        self.deadline = monotonic() + delay / 1000
        self.schedule_capture()

    def schedule_capture(self):
        if not self.timer_pending and not self.render_pending:
            self.timer_pending = True
            sublime.set_timeout(self.capture, self.remaining_delay())

    def remaining_delay(self):
        return max(0, math.ceil((self.deadline - monotonic()) * 1000))

    def is_open(self):
        return (previews.get(self.window.id()) is self
                and self.view.is_valid() and self.source.is_valid())

    def source_version(self):
        pane_width = self.view.viewport_extent()[0]
        em_width = max(1, self.view.em_width())
        table_width = max(20, int(pane_width / em_width) - 5)
        return self.source.id(), self.source.change_count(), self.source.file_name(), table_width

    def capture(self):
        self.timer_pending = False
        if not self.is_open() or self.source.is_loading():
            return
        if self.remaining_delay():
            self.schedule_capture()
            return
        version = self.source_version()
        if version == self.rendered_source:
            return
        filename = version[2]
        title = os.path.basename(filename) if filename else self.source.name() or "Untitled"
        title = "Preview - " + title
        if title != self.view.name():
            self.view.set_name(title)
        text = self.source.substr(sublime.Region(0, self.source.size()))
        self.render_pending = True
        sublime.set_timeout_async(lambda: self.build(version, text), 0)

    def build(self, version, text):
        try:
            from .rendering import render

            content, links = render(text, version[2], version[3])
        except Exception:
            traceback.print_exc()
            content, links = "<p>Unable to render this Markdown. See the Sublime console.</p>", {}
        sublime.set_timeout(lambda: self.display(version, content, links), 0)

    def display(self, version, content, links):
        self.render_pending = False
        if not self.is_open():
            return
        if version != self.source_version():
            self.schedule_capture()
            return
        viewport = self.view.viewport_position()
        self.view.erase_phantoms(PREVIEW_KEY)
        self.view.add_phantom(PREVIEW_KEY, sublime.Region(0), content,
                              sublime.LAYOUT_BLOCK, lambda token: self.navigate(links, token))
        self.view.set_viewport_position(viewport, False)
        self.rendered_source = version

    def navigate(self, links, token):
        target = links.get(token)
        if target and self.source.is_valid():
            group = self.window.get_view_index(self.source)[0]
            self.window.open_file(target, group=group)

    def restore_layout(self):
        if (self.original_layout and self.window.is_valid()
                and self.window.get_layout() == SPLIT
                and not self.window.sheets_in_group(1)):
            self.window.set_layout(self.original_layout)
            self.original_layout = None

    def close_if_showing(self, source_id):
        if self.view.is_valid() and self.source.id() == source_id:
            self.view.close()


class OpenMarkdownPreviewInPlaceCommand(sublime_plugin.WindowCommand):
    def source_view(self):
        active = self.window.active_view()
        preview = previews.get(self.window.id())
        if active and preview and active.id() == preview.view.id():
            return preview.source
        return active

    def is_enabled(self, to_side=True):
        return is_markdown(self.source_view())

    def run(self, to_side=True):
        source = self.source_view()
        if not is_markdown(source):
            return
        preview = previews.get(self.window.id())
        if preview is None:
            preview = Preview(self.window, source)
            previews[self.window.id()] = preview
        preview.show(source, to_side)


class CloseMarkdownPreviewInPlaceCommand(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return self.window.id() in previews

    def run(self):
        preview = previews.get(self.window.id())
        if preview:
            preview.view.close()


class MarkdownPreviewInPlaceListener(sublime_plugin.EventListener):
    def refresh(self, view):
        window = view.window()
        preview = previews.get(window.id()) if window else None
        if preview and preview.source.id() == view.id():
            preview.queue_render()

    def on_modified(self, view):
        self.refresh(view)

    def on_post_save(self, view):
        self.refresh(view)

    def on_load(self, view):
        self.refresh(view)

    def on_close(self, view):
        for window_id, preview in list(previews.items()):
            if preview.view.id() == view.id():
                del previews[window_id]
                sublime.set_timeout(preview.restore_layout, 0)
                break
            if preview.source.id() == view.id():
                sublime.set_timeout(lambda: preview.close_if_showing(view.id()), 0)
                break


def plugin_loaded():
    for window in sublime.windows():
        for view in window.views():
            if view.settings().get(PREVIEW_KEY) and not view.is_dirty():
                view.close()


def plugin_unloaded():
    for preview in list(previews.values()):
        preview.view.close()
