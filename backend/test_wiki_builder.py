import wiki_builder as wb


def test_extract_json_plain():
    assert wb.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "Sure!\n```json\n{\"entities\": [], \"relationships\": []}\n```\nDone."
    assert wb.extract_json(text) == {"entities": [], "relationships": []}


def test_extract_json_embedded():
    text = 'noise before {"x": [1, 2]} noise after'
    assert wb.extract_json(text) == {"x": [1, 2]}


def test_extract_json_invalid_returns_empty_dict():
    assert wb.extract_json("not json at all") == {}


def test_slugify():
    assert wb.slugify("Claude Mythos Preview!") == "claude-mythos-preview"
    assert wb.slugify("  Multi   Space ") == "multi-space"
    assert wb.slugify("CamelCase/With:Punct") == "camelcase-with-punct"
