"""AppleScript escaping in the Apple Notes adapter (the part most likely to break a script)."""

from adapters import apple_notes


def test_osa_quote_escapes_backslash_then_quote():
    # Backslashes are doubled first, then double-quotes are backslash-escaped.
    assert apple_notes._osa_quote('a"b\\c') == 'a\\"b\\\\c'
    assert apple_notes._osa_quote("plain text") == "plain text"


def test_build_script_escapes_title_and_embeds_folder():
    script = apple_notes._build_script('He said "hi"', "<div>body</div>", "My Folder")
    # The title's quotes are escaped so they can't break out of the AppleScript literal.
    assert 'He said \\"hi\\"' in script
    # The folder name is used (exists-check + make-new-note).
    assert '"My Folder"' in script
    # Sanity: it's a Notes tell block.
    assert 'tell application "Notes"' in script
