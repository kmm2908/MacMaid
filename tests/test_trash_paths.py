from modules.base import is_in_trash


def test_home_trash_root_is_in_trash():
    assert is_in_trash("/Users/fred/.Trash")


def test_file_inside_home_trash_is_in_trash():
    assert is_in_trash("/Users/fred/.Trash/node_modules")
    assert is_in_trash("/Users/fred/.Trash/proj/__pycache__/x.pyc")


def test_volume_trashes_is_in_trash():
    assert is_in_trash("/Volumes/Ext Data/.Trashes/501")
    assert is_in_trash("/Volumes/Ext Data/.Trashes/501/proj/node_modules")


def test_normal_paths_are_not_in_trash():
    assert not is_in_trash("/Users/fred/Documents/report.pdf")
    assert not is_in_trash("/Volumes/Ext Data/VSC Projects/app/node_modules")
    assert not is_in_trash("/Users/fred/Library/Caches/pip")


def test_lookalike_names_are_not_in_trash():
    assert not is_in_trash("/Users/fred/Trash")
    assert not is_in_trash("/Users/fred/.Trashcan/x")
    assert not is_in_trash("/Users/fred/my.Trash/x")


def test_trailing_slash_and_relative_forms():
    assert is_in_trash("/Users/fred/.Trash/")
    assert is_in_trash("/Users/fred/./.Trash/x")
