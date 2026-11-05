# Markdown Preview In Place

A live Markdown preview in a tab or split pane in Sublime Text. It works on
Sublime Text 3 build 3211 and uses Sublime's minihtml renderer.

## Use

1. Open a Markdown file, or set an untitled buffer's syntax to **Markdown**.
2. Open the Command Palette (`Ctrl+Shift+P`) and choose a preview mode.
   - **Markdown: Open Preview in New Tab** uses the full width of the source pane.
   - **Markdown: Open Preview to the Side** shows the source and preview together.
     In a Markdown buffer, press `Ctrl+K` followed by `Ctrl+M` for this mode.
3. Edit the source. The preview updates before saving. Run either command
   from the source or its preview to switch modes, or from another Markdown
   file to preview that file.
4. Close the preview tab or run **Markdown: Close Preview**.

The preview supports headings, emphasis, blockquotes, lists, task items, fenced
code, and document-relative PNG, JPEG, and GIF images. Tables have a shaded
header, grid lines, Markdown column alignment, and wrapping for long cells.
Relative links to existing local files
open in the source pane. Web links are displayed as text and remote images use
their alt text. Raw HTML is displayed as text.

## Install

Choose **Preferences > Browse Packages** in Sublime Text and copy the
`Markdown Preview In Place` folder into the directory that opens.

The package includes the runtime modules it uses from
[Python-Markdown 2.6.11](https://pypi.org/project/Markdown/2.6.11/) for
compatibility with Sublime Text 3's Python 3.3 host. The bundled copy uses
single-pass fenced-code and placeholder replacement and avoids repeated list
shifting during reference parsing. See the
[bundled license](Markdown%20Preview%20In%20Place/_vendor/Python-Markdown-LICENSE.md).
