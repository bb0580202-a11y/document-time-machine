from dtm.app.reconcile import plan_reconcile


def test_start_new_folders():
    to_start, to_stop, to_restart = plan_reconcile(
        desired={"u1": "/a", "u2": "/b"}, running={})
    assert to_start == {"u1", "u2"} and to_stop == set() and to_restart == set()


def test_stop_removed_folders():
    to_start, to_stop, to_restart = plan_reconcile(
        desired={"u1": "/a"}, running={"u1": "/a", "u2": "/b"})
    assert to_start == set() and to_stop == {"u2"} and to_restart == set()


def test_restart_on_relocate_same_uuid_diff_path():
    to_start, to_stop, to_restart = plan_reconcile(
        desired={"u1": "/new/path"}, running={"u1": "/old/path"})
    assert to_start == set() and to_stop == set() and to_restart == {"u1"}


def test_noop_when_identical():
    to_start, to_stop, to_restart = plan_reconcile(
        desired={"u1": "/a"}, running={"u1": "/a"})
    assert to_start == set() and to_stop == set() and to_restart == set()


def test_mixed():
    to_start, to_stop, to_restart = plan_reconcile(
        desired={"u1": "/a", "u2": "/moved", "u3": "/c"},
        running={"u1": "/a", "u2": "/old", "u4": "/d"})
    assert to_start == {"u3"}
    assert to_stop == {"u4"}
    assert to_restart == {"u2"}
