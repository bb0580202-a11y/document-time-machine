import os

from dtm.app import single_instance


def test_acquire_then_second_blocked(tmp_path):
    lock = tmp_path / "daemon.lock"
    fd1 = single_instance.acquire(lock)
    assert fd1 is not None
    assert lock.exists()                              # O_CREAT 建了锁文件
    assert single_instance.acquire(lock) is None      # 第二个拿不到(已被独占)
    os.close(fd1)


def test_release_on_close_lets_second_acquire(tmp_path):
    # 焊死铁律:fd 被关=锁释放=守卫失效——反向证明"持有 fd"才是守卫本体
    lock = tmp_path / "daemon.lock"
    fd1 = single_instance.acquire(lock)
    os.close(fd1)
    fd2 = single_instance.acquire(lock)
    assert fd2 is not None
    os.close(fd2)
