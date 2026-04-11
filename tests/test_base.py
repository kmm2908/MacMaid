from modules.base import make_result, ModuleResult

def test_make_result_defaults():
    r = make_result("Caches", "safe")
    assert r["category"] == "Caches"
    assert r["risk"] == "safe"
    assert r["items"] == []
    assert r["total_size_bytes"] == 0
    assert r["suggestion"] == ""
    assert r["action"] == "trash"

def test_make_result_custom_action():
    r = make_result("Trash", "safe", action="empty-trash")
    assert r["action"] == "empty-trash"

def test_make_result_inform_only():
    r = make_result("Memory", "inform-only", action="none")
    assert r["risk"] == "inform-only"
    assert r["action"] == "none"

def test_make_item():
    from modules.base import make_item
    item = make_item("/tmp/foo.log", 1024, "foo.log")
    assert item["path"] == "/tmp/foo.log"
    assert item["size_bytes"] == 1024
    assert item["label"] == "foo.log"
    assert item["meta"] == {}

def test_make_item_with_meta():
    from modules.base import make_item
    item = make_item("/tmp/foo.log", 1024, "foo.log", meta={"last_opened": "2024-01-01"})
    assert item["meta"]["last_opened"] == "2024-01-01"
